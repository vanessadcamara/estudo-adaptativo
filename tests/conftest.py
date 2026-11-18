import pytest
from argon2 import PasswordHasher
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app import models  # noqa: F401
from app.db import Base, get_db
from app.main import app


@pytest.fixture
def anon_client(monkeypatch):
    monkeypatch.setenv('APP_ENV', 'test')
    monkeypatch.setenv('APP_SECRET_KEY', 'chave_super_longa_apenas_para_testes_123456789012345')
    monkeypatch.setenv('ADMIN_USERNAME', 'estudante')
    monkeypatch.setenv('ADMIN_PASSWORD_HASH', PasswordHasher(time_cost=1, memory_cost=8192).hash('SenhaForteDeTeste!'))
    engine = create_engine('sqlite+pysqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)

    def override_db():
        with Session(engine) as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    engine.dispose()


@pytest.fixture
def client(anon_client):
    response = anon_client.post('/api/auth/login', json={'username': 'estudante', 'password': 'SenhaForteDeTeste!'})
    assert response.status_code == 200, response.text
    anon_client.headers.update({'X-CSRF-Token': response.json()['csrf_token']})
    return anon_client
