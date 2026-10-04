"""Room mix builder + point templates integration tests.

Runs against a local mongod (Atlas DNS is blocked from the sandbox).
Usage:  ~/workspace/.venv-phase1/bin/python tests/test_room_mix_templates.py
Expects mongod on 127.0.0.1:27019 (start: ~/workspace/.mongo/bin/mongod
--dbpath /tmp/mongo-link --port 27019 --fork --logpath /tmp/mongo-link.log)
"""
import os
import sys

os.environ['MONGO_URL'] = 'mongodb://127.0.0.1:27019'
os.environ['DB_NAME'] = 'roommix'
os.environ['AUTH_SECRET'] = 'test-secret-roommix'
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


def kind_counts(points):
    d = {}
    for p in points:
        d[p['kind']] = d.get(p['kind'], 0) + 1
    return d


def run(c):
    def login(identifier, password):
        r = c.post('/api/auth/login', json={'identifier': identifier, 'password': password})
        assert r.status_code == 200, f'login failed for {identifier}: {r.text[:200]}'
        return r.json()['token']

    admin = login('admin@voltcraft.local', 'changeme123')
    H = {'Authorization': f'Bearer {admin}'}
    users = {}
    for role, ident in [('manager', 'mgr@l.co'), ('engineer', 'eng@l.co'), ('worker', 'wk@l.co')]:
        r = c.post('/api/auth/users', headers=H,
                   json={'name': f'R-{role}', 'email': ident, 'role': role, 'password': 'password123'})
        assert r.status_code == 200, f'create {role}: {r.text[:200]}'
        users[role] = login(ident, 'password123')
    tok = lambda role: {'Authorization': f'Bearer {users[role]}'}

    pid = c.get('/api/projects', headers=H).json()[0]['id']

    print('\n[block creation with room_mix]')
    mix = [{'room_type': '4-room', 'count': 4}, {'room_type': '2-room', 'count': 3}, {'room_type': '3-room', 'count': 2}]
    r = c.post(f'/api/projects/{pid}/blocks', headers=tok('manager'),
               json={'name': 'MIX1', 'levels': 2, 'first_unit': 401, 'units_per_level': 9, 'room_mix': mix})
    check('create block with mix -> 200', r.status_code == 200, r.text[:160])
    units = sorted(SYNC[os.environ['DB_NAME']].units.find(
        {'project_id': pid, 'block': 'MIX1'}, {'_id': 0}),
        key=lambda u: (u['level'], u['number']))
    check('unit count = levels x total', len(units) == 18, f'got {len(units)}')
    lvl1 = [u for u in units if u['level'] == 1]
    got_types = [u['unit_type'] for u in lvl1]
    want_types = ['4-room'] * 4 + ['2-room'] * 3 + ['3-room'] * 2
    check('unit_types match mix order', got_types == want_types, str(got_types))
    check('numbering sequential from first_unit',
          [u['number'] for u in lvl1] == [str(401 + i) for i in range(9)],
          str([u['number'] for u in lvl1]))
    u4 = [u for u in lvl1 if u['unit_type'] == '4-room'][0]
    kc4 = kind_counts(u4['points'])
    check('4-room points match template',
          kc4.get('power') == 23 and kc4.get('fan') == 4 and kc4.get('data') == 1 and len(u4['points']) == 49,
          str(kc4))
    u2 = [u for u in lvl1 if u['unit_type'] == '2-room'][0]
    kc2 = kind_counts(u2['points'])
    check('2-room points match template',
          kc2.get('power') == 10 and kc2.get('heater') == 1 and len(u2['points']) == 21,
          str(kc2))
    check('point ids unique per unit', len({p['id'] for p in u4['points']}) == len(u4['points']))
    names = [p['name'] for p in u4['points'] if p['kind'] == 'power'][:3]
    check('point naming convention', names[0].startswith('P-01 ·'), str(names))

    print('\n[invalid mixes -> 400]')
    bad = [
        ('empty mix', []),
        ('unknown room_type', [{'room_type': '6-room', 'count': 2}]),
        ('count 0', [{'room_type': '4-room', 'count': 0}]),
        ('total > 30', [{'room_type': '4-room', 'count': 20}, {'room_type': '3-room', 'count': 15}]),
        ('duplicate room_type', [{'room_type': '4-room', 'count': 2}, {'room_type': '4-room', 'count': 3}]),
    ]
    for label, m in bad:
        r = c.post(f'/api/projects/{pid}/blocks', headers=tok('manager'),
                   json={'name': f'BAD{label[:3].upper()}', 'levels': 1, 'first_unit': 401,
                         'units_per_level': 9, 'room_mix': m})
        check(f'{label} -> 400', r.status_code == 400, f'{r.status_code} {r.text[:100]}')

    print('\n[legacy path: no room_mix]')
    r = c.post(f'/api/projects/{pid}/blocks', headers=tok('manager'),
               json={'name': 'LEG1', 'levels': 1, 'first_unit': 501, 'units_per_level': 3})
    check('legacy create -> 200', r.status_code == 200, r.text[:160])
    leg = list(SYNC[os.environ['DB_NAME']].units.find({'project_id': pid, 'block': 'LEG1'}, {'_id': 0}))
    check('legacy units default to 4-room', len(leg) == 3 and all(u['unit_type'] == '4-room' for u in leg))
    check('legacy units use 4-room template', len(leg[0]['points']) == 49, str(len(leg[0]['points'])))

    print('\n[point template endpoints]')
    r = c.get(f'/api/projects/{pid}/settings/point-templates', headers=tok('engineer'))
    check('GET templates -> 200 with 5 room types',
          r.status_code == 200 and set(r.json()['templates'].keys()) == {'2-room', '3-room', '4-room', '5-room', 'executive'},
          r.text[:120])
    r = c.put(f'/api/projects/{pid}/settings/point-templates', headers=tok('manager'),
              json={'templates': {'2-room': [{'room': 'Living', 'kind': 'power', 'count': 7}]}})
    check('PUT valid -> 200 persists', r.status_code == 200 and
          r.json()['templates']['2-room'] == [{'room': 'Living', 'kind': 'power', 'count': 7}], r.text[:160])
    r = c.put(f'/api/projects/{pid}/settings/point-templates', headers=tok('manager'),
              json={'templates': {'2-room': [{'room': 'Living', 'kind': 'nuclear', 'count': 1}]}})
    check('bad kind -> 400', r.status_code == 400, f'{r.status_code}')
    r = c.put(f'/api/projects/{pid}/settings/point-templates', headers=tok('manager'),
              json={'templates': {'9-room': [{'room': 'Living', 'kind': 'power', 'count': 1}]}})
    check('bad room_type key -> 400', r.status_code == 400, f'{r.status_code}')
    r = c.put(f'/api/projects/{pid}/settings/point-templates', headers=tok('engineer'),
              json={'templates': {'2-room': [{'room': 'Living', 'kind': 'power', 'count': 1}]}})
    check('non-admin/manager -> 403', r.status_code == 403, f'{r.status_code}')
    r = c.get(f'/api/projects/{pid}/settings/point-templates', headers=tok('manager'))
    check('other room types preserved after partial PUT',
          len(r.json()['templates']['4-room']) > 10, '4-room template wiped!')

    print('\n[template edits affect new units only]')
    before_units = {u['id']: len(u['points']) for u in
                    SYNC[os.environ['DB_NAME']].units.find({'project_id': pid}, {'_id': 0})}
    r = c.post(f'/api/projects/{pid}/blocks', headers=tok('manager'),
               json={'name': 'MIX2', 'levels': 1, 'first_unit': 601, 'units_per_level': 2,
                     'room_mix': [{'room_type': '2-room', 'count': 2}]})
    check('new block after edit -> 200', r.status_code == 200, r.text[:160])
    new_units = list(SYNC[os.environ['DB_NAME']].units.find({'project_id': pid, 'block': 'MIX2'}, {'_id': 0}))
    check('new 2-room units use edited template (7 power)',
          len(new_units) == 2 and kind_counts(new_units[0]['points']).get('power') == 7,
          str(kind_counts(new_units[0]['points'])))
    after_units = {u['id']: len(u['points']) for u in
                   SYNC[os.environ['DB_NAME']].units.find({'project_id': pid}, {'_id': 0})}
    unchanged = all(after_units[uid] == n for uid, n in before_units.items())
    check('existing units points untouched by template edit', unchanged)


main()
