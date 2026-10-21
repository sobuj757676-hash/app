"""RTO Walk batch endpoints (spec v2 §4 + v2.1 §D).

The walk is a batch front-end over the existing RTO machinery: requests
create the same inspection records as POST /units/{id}/inspections,
proposals live on the inspection record (proposed_result/by/at), and
decisions write through the same path as POST /inspections/{id}/decision.
"""
import os

from pymongo import MongoClient

SYNC = MongoClient(os.environ.get('MONGO_URL', 'mongodb://127.0.0.1:27019'))
DB = SYNC[os.environ['DB_NAME']]

_used = set()


def _gate_index(pid):
    project = DB.projects.find_one({'id': pid})
    return next(i for i, s in enumerate(project['workflow_stages'])
                if s.get('requires_rto'))


def _unit_at(pid, stage, rto='none'):
    u = DB.units.find_one({'project_id': pid, 'id': {'$nin': list(_used)}})
    _used.add(u['id'])
    DB.units.update_one({'id': u['id']}, {'$set': {'stage': stage, 'rto': rto}})
    return u['id']


def _checklist(client, pid, headers):
    tpl = client.get(f'/api/projects/{pid}/settings/rto-checklist',
                     headers=headers).json()['template']
    return [{'item': i, 'checked': True} for i in tpl]


def _request(client, pid, headers, unit_ids):
    return client.post(f'/api/projects/{pid}/rto-walk/requests', headers=headers,
                       json={'unit_ids': unit_ids, 'inspector': 'RTO Officer',
                             'date': '2026-10-21', 'note': '',
                             'checklist': _checklist(client, pid, headers)})


def test_walk_requests_batch_and_idempotent(client, users, pid):
    gate = _gate_index(pid)
    a, b = _unit_at(pid, gate), _unit_at(pid, gate)
    off_gate = _unit_at(pid, gate - 1)
    before = DB.inspections.count_documents({'unit_id': a})
    r = _request(client, pid, users['supervisor'], [a, b, off_gate, 'missing-id'])
    assert r.status_code == 200, r.text[:200]
    by_id = {x['unit_id']: x for x in r.json()['results']}
    assert by_id[a]['status'] == 'requested' and by_id[a]['inspection_id']
    assert by_id[b]['status'] == 'requested'
    assert by_id[off_gate]['status'] == 'not_at_gate'
    assert by_id['missing-id']['status'] == 'not_found'
    # Records match the single-unit shape: pending, checklist stored with
    # checked_by, requested_by set, unit flipped to rto=pending.
    insp = DB.inspections.find_one({'id': by_id[a]['inspection_id']})
    assert insp['status'] == 'pending' and insp['unit_id'] == a
    assert insp['inspector'] == 'RTO Officer' and insp['date'] == '2026-10-21'
    assert insp['checklist'] and all(c['checked'] for c in insp['checklist'])
    assert insp['checklist'][0]['checked_by']['name']
    assert insp['requested_by']['name']
    assert DB.units.find_one({'id': a})['rto'] == 'pending'
    # Re-run: already_pending, no duplicate inspection.
    r = _request(client, pid, users['supervisor'], [a])
    res = r.json()['results'][0]
    assert res['status'] == 'already_pending'
    assert res['inspection_id'] == by_id[a]['inspection_id']
    assert DB.inspections.count_documents({'unit_id': a}) == before + 1


def test_walk_requests_roles_and_checklist(client, users, pid):
    gate = _gate_index(pid)
    u = _unit_at(pid, gate)
    payload = {'unit_ids': [u], 'inspector': 'RTO Officer', 'date': '2026-10-21',
               'checklist': _checklist(client, pid, users['supervisor'])}
    r = client.post(f'/api/projects/{pid}/rto-walk/requests',
                    headers=users['worker'], json=payload)
    assert r.status_code == 403
    r = client.post(f'/api/projects/{pid}/rto-walk/requests',
                    headers=users['viewer'], json=payload)
    assert r.status_code == 403
    # Unconfirmed checklist is rejected before any unit is touched.
    bad = dict(payload, checklist=[{'item': i['item'], 'checked': False}
                                   for i in payload['checklist']])
    r = client.post(f'/api/projects/{pid}/rto-walk/requests',
                    headers=users['supervisor'], json=bad)
    assert r.status_code == 400
    assert DB.units.find_one({'id': u})['rto'] == 'none'


def test_proposal_lifecycle_and_confirm(client, users, pid, me):
    gate = _gate_index(pid)
    u = _unit_at(pid, gate)
    insp_id = _request(client, pid, users['supervisor'], [u]).json()['results'][0]['inspection_id']
    # Supervisor records a proposal: fields set, nothing decided.
    r = client.post(f'/api/projects/{pid}/rto-walk/proposals', headers=users['supervisor'],
                    json={'items': [{'inspection_id': insp_id, 'result': 'approved'}]})
    assert r.status_code == 200 and r.json()['results'][0]['status'] == 'proposed'
    insp = DB.inspections.find_one({'id': insp_id})
    assert insp['proposed_result'] == 'approved'
    assert insp['proposed_by']['id'] == me['supervisor']
    assert insp['proposed_at']
    assert insp['status'] == 'pending' and insp['decided_by'] is None
    unit = DB.units.find_one({'id': u})
    assert unit['stage'] == gate and unit['rto'] == 'pending'
    # Worker/viewer cannot propose.
    for role in ('worker', 'viewer'):
        r = client.post(f'/api/projects/{pid}/rto-walk/proposals', headers=users[role],
                        json={'items': [{'inspection_id': insp_id, 'result': 'rework'}]})
        assert r.status_code == 403, role
    # Supervisor cannot decide.
    r = client.post(f'/api/projects/{pid}/rto-walk/decisions', headers=users['supervisor'],
                    json={'items': [{'inspection_id': insp_id}], 'inspector': 'RTO Officer'})
    assert r.status_code == 403
    # Manager confirms the proposal (no explicit result): unit advances past
    # the gate, record closes, proposal fields survive for the audit trail.
    r = client.post(f'/api/projects/{pid}/rto-walk/decisions', headers=admin_headers(client),
                    json={'items': [{'inspection_id': insp_id}], 'inspector': 'RTO Officer'})
    assert r.status_code == 200, r.text[:200]
    res = r.json()['results'][0]
    assert res['status'] == 'decided' and res['result'] == 'approved'
    unit = DB.units.find_one({'id': u})
    assert unit['stage'] == gate + 1 and unit['rto'] == 'approved'
    insp = DB.inspections.find_one({'id': insp_id})
    assert insp['status'] == 'approved' and insp['decided_by']
    assert insp['proposed_result'] == 'approved' and insp['proposed_by']['id'] == me['supervisor']
    hist = [h for h in unit['history'] if h.get('result') == 'approved']
    assert hist and hist[-1]['inspector'] == 'RTO Officer'
    # Proposing on a decided inspection is refused per item.
    r = client.post(f'/api/projects/{pid}/rto-walk/proposals', headers=users['supervisor'],
                    json={'items': [{'inspection_id': insp_id, 'result': 'rework'}]})
    assert r.json()['results'][0]['status'] == 'already_decided'
    # A repeat decision is refused the same way.
    r = client.post(f'/api/projects/{pid}/rto-walk/decisions', headers=admin_headers(client),
                    json={'items': [{'inspection_id': insp_id}], 'inspector': 'RTO Officer'})
    assert r.json()['results'][0]['status'] == 'already_decided'


def admin_headers(client):
    r = client.post('/api/auth/login', json={'identifier': 'admin@voltcraft.local',
                                             'password': 'changeme123'})
    return {'Authorization': f"Bearer {r.json()['token']}"}


def test_proposal_overwrite_logs_twice(client, users, pid):
    gate = _gate_index(pid)
    u = _unit_at(pid, gate)
    insp_id = _request(client, pid, users['supervisor'], [u]).json()['results'][0]['inspection_id']
    for result in ('approved', 'rework'):
        r = client.post(f'/api/projects/{pid}/rto-walk/proposals', headers=users['supervisor'],
                        json={'items': [{'inspection_id': insp_id, 'result': result}]})
        assert r.json()['results'][0]['status'] == 'proposed'
    insp = DB.inspections.find_one({'id': insp_id})
    assert insp['proposed_result'] == 'rework' and insp['status'] == 'pending'
    logs = DB.activity.count_documents(
        {'project_id': pid, 'kind': 'inspection',
         'message': {'$regex': 'Proposed outcome recorded'}})
    assert logs >= 2


def test_walk_decision_override_to_rework(client, users, pid):
    gate = _gate_index(pid)
    u = _unit_at(pid, gate)
    insp_id = _request(client, pid, users['supervisor'], [u]).json()['results'][0]['inspection_id']
    client.post(f'/api/projects/{pid}/rto-walk/proposals', headers=users['supervisor'],
                json={'items': [{'inspection_id': insp_id, 'result': 'approved'}]})
    # Engineer overrides the proposal at decision time.
    r = client.post(f'/api/projects/{pid}/rto-walk/decisions', headers=users['engineer'],
                    json={'items': [{'inspection_id': insp_id, 'result': 'rework'}],
                          'inspector': 'RTO Officer', 'note': 'Rectify containment'})
    res = r.json()['results'][0]
    assert res['status'] == 'decided' and res['result'] == 'rework'
    unit = DB.units.find_one({'id': u})
    assert unit['stage'] == gate and unit['rto'] == 'rework'
    insp = DB.inspections.find_one({'id': insp_id})
    assert insp['status'] == 'rework' and insp['proposed_result'] == 'approved'


def test_walk_decision_needs_a_result(client, users, pid):
    gate = _gate_index(pid)
    u = _unit_at(pid, gate)
    insp_id = _request(client, pid, users['supervisor'], [u]).json()['results'][0]['inspection_id']
    r = client.post(f'/api/projects/{pid}/rto-walk/decisions', headers=users['engineer'],
                    json={'items': [{'inspection_id': insp_id}], 'inspector': 'RTO Officer'})
    assert r.json()['results'][0]['status'] == 'no_result'
    assert DB.inspections.find_one({'id': insp_id})['status'] == 'pending'
    r = client.post(f'/api/projects/{pid}/rto-walk/decisions', headers=users['engineer'],
                    json={'items': [{'inspection_id': 'missing-id'}], 'inspector': 'RTO Officer'})
    assert r.json()['results'][0]['status'] == 'not_found'
