from datetime import timedelta

from sqlalchemy import select

from app.db import get_db
from app.models import AuthSession, utcnow


def test_anonymous_cannot_access_sensitive_apis(anon_client):
    assert anon_client.get('/').status_code == 200  # segue redirecionamento para login
    assert 'loginForm' in anon_client.get('/login').text
    assert anon_client.get('/api/subjects').status_code == 401
    assert anon_client.get('/api/dashboard').status_code == 401
    assert anon_client.get('/api/queue').status_code == 401
    assert anon_client.post('/api/subjects', json={'name': 'Teste'}).status_code == 401
    assert anon_client.get('/api/auth/me').status_code == 401
    assert anon_client.get('/api/health').json()['status'] == 'ok'


def test_login_and_csrf_protection(anon_client):
    assert anon_client.post('/api/auth/login', json={'username':'estudante','password':'errada'}).status_code == 401
    result=anon_client.post('/api/auth/login', json={'username':'estudante','password':'SenhaForteDeTeste!'})
    assert result.status_code == 200
    assert result.cookies.get('estudo_session')
    assert result.cookies['estudo_session'] != 'SenhaForteDeTeste!'
    assert 'HttpOnly' in result.headers['set-cookie']
    assert 'SameSite=strict' in result.headers['set-cookie']
    assert anon_client.get('/api/auth/me').status_code == 200
    assert anon_client.get('/api/subjects').status_code == 200
    assert anon_client.post('/api/subjects', json={'name':'Português'}).status_code == 403
    assert anon_client.post('/api/subjects', json={'name':'Português'}, headers={'X-CSRF-Token':'invalido'}).status_code == 403
    csrf=result.json()['csrf_token']
    assert anon_client.post('/api/subjects', json={'name':'Português'}, headers={'X-CSRF-Token':csrf}).status_code == 201
    assert anon_client.post('/api/auth/logout', headers={'X-CSRF-Token':csrf}).status_code == 200
    assert anon_client.get('/api/dashboard').status_code == 401


def test_stale_session_denied(client):
    get_session=client.app.dependency_overrides[get_db]
    with next(get_session()) as db:
        session=db.scalars(select(AuthSession)).first()
        session.expires_at=utcnow()-timedelta(days=1)
        db.commit()
    assert client.get('/api/dashboard').status_code == 401


def test_headers_and_login_page(anon_client):
    response=anon_client.get('/login')
    assert response.headers['x-frame-options'] == 'DENY'
    assert "frame-ancestors 'none'" in response.headers['content-security-policy']
    assert response.headers['cache-control'] == 'no-store'


def test_expired_or_forged_cookie_denied(anon_client):
    anon_client.cookies.set('estudo_session', 'token-forjado')
    assert anon_client.get('/api/subjects').status_code == 401
