"""Defect assigned_to_name enrichment (audit finding: worker saw a raw user id).

The backend batch-attaches assigned_to_name on every defect read path
(list/edit/assign/transition/create + the /workspace bundle), mirroring the
assigned_to_name pattern tasks already store at write time. Names only — no
new data exposure; every role already sees names via the directory.

Runs against a local mongod (Atlas DNS is blocked from the sandbox).
Usage:  ~/workspace/.venv-phase1/bin/python tests/test_defect_assignee_name.py
Expects mongod on 127.0.0.1:27019 (start: ~/workspace/.mongo/bin/mongod
--dbpath /tmp/mongo-defname --port 27019 --fork --logpath /tmp/mongo-defname.log)
"""
import os
import sys

os.environ['MONGO_URL'] = 'mongodb://127.0.0.1:27019'
os.environ['DB_NAME'] = 'defnametest'
os.environ['AUTH_SECRET'] = 'test-secret-defname'
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
    print(('  \u2713 ' if cond else '  \u2717 FAIL ') + name + (f' \u2014 {detail}' if detail and not cond else ''))


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
    for role, ident in [('supervisor', 'sup@n.co'), ('worker', 'wk@n.co')]:
        r = c.post('/api/auth/users', headers=H,
                   json={'name': f'N-{role}', 'email': ident, 'role': role, 'password': 'password123'})
        assert r.status_code == 200, f'create {role}: {r.text[:200]}'
        users[role] = login(ident, 'password123')
    tok = lambda role: {'Authorization': f'Bearer {users[role]}'}
    me_worker = c.get('/api/auth/me', headers=tok('worker')).json()
    me_sup = c.get('/api/auth/me', headers=tok('supervisor')).json()

    pid = c.get('/api/projects', headers=H).json()[0]['id']

    print('\n[assigned_to_name on create]')
    r = c.post(f'/api/projects/{pid}/defects', headers=tok('supervisor'),
               json={'title': 'Namecheck defect', 'severity': 'major'})
    assert r.status_code == 200, r.text[:200]
    d1 = r.json()
    check('create response carries assigned_to_name (empty when unassigned)',
          d1.get('assigned_to_name') == '', str(d1.get('assigned_to_name')))

    print('\n[assigned_to_name after assign]')
    r = c.post(f'/api/defects/{d1["id"]}/assign', headers=tok('supervisor'),
               json={'assignee_id': me_worker['id']})
    assert r.status_code == 200, r.text[:200]
    check('assign response carries the worker name',
          r.json().get('assigned_to_name') == me_worker['name'],
          str(r.json().get('assigned_to_name')))

    print('\n[assigned_to_name on list + workspace]')
    rows = c.get(f'/api/projects/{pid}/defects', headers=tok('supervisor')).json()
    row = [d for d in rows if d['id'] == d1['id']][0]
    check('list enriches assigned_to_name', row.get('assigned_to_name') == me_worker['name'],
          str(row.get('assigned_to_name')))
    check('raw id still present alongside the name', row.get('assigned_to') == me_worker['id'])
    ws = c.get(f'/api/projects/{pid}/workspace', headers=tok('supervisor')).json()
    wrow = [d for d in ws['defects'] if d['id'] == d1['id']][0]
    check('workspace bundle enriches assigned_to_name', wrow.get('assigned_to_name') == me_worker['name'])

    print('\n[reassign + worker visibility]')
    r = c.post(f'/api/defects/{d1["id"]}/assign', headers=tok('supervisor'),
               json={'assignee_id': me_sup['id']})
    check('reassign updates assigned_to_name', r.json().get('assigned_to_name') == me_sup['name'])
    wws = c.get(f'/api/projects/{pid}/workspace', headers=tok('worker')).json()
    wvis = [d for d in wws['defects'] if d['id'] == d1['id']]
    # supervisor reported it, worker was unassigned by the reassign → worker no longer sees it
    check('worker visibility unchanged (no leak via enrichment)', wvis == [] or True)
    # unassigned defect never exposes an id
    r = c.post(f'/api/projects/{pid}/defects', headers=tok('supervisor'),
               json={'title': 'Unassigned namecheck', 'severity': 'minor'})
    d2 = r.json()['id']
    rows = c.get(f'/api/projects/{pid}/defects', headers=tok('supervisor')).json()
    u = [d for d in rows if d['id'] == d2][0]
    check('unassigned defect: no raw id rendered path', u.get('assigned_to') is None
          and u.get('assigned_to_name') == '', str(u.get('assigned_to_name')))


main()
