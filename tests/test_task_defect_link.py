"""Task-Defect linking integration tests.

Runs against a local mongod (Atlas DNS is blocked from the sandbox).
Usage:  ~/workspace/.venv-phase1/bin/python tests/test_task_defect_link.py
Expects mongod on 127.0.0.1:27019 (start: ~/workspace/.mongo/bin/mongod
--dbpath /tmp/mongo-link --port 27019 --fork --logpath /tmp/mongo-link.log)
"""
import os
import sys

os.environ['MONGO_URL'] = 'mongodb://127.0.0.1:27019'
os.environ['DB_NAME'] = 'linktest'
os.environ['AUTH_SECRET'] = 'test-secret-link'
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
    for role, ident in [('engineer', 'eng@l.co'), ('supervisor', 'sup@l.co'),
                        ('worker', 'wk@l.co'), ('viewer', 'vw@l.co')]:
        r = c.post('/api/auth/users', headers=H,
                   json={'name': f'L-{role}', 'email': ident, 'role': role, 'password': 'password123'})
        assert r.status_code == 200, f'create {role}: {r.text[:200]}'
        users[role] = login(ident, 'password123')
    tok = lambda role: {'Authorization': f'Bearer {users[role]}'}
    w2 = c.post('/api/auth/users', headers=H,
                json={'name': 'L-worker2', 'email': 'wk2@l.co', 'role': 'worker', 'password': 'password123'})
    assert w2.status_code == 200
    worker2 = login('wk2@l.co', 'password123')
    T2 = {'Authorization': f'Bearer {worker2}'}

    pid = c.get('/api/projects', headers=H).json()[0]['id']
    me_worker = c.get('/api/auth/me', headers=tok('worker')).json()
    me_sup = c.get('/api/auth/me', headers=tok('supervisor')).json()

    print('\n[link setup]')
    r = c.post(f'/api/projects/{pid}/defects', headers=tok('supervisor'),
               json={'title': 'Loose conduit in riser', 'severity': 'major'})
    assert r.status_code == 200, r.text[:200]
    d1 = r.json()['id']
    # foreign-project defect (inserted directly)
    SYNC[os.environ['DB_NAME']].defects.insert_one(
        {'id': 'foreign-defect', 'project_id': 'other-project', 'title': 'x',
         'status': 'open', 'severity': 'minor', 'category': 'other'})

    print('\n[create with defect_id]')
    r = c.post(f'/api/projects/{pid}/tasks', headers=tok('supervisor'),
               json={'title': 'Order gang boxes', 'assigned_to': me_worker['id'],
                     'defect_id': d1})
    check('create task with valid defect_id', r.status_code == 200, r.text[:160])
    t1 = r.json()
    check('linked + embedded defect summary',
          t1.get('defect_id') == d1 and t1.get('defect', {}).get('title') == 'Loose conduit in riser'
          and t1['defect']['severity'] == 'major', str(t1.get('defect')))
    r = c.post(f'/api/projects/{pid}/tasks', headers=tok('supervisor'),
               json={'title': 'Bad link', 'assigned_to': me_worker['id'], 'defect_id': 'nope'})
    check('invalid defect_id -> 400', r.status_code == 400, r.text[:120])
    r = c.post(f'/api/projects/{pid}/tasks', headers=tok('supervisor'),
               json={'title': 'Foreign link', 'assigned_to': me_worker['id'], 'defect_id': 'foreign-defect'})
    check('cross-project defect_id -> 400', r.status_code == 400, r.text[:120])
    r = c.post(f'/api/projects/{pid}/tasks', headers=tok('worker'),
               json={'title': 'Worker task', 'assigned_to': me_worker['id']})
    check('worker cannot create tasks', r.status_code == 403)

    print('\n[follow-up endpoint]')
    r = c.post(f'/api/defects/{d1}/tasks', headers=tok('supervisor'),
               json={'title': 'Rectify conduit', 'assigned_to': me_worker['id'], 'priority': 'high'})
    check('POST /defects/{id}/tasks creates', r.status_code == 200, r.text[:160])
    t2 = r.json()
    check('follow-up has defect project_id + link',
          t2['project_id'] == pid and t2['defect_id'] == d1 and t2['defect']['id'] == d1)
    r = c.get('/api/notifications?unread_only=true', headers=tok('worker'))
    check('assignee got task_assigned notification',
          any(n['kind'] == 'task_assigned' and t2['id'] in str(n.get('link', {})) for n in r.json()))
    r = c.post(f'/api/defects/{d1}/tasks', headers=tok('supervisor'),
               json={'title': 'Unassigned follow-up'})
    check('follow-up without assignee works', r.status_code == 200 and r.json()['assigned_to'] is None,
          r.text[:160])
    t3 = r.json()['id']
    r = c.post(f'/api/defects/{d1}/tasks', headers=tok('worker'), json={'title': 'no'})
    check('worker cannot use follow-up endpoint', r.status_code == 403)
    r = c.post(f'/api/defects/{d1}/tasks', headers=tok('viewer'), json={'title': 'no'})
    check('viewer cannot use follow-up endpoint', r.status_code == 403)
    r = c.post('/api/defects/nope/tasks', headers=tok('supervisor'), json={'title': 'no'})
    check('follow-up on missing defect -> 404', r.status_code == 404)

    print('\n[list linked]')
    r = c.get(f'/api/defects/{d1}/tasks', headers=tok('supervisor'))
    got = r.json()
    check('GET returns exactly the linked tasks',
          r.status_code == 200 and {t['id'] for t in got} == {t1['id'], t2['id'], t3}, str([t['id'] for t in got]))
    check('linked list embeds defect summaries', all(t.get('defect', {}).get('id') == d1 for t in got))
    r = c.get(f'/api/defects/{d1}/tasks', headers=tok('viewer'))
    check('viewer can list linked tasks', r.status_code == 200)

    print('\n[patch link/unlink]')
    r = c.patch(f'/api/tasks/{t1["id"]}', headers=tok('supervisor'), json={'defect_id': None})
    check('unlink via PATCH', r.status_code == 200 and r.json().get('defect_id') is None
          and r.json().get('defect') is None, r.text[:160])
    r = c.patch(f'/api/tasks/{t1["id"]}', headers=tok('supervisor'), json={'defect_id': d1})
    check('re-link via PATCH', r.status_code == 200 and r.json().get('defect_id') == d1
          and r.json()['defect']['title'] == 'Loose conduit in riser')
    r = c.patch(f'/api/tasks/{t1["id"]}', headers=tok('supervisor'), json={'defect_id': 'nope'})
    check('PATCH invalid defect_id -> 400', r.status_code == 400)

    print('\n[worker visibility]')
    r = c.get(f'/api/projects/{pid}/tasks', headers=tok('worker'))
    mine = r.json()
    check('worker sees own linked tasks with defect chip data',
          any(t['id'] == t2['id'] and t.get('defect', {}).get('id') == d1 for t in mine),
          str([(t['id'], t.get('defect_id')) for t in mine]))
    check('worker does not see unassigned task', all(t['id'] != t3 for t in mine))
    r = c.get(f'/api/projects/{pid}/tasks', headers=T2)
    check('other worker sees none', r.json() == [])
    # assign defect to worker -> appears in their defect list ("My work" source)
    r = c.post(f'/api/defects/{d1}/assign', headers=tok('supervisor'),
               json={'assignee_id': me_worker['id']})
    assert r.status_code == 200, r.text[:160]
    r = c.get(f'/api/projects/{pid}/defects?assigned_to=me', headers=tok('worker'))
    check('worker sees assigned defect', any(d['id'] == d1 for d in r.json()))
    r = c.get(f'/api/defects/{d1}/tasks', headers=T2)
    check('unrelated worker cannot list defect tasks', r.status_code == 403)


if __name__ == '__main__':
    main()
