"""Regression tests for browser-found linking bugs:
1. Workspace bundle must embed defect summaries on linked tasks
   (Tasks board + worker My work read from /workspace, not /tasks).
2. (Frontend) DefectDrawer TaskModal dead-code fix is covered by the
   CI=true craco production build.

Runs against a local mongod (Atlas DNS is blocked from the sandbox).
Usage:  ~/workspace/.venv-phase1/bin/python tests/test_link_fixes.py
Expects mongod on 127.0.0.1:27019 (start: ~/workspace/.mongo/bin/mongod
--dbpath /tmp/mongo-link --port 27019 --fork --logpath /tmp/mongo-link.log)
"""
import os
import sys

os.environ['MONGO_URL'] = 'mongodb://127.0.0.1:27019'
os.environ['DB_NAME'] = 'linkfix'
os.environ['AUTH_SECRET'] = 'test-secret-linkfix'
os.environ['CORS_ORIGINS'] = '*'
os.environ.pop('BLOB_READ_WRITE_TOKEN', None)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'api'))

from pymongo import MongoClient  # noqa: E402

SYNC = MongoClient(os.environ['MONGO_URL'])
SYNC.drop_database(os.environ['DB_NAME'])

import index  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

PASS, FAIL = [], []


def check(name, cond, detail=''):
    (PASS if cond else FAIL).append(name)
    print(('  ✓ ' if cond else '  ✗ FAIL ') + name + (f' — {detail}' if detail and not cond else ''))


def main():
    with TestClient(index.app, raise_server_exceptions=False) as c:
        run(c)
    print(f'\n{len(PASS)} passed, {len(FAIL)} failed')
    sys.exit(1 if FAIL else 0)


def run(c):
    def login(identifier, password):
        r = c.post('/api/auth/login', json={'identifier': identifier, 'password': password})
        assert r.status_code == 200, f'login failed for {identifier}: {r.text[:200]}'
        return r.json()['token']

    admin = login('admin@voltcraft.local', 'changeme123')
    H = {'Authorization': f'Bearer {admin}'}
    users = {}
    for role, ident in [('supervisor', 'sup@l.co'), ('worker', 'wk@l.co')]:
        r = c.post('/api/auth/users', headers=H,
                   json={'name': f'F-{role}', 'email': ident, 'role': role, 'password': 'password123'})
        assert r.status_code == 200, f'create {role}: {r.text[:200]}'
        users[role] = login(ident, 'password123')
    tok = lambda role: {'Authorization': f'Bearer {users[role]}'}
    me_worker = c.get('/api/auth/me', headers=tok('worker')).json()

    pid = c.get('/api/projects', headers=H).json()[0]['id']

    print('\n[workspace embeds defect on linked tasks]')
    r = c.post(f'/api/projects/{pid}/defects', headers=tok('supervisor'),
               json={'title': 'Fixreg defect', 'severity': 'critical'})
    assert r.status_code == 200, r.text[:200]
    d1 = r.json()['id']
    r = c.post(f'/api/projects/{pid}/tasks', headers=tok('supervisor'),
               json={'title': 'Fixreg linked task', 'assigned_to': me_worker['id'], 'defect_id': d1})
    assert r.status_code == 200, r.text[:200]
    t1 = r.json()['id']
    r = c.post(f'/api/projects/{pid}/tasks', headers=tok('supervisor'),
               json={'title': 'Fixreg plain task', 'assigned_to': me_worker['id']})
    assert r.status_code == 200, r.text[:200]

    ws = c.get(f'/api/projects/{pid}/workspace', headers=tok('supervisor')).json()
    by_id = {t['id']: t for t in ws['tasks']}
    check('workspace task carries embedded defect summary',
          by_id[t1].get('defect', {}).get('title') == 'Fixreg defect'
          and by_id[t1]['defect']['severity'] == 'critical'
          and by_id[t1]['defect']['id'] == d1,
          str(by_id[t1].get('defect')))
    plain = [t for t in ws['tasks'] if t['title'] == 'Fixreg plain task'][0]
    check('unlinked task has defect None', plain.get('defect') is None, str(plain.get('defect')))

    print('\n[worker workspace view]')
    ws_w = c.get(f'/api/projects/{pid}/workspace', headers=tok('worker')).json()
    wt = [t for t in ws_w['tasks'] if t['id'] == t1]
    check('worker sees own linked task with defect chip data',
          len(wt) == 1 and wt[0].get('defect', {}).get('id') == d1,
          str(wt[0].get('defect') if wt else 'missing'))


main()
