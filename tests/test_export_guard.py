"""Export CSV cost-visibility guard (audit finding #8).

Supervisors are blocked from the /expenses page (RequireAuth in App.js) and must
likewise be blocked from the expenses CSV export on /reports; workers were
already blocked server-side. Engineers/viewers/admin/manager behavior is
unchanged.

Runs against a local mongod (Atlas DNS is blocked from the sandbox).
Usage:  ~/workspace/.venv-phase1/bin/python tests/test_export_guard.py
Expects mongod on 127.0.0.1:27019 (start: ~/workspace/.mongo/bin/mongod
--dbpath /tmp/mongo-phase2 --port 27019 --fork --logpath /tmp/mongo-phase2.log)
"""
import os
import sys

os.environ['MONGO_URL'] = 'mongodb://127.0.0.1:27019'
os.environ['DB_NAME'] = 'exportguardtest'
os.environ['AUTH_SECRET'] = 'test-secret-exportguard'
os.environ['CORS_ORIGINS'] = '*'
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'api'))

from pymongo import MongoClient  # noqa: E402  (sync client: setup only, no loop issues)

SYNC = MongoClient(os.environ['MONGO_URL'])
SYNC.drop_database(os.environ['DB_NAME'])

import index  # noqa: E402  (builds its own motor client + fake `server` module)
from fastapi.testclient import TestClient  # noqa: E402

PASS, FAIL = [], []


def check(name, cond, detail=''):
    (PASS if cond else FAIL).append(name)
    print(('  \u2713 ' if cond else '  \u2717 FAIL ') + name + (f' \u2014 {detail}' if detail and not cond else ''))


def main():
    # Context-manager form: one shared event loop for all requests
    # (motor binds to the first loop it sees).
    with TestClient(index.app, raise_server_exceptions=False) as c:
        r = c.post('/api/auth/login', json={'identifier': 'admin@voltcraft.local', 'password': 'changeme123'})
        assert r.status_code == 200, f'admin login: {r.text[:200]}'
        admin = r.json()['token']
        H = {'Authorization': f'Bearer {admin}'}
        users = {}
        for role, ident in [('manager', 'mgr@t.co'), ('engineer', 'eng@t.co'),
                            ('supervisor', 'sup@t.co'), ('worker', 'wk@t.co'),
                            ('viewer', 'vw@t.co')]:
            r = c.post('/api/auth/users', headers=H,
                       json={'name': f'T-{role}', 'email': ident, 'role': role, 'password': 'password123'})
            assert r.status_code == 200, f'create {role}: {r.text[:200]}'
            r = c.post('/api/auth/login', json={'identifier': ident, 'password': 'password123'})
            assert r.status_code == 200, f'login {role}: {r.text[:200]}'
            users[role] = r.json()['token']
        tok = lambda role: {'Authorization': f'Bearer {users[role]}'}  # noqa: E731
        pid = c.get('/api/projects', headers=H).json()[0]['id']

        r = c.get(f'/api/projects/{pid}/export/expenses', headers=tok('supervisor'))
        check('supervisor expenses export -> 403', r.status_code == 403, f'got {r.status_code}: {r.text[:120]}')
        r = c.get(f'/api/projects/{pid}/export/expenses', headers=tok('worker'))
        check('worker expenses export -> 403 (unchanged)', r.status_code == 403, f'got {r.status_code}: {r.text[:120]}')
        for role, hdr in (('admin', H), ('manager', tok('manager'))):
            r = c.get(f'/api/projects/{pid}/export/expenses', headers=hdr)
            ok = r.status_code == 200 and r.text.lstrip('\ufeff').startswith('date,description,category,amount,block,reference')
            check(f'{role} expenses export -> 200 with CSV header', ok, f'got {r.status_code}: {r.text[:120]}')
        r = c.get(f'/api/projects/{pid}/export/engineer', headers=tok('engineer'))
        check('unknown kind still 400 for engineer', r.status_code == 400, f'got {r.status_code}')
        r = c.get(f'/api/projects/{pid}/export/units', headers=tok('supervisor'))
        check('supervisor units export still 200', r.status_code == 200, f'got {r.status_code}: {r.text[:120]}')

    print(f'\n{len(PASS)} passed, {len(FAIL)} failed')
    return 1 if FAIL else 0


if __name__ == '__main__':
    sys.exit(main())
