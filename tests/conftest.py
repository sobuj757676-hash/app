"""pytest fixtures for the VoltCraft backend suite.

Env is set BEFORE the api package is imported; a dedicated database is
dropped once per run; the FastAPI app boots once (session scope).

Requires mongod on 127.0.0.1:27019:
  ~/workspace/.mongo/bin/mongod --dbpath /tmp/mongo-pytest --port 27019 \
      --fork --logpath /tmp/mongo-pytest.log
Run:  ~/workspace/.venv-phase1/bin/python -m pytest tests/test_daily_work_stages.py -x -q
"""
import os
import sys

os.environ.setdefault('MONGO_URL', 'mongodb://127.0.0.1:27019')
os.environ['DB_NAME'] = 'voltcraft-pytest'
os.environ['AUTH_SECRET'] = 'pytest-secret-key'
os.environ['CORS_ORIGINS'] = '*'
os.environ.pop('BLOB_READ_WRITE_TOKEN', None)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'api'))

import pytest  # noqa: E402
from pymongo import MongoClient  # noqa: E402

SYNC = MongoClient(os.environ['MONGO_URL'])
SYNC.drop_database(os.environ['DB_NAME'])

import index  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

DB = SYNC[os.environ['DB_NAME']]


def _login(client, identifier, password):
    r = client.post('/api/auth/login', json={'identifier': identifier, 'password': password})
    assert r.status_code == 200, f'login failed for {identifier}: {r.text[:200]}'
    return {'Authorization': f"Bearer {r.json()['token']}"}


@pytest.fixture(scope='session')
def client():
    with TestClient(index.app, raise_server_exceptions=False) as c:
        yield c


@pytest.fixture(scope='session')
def admin(client):
    return _login(client, 'admin@voltcraft.local', 'changeme123')


@pytest.fixture(scope='session')
def users(client, admin):
    """One user per role. Returns dict role -> headers (worker2 = second worker)."""
    specs = [('engineer', 'py-eng@l.co'), ('supervisor', 'py-sup@l.co'),
             ('worker', 'py-wk@l.co'), ('worker', 'py-wk2@l.co'),
             ('worker', 'py-wk3@l.co'), ('viewer', 'py-vw@l.co')]
    out = {}
    for i, (role, ident) in enumerate(specs):
        r = client.post('/api/auth/users', headers=admin,
                        json={'name': f'PY {role} {i}', 'email': ident,
                              'role': role, 'password': 'password123'})
        assert r.status_code == 200, f'create {role}: {r.text[:200]}'
        out.setdefault(role, []).append(_login(client, ident, 'password123'))
    return {'engineer': out['engineer'][0],
            'supervisor': out['supervisor'][0],
            'worker': out['worker'][0],
            'worker2': out['worker'][1],
            'worker3': out['worker'][2],
            'viewer': out['viewer'][0]}


@pytest.fixture(scope='session')
def me(client, users):
    """user_id per token, resolved via /auth/me."""
    return {role: client.get('/api/auth/me', headers=headers).json()['id']
            for role, headers in users.items()}


@pytest.fixture(scope='session')
def pid(client, admin):
    return client.get('/api/projects', headers=admin).json()[0]['id']
