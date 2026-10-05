"""Block rename/delete endpoints (audit finding: no way to rename or delete a block).

PATCH /projects/{pid}/blocks/{bid} renames a block (admin/manager only) and
cascades the denormalized block name on units/defects/inspections/tests.
DELETE refuses with 409 while the block still has units (no cascade data loss).

Runs against a local mongod (Atlas DNS is blocked from the sandbox).
Usage:  ~/workspace/.venv-phase1/bin/python tests/test_block_rename_delete.py
Expects mongod on 127.0.0.1:27019 (start: ~/workspace/.mongo/bin/mongod
--dbpath /tmp/mongo-phase2 --port 27019 --fork --logpath /tmp/mongo-phase2.log)
"""
import os
import sys

os.environ['MONGO_URL'] = 'mongodb://127.0.0.1:27019'
os.environ['DB_NAME'] = 'blockrenametest'
os.environ['AUTH_SECRET'] = 'test-secret-blockrename'
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
        r = c.post('/api/auth/users', headers=H,
                   json={'name': 'W-orker', 'email': 'blk@t.co', 'role': 'worker', 'password': 'password123'})
        assert r.status_code == 200, f'create worker: {r.text[:200]}'
        r = c.post('/api/auth/login', json={'identifier': 'blk@t.co', 'password': 'password123'})
        assert r.status_code == 200, f'worker login: {r.text[:200]}'
        W = {'Authorization': f'Bearer {r.json()["token"]}'}

        pid = c.get('/api/projects', headers=H).json()[0]['id']

        def make_block(name, room_mix=None):
            body = {'name': name, 'levels': 2, 'first_unit': 401}
            body['room_mix'] = room_mix or [{'room_type': '4-room', 'count': 1}]
            r = c.post(f'/api/projects/{pid}/blocks', headers=H, json=body)
            assert r.status_code == 200, f'create block {name}: {r.text[:200]}'
            return r.json()['id']

        bid = make_block('77A')
        ws = c.get(f'/api/projects/{pid}/workspace', headers=H).json()
        units = [u for u in ws['units'] if u['block_id'] == bid]
        check('block created with units', len(units) == 2, f'got {len(units)}')

        # --- rename ---
        r = c.patch(f'/api/projects/{pid}/blocks/{bid}', headers=H, json={'name': '77b'})
        check('admin rename -> 200 and uppercased', r.status_code == 200 and r.json()['name'] == '77B',
              f'got {r.status_code}: {r.text[:120]}')
        ws = c.get(f'/api/projects/{pid}/workspace', headers=H).json()
        renamed = [u for u in ws['units'] if u['block_id'] == bid]
        check('rename cascades to unit block names', all(u['block'] == '77B' for u in renamed),
              f'{[u["block"] for u in renamed]}')

        bid2 = make_block('78A')
        r = c.patch(f'/api/projects/{pid}/blocks/{bid}', headers=H, json={'name': '78A'})
        check('rename to existing name -> 409', r.status_code == 409, f'got {r.status_code}: {r.text[:120]}')

        r = c.patch(f'/api/projects/{pid}/blocks/{bid}', headers=W, json={'name': '79A'})
        check('worker rename -> 403 (RBAC unchanged)', r.status_code == 403, f'got {r.status_code}')

        r = c.patch(f'/api/projects/{pid}/blocks/nope', headers=H, json={'name': '79A'})
        check('rename unknown block -> 404', r.status_code == 404, f'got {r.status_code}')

        # --- delete ---
        r = c.delete(f'/api/projects/{pid}/blocks/{bid}', headers=H)
        check('delete block with units -> 409 (no cascade data loss)',
              r.status_code == 409 and 'units' in r.text, f'got {r.status_code}: {r.text[:120]}')

        r = c.delete(f'/api/projects/{pid}/blocks/{bid2}', headers=W)
        check('worker delete -> 403 (RBAC unchanged)', r.status_code == 403, f'got {r.status_code}')

        # Remove units directly, then delete must succeed.
        SYNC[os.environ['DB_NAME']].units.delete_many({'block_id': bid2})
        r = c.delete(f'/api/projects/{pid}/blocks/{bid2}', headers=H)
        ok = r.status_code == 200 and r.json().get('deleted') is True
        check('delete empty block -> 200', ok, f'got {r.status_code}: {r.text[:120]}')
        ws = c.get(f'/api/projects/{pid}/workspace', headers=H).json()
        check('block gone from workspace', all(b['id'] != bid2 for b in ws['blocks']))

        r = c.delete(f'/api/projects/{pid}/blocks/nope', headers=H)
        check('delete unknown block -> 404', r.status_code == 404, f'got {r.status_code}')

    print(f'\n{len(PASS)} passed, {len(FAIL)} failed')
    return 1 if FAIL else 0


if __name__ == '__main__':
    sys.exit(main())
