"""Phase 2 integration tests: defects, tasks, photos, notifications, RTO checklist.

Runs against a local mongod (Atlas DNS is blocked from the sandbox).
Usage:  ~/workspace/.venv-phase1/bin/python tests/test_phase2.py
Expects mongod on 127.0.0.1:27019 (start: ~/workspace/.mongo/bin/mongod
--dbpath /tmp/mongo-phase2 --port 27019 --fork --logpath /tmp/mongo-phase2.log)
"""
import io
import os
import sys

os.environ['MONGO_URL'] = 'mongodb://127.0.0.1:27019'
os.environ['DB_NAME'] = 'phase2test'
os.environ['AUTH_SECRET'] = 'test-secret-phase2'
os.environ['CORS_ORIGINS'] = '*'
os.environ.pop('BLOB_READ_WRITE_TOKEN', None)  # ensure upload-token-missing path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'api'))

from pymongo import MongoClient  # noqa: E402  (sync client: setup only, no loop issues)

SYNC = MongoClient(os.environ['MONGO_URL'])
SYNC.drop_database(os.environ['DB_NAME'])

import index  # noqa: E402  (builds its own motor client + fake `server` module)
from fastapi.testclient import TestClient  # noqa: E402

PASS, FAIL = [], []


def check(name, cond, detail=''):
    (PASS if cond else FAIL).append(name)
    print(('  ✓ ' if cond else '  ✗ FAIL ') + name + (f' — {detail}' if detail and not cond else ''))


def main():
    # Context-manager form: one shared event loop for all requests
    # (motor binds to the first loop it sees).
    with TestClient(index.app, raise_server_exceptions=False) as c:
        return run(c)


def run(c):

    r = c.get('/api/health')
    check('health ok', r.status_code == 200, r.text[:200])

    # --- users ---
    def login(identifier, password):
        r = c.post('/api/auth/login', json={'identifier': identifier, 'password': password})
        assert r.status_code == 200, f'login failed for {identifier}: {r.text[:200]}'
        return r.json()['token']

    admin = login('admin@voltcraft.local', 'changeme123')
    H = {'Authorization': f'Bearer {admin}'}
    users = {}
    for role, ident in [('engineer', 'eng@t.co'), ('supervisor', 'sup@t.co'),
                        ('worker', 'wk@t.co'), ('viewer', 'vw@t.co')]:
        r = c.post('/api/auth/users', headers=H,
                   json={'name': f'T-{role}', 'email': ident, 'role': role, 'password': 'password123'})
        assert r.status_code == 200, f'create {role}: {r.text[:200]}'
        users[role] = login(ident, 'password123')
    tok = lambda role: {'Authorization': f'Bearer {users[role]}'}  # noqa: E731
    worker2_r = c.post('/api/auth/users', headers=H,
                       json={'name': 'T-worker2', 'email': 'wk2@t.co', 'role': 'worker', 'password': 'password123'})
    worker2 = login('wk2@t.co', 'password123')
    T2 = {'Authorization': f'Bearer {worker2}'}

    projects = c.get('/api/projects', headers=H).json()
    pid = projects[0]['id']
    ws = c.get(f'/api/projects/{pid}/workspace', headers=H).json()
    unit = ws['units'][0]
    check('workspace includes defects+tasks lists', 'defects' in ws and 'tasks' in ws)
    check('checklist template seeded on project',
          ws['project'].get('rto_checklist_template') == [
              'All conduit points hacked / exposed', 'Wires pulled and labeled',
              'Gang boxes installed where required', 'Work area cleaned and accessible',
              'Relevant drawing revision available on site',
              'Previous defects on this unit verified closed'])
    template = ws['project']['rto_checklist_template']

    print('\n[2.1 defects]')
    # worker reports a defect
    r = c.post(f'/api/projects/{pid}/defects', headers=tok('worker'),
               json={'title': 'Conduit crushed at bend', 'description': 'dented',
                     'category': 'workmanship', 'severity': 'major', 'unit_id': unit['id']})
    check('worker creates defect', r.status_code == 200, r.text[:200])
    d1 = r.json()
    check('defect starts open, reported_by=worker',
          d1['status'] == 'open' and d1['reported_by']['id'] != '')
    # viewer cannot create
    r = c.post(f'/api/projects/{pid}/defects', headers=tok('viewer'),
               json={'title': 'x', 'description': 'y'})
    check('viewer cannot create defect', r.status_code == 403, r.text[:120])
    # invalid transition open -> verified rejected
    r = c.post(f"/api/defects/{d1['id']}/transition", headers=H, json={'status': 'verified'})
    check('open->verified rejected', r.status_code == 400, r.text[:120])
    # supervisor assigns to worker
    me = c.get('/api/auth/me', headers=tok('worker')).json()
    r = c.post(f"/api/defects/{d1['id']}/assign", headers=tok('supervisor'),
               json={'assignee_id': me['id']})
    d1a = r.json()
    check('supervisor assigns, status->assigned',
          r.status_code == 200 and d1a['status'] == 'assigned' and d1a['assigned_to'] == me['id'], r.text[:160])
    # worker cannot assign
    r = c.post(f"/api/defects/{d1['id']}/assign", headers=tok('worker'),
               json={'assignee_id': me['id']})
    check('worker cannot assign', r.status_code == 403)
    # notification to assignee
    r = c.get('/api/notifications?unread_only=true', headers=tok('worker'))
    notifs = r.json()
    check('defect_assigned notification created',
          any(n['kind'] == 'defect_assigned' for n in notifs), str([n['kind'] for n in notifs]))
    # worker lifecycle on own defect
    for s in ['in_progress', 'rectified']:
        r = c.post(f"/api/defects/{d1['id']}/transition", headers=tok('worker'), json={'status': s})
        check(f'worker moves to {s}', r.status_code == 200, r.text[:160])
    r = c.post(f"/api/defects/{d1['id']}/transition", headers=tok('worker'), json={'status': 'verified'})
    check('worker cannot verify', r.status_code == 403, r.text[:120])
    r = c.post(f"/api/defects/{d1['id']}/transition", headers=tok('supervisor'), json={'status': 'verified'})
    check('supervisor cannot verify', r.status_code == 403, r.text[:120])
    r = c.post(f"/api/defects/{d1['id']}/transition", headers=tok('engineer'),
               json={'status': 'verified', 'note': 'checked ok'})
    check('engineer verifies', r.status_code == 200 and r.json()['verified_by'] is not None, r.text[:160])
    r = c.post(f"/api/defects/{d1['id']}/transition", headers=H, json={'status': 'open'})
    check('verified is terminal', r.status_code == 400)
    # worker visibility: worker2 sees only own
    r = c.get(f'/api/projects/{pid}/defects', headers=T2)
    check('worker2 sees no defects', r.status_code == 200 and r.json() == [])
    r = c.get(f'/api/projects/{pid}/defects', headers=tok('worker'))
    check('worker sees own defect', len(r.json()) == 1)
    r = c.get(f'/api/projects/{pid}/defects?status=verified', headers=H)
    check('status filter works', len(r.json()) == 1 and r.json()[0]['id'] == d1['id'])
    # edit: reporter can edit
    r = c.patch(f"/api/defects/{d1['id']}", headers=tok('worker'), json={'title': 'Conduit crushed (updated)'})
    check('reporter edits defect', r.status_code == 200 and r.json()['title'] == 'Conduit crushed (updated)')
    r = c.patch(f"/api/defects/{d1['id']}", headers=T2, json={'title': 'hijack'})
    check('other worker cannot edit', r.status_code == 403)

    print('\n[critical defect gate]')
    r = c.post(f'/api/projects/{pid}/defects', headers=H,
               json={'title': 'Exposed live cable', 'severity': 'critical', 'unit_id': unit['id']})
    crit = r.json()
    # find a unit at stage < 9 we can advance; use the defect's unit current stage
    u = c.get(f'/api/projects/{pid}/workspace', headers=H).json()['units'][0]
    r = c.post(f"/api/units/{u['id']}/advance", headers=H,
               json={'expected_stage': u['stage'], 'note': 'try'})
    blocked = r.status_code == 400 and 'Exposed live cable' in r.text
    check('critical defect blocks advance', blocked, r.text[:160])
    # verify the defect, then advance works
    for s, hdr in [('assigned', H), ('in_progress', H), ('rectified', H), ('verified', H)]:
        rr = c.post(f"/api/defects/{crit['id']}/transition", headers=hdr, json={'status': s})
        assert rr.status_code == 200, f'{s}: {rr.text[:160]}'
    r = c.post(f"/api/units/{u['id']}/advance", headers=H,
               json={'expected_stage': u['stage'], 'note': 'after fix'})
    check('advance works after verify', r.status_code == 200, r.text[:160])

    print('\n[2.3 tasks]')
    r = c.post(f'/api/projects/{pid}/tasks', headers=tok('worker'),
               json={'title': 'sneaky', 'assigned_to': me['id']})
    check('worker cannot create task', r.status_code == 403)
    r = c.post(f'/api/projects/{pid}/tasks', headers=tok('supervisor'),
               json={'title': 'Pull wires L3', 'description': 'all points',
                     'assigned_to': me['id'], 'priority': 'high',
                     'due_date': '2026-10-10', 'unit_id': unit['id']})
    check('supervisor creates task', r.status_code == 200, r.text[:200])
    t1 = r.json()
    r = c.get('/api/notifications?unread_only=true', headers=tok('worker'))
    check('task_assigned notification created',
          any(n['kind'] == 'task_assigned' and t1['id'] in n['link'].get('id', '') for n in r.json()))
    r = c.get(f'/api/projects/{pid}/tasks', headers=T2)
    check('worker2 sees no tasks', r.json() == [])
    r = c.get(f'/api/projects/{pid}/tasks?assigned_to=me', headers=tok('worker'))
    check('worker sees own task', len(r.json()) == 1)
    r = c.post(f"/api/tasks/{t1['id']}/transition", headers=tok('worker'), json={'status': 'done'})
    check('worker cannot skip to done', r.status_code == 400, r.text[:120])
    for s in ['in_progress', 'done']:
        r = c.post(f"/api/tasks/{t1['id']}/transition", headers=tok('worker'), json={'status': s})
        check(f'worker moves task to {s}', r.status_code == 200, r.text[:160])
    r = c.get('/api/notifications?unread_only=true', headers=tok('supervisor'))
    check('task_completed notifies creator',
          any(n['kind'] == 'task_completed' for n in r.json()))
    r = c.post(f"/api/tasks/{t1['id']}/transition", headers=tok('worker'), json={'status': 'todo'})
    check('done is terminal', r.status_code == 400)
    r = c.get(f'/api/projects/{pid}/tasks', headers=tok('viewer'))
    check('viewer can list tasks', r.status_code == 200)

    print('\n[2.4 notifications API]')
    r = c.get('/api/notifications/unread-count', headers=tok('worker'))
    n0 = r.json()['count']
    check('unread-count > 0', n0 > 0)
    nid = c.get('/api/notifications', headers=tok('worker')).json()[0]['id']
    r = c.post(f'/api/notifications/{nid}/read', headers=tok('worker'))
    check('mark read', r.status_code == 200 and r.json()['ok'] is True)
    r = c.get('/api/notifications/unread-count', headers=tok('worker'))
    check('unread-count decreases', r.json()['count'] == n0 - 1)
    r = c.post(f'/api/notifications/{nid}/read', headers=T2)
    check('cannot read others notification', r.status_code == 404)

    print('\n[2.5 RTO checklist + approvals]')
    r = c.get(f'/api/projects/{pid}/settings/rto-checklist', headers=tok('viewer'))
    check('checklist readable by viewer', r.status_code == 200 and len(r.json()['template']) == 6)
    r = c.put(f'/api/projects/{pid}/settings/rto-checklist', headers=tok('supervisor'),
              json={'template': ['a', 'b']})
    check('supervisor cannot edit template', r.status_code == 403)
    r = c.put(f'/api/projects/{pid}/settings/rto-checklist', headers=H,
              json={'template': ['Check one', 'Check two']})
    check('admin edits template', r.status_code == 200 and r.json()['template'] == ['Check one', 'Check two'],
          r.text[:160])
    tpl2 = ['Check one', 'Check two']
    # find a unit at stage 5 with rto none/rework for inspection request
    ws = c.get(f'/api/projects/{pid}/workspace', headers=H).json()
    cand = next(u for u in ws['units'] if u['stage'] == 5 and u['rto'] in ('none', 'rework'))
    base_insp = {'inspector': 'RTO Officer', 'date': '2026-10-05', 'note': ''}
    r = c.post(f"/api/units/{cand['id']}/inspections", headers=H, json=base_insp)
    check('missing checklist -> 400', r.status_code == 400, r.text[:160])
    bad = dict(base_insp, checklist=[{'item': 'Check one', 'checked': True},
                                    {'item': 'Check two', 'checked': False}])
    r = c.post(f"/api/units/{cand['id']}/inspections", headers=H, json=bad)
    check('unchecked item -> 400', r.status_code == 400, r.text[:160])
    bad2 = dict(base_insp, checklist=[{'item': 'Wrong item', 'checked': True},
                                     {'item': 'Check two', 'checked': True}])
    r = c.post(f"/api/units/{cand['id']}/inspections", headers=H, json=bad2)
    check('template mismatch -> 400', r.status_code == 400, r.text[:160])
    good = dict(base_insp, checklist=[{'item': 'Check one', 'checked': True},
                                     {'item': 'Check two', 'checked': True}])
    r = c.post(f"/api/units/{cand['id']}/inspections", headers=tok('supervisor'), json=good)
    check('valid checklist request accepted', r.status_code == 200, r.text[:200])
    insp = r.json()
    check('requested_by recorded + checklist stored',
          insp['requested_by']['name'] == 'T-supervisor' and len(insp['checklist']) == 2
          and insp['checklist'][0]['checked_by']['name'] == 'T-supervisor')
    # restore template for the rest of the suite
    c.put(f'/api/projects/{pid}/settings/rto-checklist', headers=H, json={'template': template})
    r = c.post(f"/api/inspections/{insp['id']}/decision", headers=tok('engineer'),
               json={'result': 'approved', 'inspector': 'RTO Officer', 'note': 'ok'})
    dec = r.json()
    check('decision records decided_by',
          r.status_code == 200 and dec['decided_by']['name'] == 'T-engineer' and dec['decided_at'])
    r = c.get('/api/notifications?unread_only=true', headers=tok('supervisor'))
    check('rto_decided notifies requester',
          any(n['kind'] == 'rto_decided' for n in r.json()))

    print('\n[directory]')
    r = c.get('/api/auth/directory', headers=H)
    check('admin sees directory', r.status_code == 200 and len(r.json()) >= 5)
    check('directory has no password hashes',
          all('password_hash' not in u for u in r.json()))
    r = c.get('/api/auth/directory', headers=tok('worker'))
    check('worker cannot see directory', r.status_code == 403)
    r = c.get('/api/auth/directory', headers=tok('supervisor'))
    check('supervisor sees directory', r.status_code == 200)

    print('\n[2.2 photos]')
    from PIL import Image as PILImage
    img = PILImage.new('RGB', (800, 600), 'red')
    buf = io.BytesIO()
    img.save(buf, 'JPEG')
    jpeg = buf.getvalue()

    def upload(headers, etype, eid, data, mime, caption='cap'):
        return c.post('/api/photos/upload', headers=headers,
                      files={'file': ('p.jpg', data, mime)},
                      data={'entity_type': etype, 'entity_id': eid, 'caption': caption})

    r = upload(tok('engineer'), 'defect', d1['id'], jpeg, 'image/jpeg')
    check('upload without token -> 503', r.status_code == 503, r.text[:160])
    r = upload(tok('engineer'), 'defect', d1['id'], b'not an image', 'text/plain')
    check('bad MIME rejected', r.status_code == 400, r.text[:120])
    r = upload(tok('engineer'), 'defect', d1['id'], b'\xff' * (11 * 1024 * 1024), 'image/jpeg')
    check('oversize rejected', r.status_code == 400, r.text[:120])
    r = upload(tok('engineer'), 'defect', 'no-such-id', jpeg, 'image/jpeg')
    check('unknown entity -> 404', r.status_code == 404)
    r = upload(T2, 'defect', d1['id'], jpeg, 'image/jpeg')
    check('worker cannot upload to others defect', r.status_code == 403)
    # mock Blob storage for the success path
    import photos as photos_mod
    real_put = photos_mod._blob_put
    photos_mod._blob_put = lambda p, d, ct: {'url': f'https://blob.test/{p}'}
    os.environ['BLOB_READ_WRITE_TOKEN'] = 'test-token-for-mocked-blob'
    try:
        r = upload(tok('engineer'), 'defect', d1['id'], jpeg, 'image/jpeg')
        ph = r.json()
        check('upload ok with mocked blob',
              r.status_code == 200 and ph['url'].startswith('https://blob.test/')
              and ph['thumb_url'].endswith('_thumb.jpg'), r.text[:200])
        r = c.get(f"/api/photos?entity_type=defect&entity_id={d1['id']}", headers=H)
        check('photo listed', r.status_code == 200 and len(r.json()) == 1)
        d_after = c.get(f'/api/projects/{pid}/defects', headers=H).json()
        d1x = next(d for d in d_after if d['id'] == d1['id'])
        check('defect.photos linked', ph['id'] in d1x['photos'])
        r = c.delete(f"/api/photos/{ph['id']}", headers=tok('supervisor'))
        check('supervisor cannot delete photo', r.status_code == 403)
        r = c.delete(f"/api/photos/{ph['id']}", headers=H)
        check('admin soft-deletes photo', r.status_code == 200 and r.json()['deleted'] is True)
        r = c.get(f"/api/photos?entity_type=defect&entity_id={d1['id']}", headers=H)
        check('deleted photo excluded', r.json() == [])
        # worker uploads to own defect
        r = c.post(f'/api/projects/{pid}/defects', headers=tok('worker'),
                   json={'title': 'worker own defect', 'unit_id': unit['id']})
        wd = r.json()
        r = upload(tok('worker'), 'defect', wd['id'], jpeg, 'image/jpeg')
        check('worker uploads to own defect', r.status_code == 200, r.text[:160])
    finally:
        photos_mod._blob_put = real_put
        os.environ.pop('BLOB_READ_WRITE_TOKEN', None)

    print(f'\n{len(PASS)} passed, {len(FAIL)} failed')
    return 1 if FAIL else 0


if __name__ == '__main__':
    sys.exit(main())
