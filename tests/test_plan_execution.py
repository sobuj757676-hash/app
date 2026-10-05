"""Plan-execution backend coverage (pytest) for the daily-plan redesign.

Covers:
- completed_unit_ids on task create (stored, validated against scope)
- PATCH completed_unit_ids: whole-list replace, 400 for ids outside scope.unit_ids
- Worker PATCH permission: allowed for completed_unit_ids on assigned tasks;
  403 for any other field; 403 on unassigned tasks
- due_date defaults to plan_date for kind='planned' when due_date omitted
- dedupe of completed_unit_ids (order preserved)
"""
import os

from pymongo import MongoClient
from pymongo import MongoClient

SYNC = MongoClient(os.environ['MONGO_URL'])
DB = SYNC[os.environ['DB_NAME']]


def _unit_ids_for_scope(pid, block_id, level, stage_index, n=3):
    cur = DB.units.find({'project_id': pid, 'block_id': block_id,
                         'level': level}).sort('number', 1).limit(n)
    ids = [u['id'] for u in cur]
    for uid in ids:
        DB.units.update_one({'id': uid}, {'$set': {'stage': stage_index}})
    return ids


def _scope_payload(pid):
    block = DB.blocks.find_one({'project_id': pid})
    level = DB.units.find_one({'project_id': pid, 'block_id': block['id']})['level']
    unit_ids = _unit_ids_for_scope(pid, block['id'], level, 3)
    return {'block_id': block['id'], 'level': level,
            'stage_index': 3, 'unit_ids': unit_ids}


def _make_planned(client, users, me, pid, **over):
    scope = _scope_payload(pid)
    payload = {'title': 'PY plan execution', 'kind': 'planned',
               'scope': scope, 'plan_date': '2026-10-06',
               'assignees': [me['worker'], me['worker2']]}
    payload.update(over)
    r = client.post(f'/api/projects/{pid}/tasks', headers=users['supervisor'],
                    json=payload)
    assert r.status_code == 200, r.text[:200]
    return r.json(), scope


def _get_task(client, headers, pid, tid):
    return next(t for t in
                client.get(f'/api/projects/{pid}/tasks', headers=headers).json()
                if t['id'] == tid)


# ---------- create ----------

def test_create_planned_with_completed_unit_ids(client, users, me, pid):
    scope = _scope_payload(pid)
    partial = scope['unit_ids'][:2]
    t, _ = _make_planned(client, users, me, pid, completed_unit_ids=partial)
    assert t['completed_unit_ids'] == partial
    # defaults: due_date == plan_date, empty list when omitted
    assert t['due_date'] == t['plan_date'] == '2026-10-06'
    t2, _ = _make_planned(client, users, me, pid)
    assert t2['completed_unit_ids'] == []


def test_create_rejects_completed_unit_not_in_scope(client, users, me, pid):
    scope = _scope_payload(pid)
    r = client.post(f'/api/projects/{pid}/tasks', headers=users['supervisor'],
                    json={'title': 'PY bad completion', 'kind': 'planned',
                          'scope': scope, 'plan_date': '2026-10-06',
                          'completed_unit_ids': ['no-such-unit'],
                          'assignees': [me['worker']]})
    assert r.status_code == 400, r.text[:160]


def test_due_date_defaults_to_plan_date(client, users, me, pid):
    t, _ = _make_planned(client, users, me, pid)
    assert t['due_date'] == '2026-10-06'
    # explicit due_date wins
    t2, _ = _make_planned(client, users, me, pid, due_date='2026-10-10')
    assert t2['due_date'] == '2026-10-10'


def test_create_dedupes_completed_unit_ids(client, users, me, pid):
    scope = _scope_payload(pid)
    u = scope['unit_ids']
    t, _ = _make_planned(client, users, me, pid,
                         completed_unit_ids=[u[1], u[0], u[1], u[0]])
    assert t['completed_unit_ids'] == [u[1], u[0]]


# ---------- PATCH by supervisor ----------

def test_patch_completed_unit_ids_replace(client, users, me, pid):
    t, scope = _make_planned(client, users, me, pid)
    tid = t['id']
    u = scope['unit_ids']
    r = client.patch(f'/api/tasks/{tid}', headers=users['supervisor'],
                     json={'completed_unit_ids': [u[0]]})
    assert r.status_code == 200, r.text[:160]
    assert r.json()['completed_unit_ids'] == [u[0]]
    # second PATCH replaces the whole list, dedupes, preserves order
    r = client.patch(f'/api/tasks/{tid}', headers=users['supervisor'],
                     json={'completed_unit_ids': [u[2], u[0], u[2]]})
    assert r.status_code == 200, r.text[:160]
    assert r.json()['completed_unit_ids'] == [u[2], u[0]]


def test_patch_completed_unit_ids_rejects_out_of_scope(client, users, me, pid):
    t, _ = _make_planned(client, users, me, pid)
    r = client.patch(f"/api/tasks/{t['id']}", headers=users['supervisor'],
                     json={'completed_unit_ids': ['ghost-unit']})
    assert r.status_code == 400, r.text[:160]


def test_supervisor_patch_other_fields_unchanged(client, users, me, pid):
    t, _ = _make_planned(client, users, me, pid)
    r = client.patch(f"/api/tasks/{t['id']}", headers=users['supervisor'],
                     json={'priority': 'high'})
    assert r.status_code == 200, r.text[:160]
    assert r.json()['priority'] == 'high'


# ---------- PATCH by worker ----------

def test_worker_can_patch_completed_unit_ids_on_assigned(client, users, me, pid):
    t, scope = _make_planned(client, users, me, pid)
    tid = t['id']
    u = scope['unit_ids']
    r = client.patch(f'/api/tasks/{tid}', headers=users['worker'],
                     json={'completed_unit_ids': [u[0]]})
    assert r.status_code == 200, r.text[:160]
    assert r.json()['completed_unit_ids'] == [u[0]]
    # worker reads it back in their queue
    seen = _get_task(client, users['worker'], pid, tid)
    assert seen['completed_unit_ids'] == [u[0]]


def test_worker_cannot_patch_other_fields(client, users, me, pid):
    t, scope = _make_planned(client, users, me, pid)
    tid = t['id']
    for body in ({'priority': 'high'}, {'title': 'sneaky rename'},
                 {'completed_unit_ids': [scope['unit_ids'][0]], 'priority': 'low'},
                 {'assignees': [me['worker3']]}):
        r = client.patch(f'/api/tasks/{tid}', headers=users['worker'], json=body)
        assert r.status_code == 403, f'{body}: {r.text[:160]}'


def test_worker_cannot_patch_unassigned_task(client, users, me, pid):
    t, scope = _make_planned(client, users, me, pid)
    tid = t['id']
    # worker3 is not an assignee (and cannot even see the task)
    r = client.patch(f'/api/tasks/{tid}', headers=users['worker3'],
                     json={'completed_unit_ids': [scope['unit_ids'][0]]})
    assert r.status_code == 403, r.text[:160]


def test_worker_patch_validates_scope_too(client, users, me, pid):
    t, _ = _make_planned(client, users, me, pid)
    r = client.patch(f"/api/tasks/{t['id']}", headers=users['worker'],
                     json={'completed_unit_ids': ['not-in-scope']})
    assert r.status_code == 400, r.text[:160]


# ---------- clearing ----------

def test_clearing_completed_unit_ids(client, users, me, pid):
    scope = _scope_payload(pid)
    t, _ = _make_planned(client, users, me, pid,
                         completed_unit_ids=[scope['unit_ids'][0]])
    tid = t['id']
    r = client.patch(f'/api/tasks/{tid}', headers=users['supervisor'],
                     json={'completed_unit_ids': []})
    assert r.status_code == 200, r.text[:160]
    assert r.json()['completed_unit_ids'] == []
