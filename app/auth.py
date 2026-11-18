"""Autenticação de uma única conta, sessões revogáveis e proteção CSRF.

Sem senhas ou tokens persistidos em texto claro: apenas hash Argon2 da senha
na configuração e SHA-256 de tokens aleatórios na tabela auth_sessions.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import sys
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from getpass import getpass
from threading import Lock

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import AuthSession, utcnow

COOKIE_MAX_AGE = 60 * 60 * 24 * 7  # uma semana sem necessitar novo login
FAILURE_WINDOW = 15 * 60
FAILURE_LIMIT = 8
_hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)
_failures: dict[str, deque[float]] = defaultdict(deque)
_failures_lock = Lock()
router = APIRouter(prefix="/api/auth", tags=["autenticação"])


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=1, max_length=512)


def is_production() -> bool:
    return os.getenv("APP_ENV", "development").casefold() == "production"


def cookie_name() -> str:
    return "__Host-estudo_session" if is_production() else "estudo_session"


def secret_key() -> bytes:
    return os.environ["APP_SECRET_KEY"].encode("utf-8")


def validate_auth_configuration() -> None:
    if not os.getenv("ADMIN_USERNAME"):
        raise RuntimeError("Configure ADMIN_USERNAME no ambiente.")
    try:
        _hasher.check_needs_rehash(os.environ["ADMIN_PASSWORD_HASH"])
    except (KeyError, InvalidHashError, VerificationError, ValueError) as exc:
        raise RuntimeError("Configure ADMIN_PASSWORD_HASH com um hash Argon2 válido.") from exc
    if len(os.getenv("APP_SECRET_KEY", "")) < 32:
        raise RuntimeError("Configure APP_SECRET_KEY com pelo menos 32 caracteres aleatórios.")
    if os.getenv("APP_ENV", "development") not in {"production", "development", "test"}:
        raise RuntimeError("APP_ENV deve ser production, development ou test.")


def token_hash(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def csrf_token(raw: str) -> str:
    return hmac.new(secret_key(), b"csrf:" + raw.encode("utf-8"), hashlib.sha256).hexdigest()


def find_session(request: Request, db: Session) -> AuthSession | None:
    raw = request.cookies.get(cookie_name())
    if not raw or len(raw) > 256:
        return None
    session = db.get(AuthSession, token_hash(raw))
    if session is None or session.revoked_at is not None:
        return None
    expiry = session.expires_at
    # SQLite utilizado apenas em testes retorna datetimes sem tzinfo.
    if expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=timezone.utc)
    return session if expiry > utcnow() else None


def require_login(request: Request, db: Session = Depends(get_db)) -> None:
    if find_session(request, db) is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Faça login para acessar seus estudos.")
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        raw = request.cookies[cookie_name()]
        supplied = request.headers.get("X-CSRF-Token", "")
        if len(supplied) != 64 or not supplied.isascii() or not hmac.compare_digest(supplied, csrf_token(raw)):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Token CSRF ausente ou inválido.")


def _client_id(request: Request) -> str:
    # Nunca confie em X-Forwarded-For fornecido pelo próprio cliente.
    return request.client.host if request.client else "unknown"


def _rate_limited(client: str) -> bool:
    import time
    now = time.monotonic()
    with _failures_lock:
        events = _failures[client]
        while events and events[0] < now - FAILURE_WINDOW:
            events.popleft()
        return len(events) >= FAILURE_LIMIT


def _register_failure(client: str) -> None:
    import time
    with _failures_lock:
        _failures[client].append(time.monotonic())


def _clear_failures(client: str) -> None:
    with _failures_lock:
        _failures.pop(client, None)


def _set_cookie(response: Response, raw: str) -> None:
    response.set_cookie(
        key=cookie_name(), value=raw, max_age=COOKIE_MAX_AGE,
        secure=is_production(), httponly=True, samesite="strict", path="/",
    )


@router.post("/login")
def login(payload: LoginIn, response: Response, request: Request, db: Session = Depends(get_db)):
    client = _client_id(request)
    if _rate_limited(client):
        raise HTTPException(429, "Muitas tentativas. Tente novamente em até 15 minutos.")
    username_ok = hmac.compare_digest(payload.username.encode("utf-8"),
                                      os.environ["ADMIN_USERNAME"].encode("utf-8"))
    try:
        password_ok = _hasher.verify(os.environ["ADMIN_PASSWORD_HASH"], payload.password)
    except (InvalidHashError, VerificationError, ValueError):
        password_ok = False
    if not username_ok or not password_ok:
        _register_failure(client)
        raise HTTPException(401, "Usuário ou senha incorretos.")
    _clear_failures(client)
    raw = secrets.token_urlsafe(32)
    now = utcnow()
    db.add(AuthSession(token_digest=token_hash(raw), created_at=now,
                       expires_at=now + timedelta(seconds=COOKIE_MAX_AGE)))
    db.commit()
    _set_cookie(response, raw)
    response.headers["Cache-Control"] = "no-store"
    return {"authenticated": True, "csrf_token": csrf_token(raw), "username": os.environ["ADMIN_USERNAME"]}


@router.get("/me")
def me(request: Request, db: Session = Depends(get_db)):
    if find_session(request, db) is None:
        raise HTTPException(401, "Sessão não autenticada.")
    return {"authenticated": True, "csrf_token": csrf_token(request.cookies[cookie_name()]),
            "username": os.environ["ADMIN_USERNAME"]}


@router.post("/logout", dependencies=[Depends(require_login)])
def logout(response: Response, request: Request, db: Session = Depends(get_db)):
    session = find_session(request, db)
    if session:
        session.revoked_at = utcnow()
        db.commit()
    response.delete_cookie(cookie_name(), path="/", secure=is_production(), httponly=True, samesite="strict")
    response.headers["Cache-Control"] = "no-store"
    return {"authenticated": False}


def main() -> None:
    if sys.argv[1:] != ["hash-password"]:
        print("Uso: python -m app.auth hash-password")
        raise SystemExit(2)
    first = getpass("Nova senha (mínimo 12 caracteres): ")
    second = getpass("Repita a senha: ")
    if first != second or len(first) < 12:
        raise SystemExit("As senhas devem coincidir e ter pelo menos 12 caracteres.")
    print("ADMIN_PASSWORD_HASH=" + _hasher.hash(first))
    print("Copie apenas para o .env local ou o painel privado do Render; nunca para o GitHub.")


if __name__ == "__main__":
    main()
