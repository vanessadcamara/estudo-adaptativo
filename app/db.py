"""Conexão com o PostgreSQL via variável de ambiente (sem credenciais no código)."""
import os
from functools import lru_cache
from typing import Iterator

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

load_dotenv()


class Base(DeclarativeBase):
    pass


def database_url() -> str:
    value = os.getenv("DATABASE_URL")
    if not value:
        raise RuntimeError("Configure DATABASE_URL no seu arquivo .env antes de iniciar.")
    # Neon retorna URLs postgres:// ou postgresql://: selecionar o driver psycopg 3.
    if value.startswith("postgres://"):
        value = "postgresql+psycopg://" + value[len("postgres://"):]
    elif value.startswith("postgresql://"):
        value = "postgresql+psycopg://" + value[len("postgresql://"):]
    return value


@lru_cache(maxsize=1)
def session_factory() -> sessionmaker[Session]:
    engine = create_engine(database_url(), pool_pre_ping=True, pool_size=2, max_overflow=3, pool_recycle=1800)
    return sessionmaker(bind=engine, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    with session_factory()() as db:
        yield db
