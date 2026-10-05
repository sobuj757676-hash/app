"""Multi-worker task assignment + daily plan task fields (pytest).

Covers: multi-assignee create/visibility, notifications to all assignees,
worker transition by a second assignee, planned-task 403 for workers,
kind/scope/plan_date fields, PATCH reassignment, legacy assigned_to migration.
"""
import asyncio
import os

from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import MongoClient

SYNC = MongoClient(os.environ['MONGO_URL'])
DB = SYNC[os.environ['DB_NAME']]

from seed import initialize  # noqa: E402


def _unit_ids_for_scope(pid, block_id, level, stage_index, n=3):
    cur = DB.units.find({'project_id': pid, 'block_id': block_id,
                         'level': level}).sort('number', 1).limit(n)
    ids = [u['id'] for u in cur]
    for uid in ids:
        DB.units.update_one({'id': uid}, {'$set': {'stage': stage_index}})
    return ids


# ---------- multi-assignee create & visibility ----------

def test_create_multi_assignee(client, users, me, pid):
    r = client.post(f'/api/projects/{pid}/tasks', headers=users['supervisor'],
                    json={'title': 'PY multi-crew pull', 'priority': 'high',
                          'assignees': [me['worker'], me['worker2']]})
    assert r.status_code == 200, r.text[:200]
    t = r.json()
    assert sorted(t['assignees']) == sorted([me['worker'], me['worker2']])
    assert t['assignee_names'] == ['PY worker 2', 'PY worker 3']
    assert t['kind'] == 'adhoc' and t['scope'] is None and t['plan_date'] is None
    assert 'assigned_to' not in t and 'assigned_to_name' not in t
    # both assignees notified
    for role in ('worker', 'worker2'):
        notifs = client.get('/api/notifications?unread_only=true',
                            headers=users[role]).json()
        assert any(n['kind'] == 'task_assigned' and t['id'] in str(n.get('link', {}))
                   for n in notifs), role
    return t['id']


def test_multi_assignee_visibility(client, users, me, pid):
    tid = test_create_multi_assignee(client, users, me, pid)
    for role in ('worker', 'worker2'):
        r = client.get(f'/api/projects/{pid}/tasks', headers=users[role])
        assert any(t['id'] == tid for t in r.json()), role
    r = client.get(f'/api/projects/{pid}/tasks', headers=users['worker3'])
    assert all(t['id'] != tid for t in r.json())
    # workspace bundle shows it only to assignees too
    ws = client.get(f'/api/projects/{pid}/workspace', headers=users['worker3']).json()
    assert all(t['id'] != tid for t in ws['tasks'])
    ws = client.get(f'/api/projects/{pid}/workspace', headers=users['worker']).json()
    assert any(t['id'] == tid and t['assignee_names'] == ['PY worker 2', 'PY worker 3']
               for t in ws['tasks'])


def test_transition_by_second_assignee(client, users, me, pid):
    r = client.post(f'/api/projects/{pid}/tasks', headers=users['supervisor'],
                    json={'title': 'PY second-hand transition',
                          'assignees': [me['worker'], me['worker2']]})
    tid = r.json()['id']
    # third worker cannot touch it
    r = client.post(f'/api/tasks/{tid}/transition', headers=users['worker3'],
                    json={'status': 'in_progress'})
    assert r.status_code == 403
    # second assignee drives it to done
    for s in ('in_progress', 'done'):
        r = client.post(f'/api/tasks/{tid}/transition', headers=users['worker2'],
                        json={'status': s})
        assert r.status_code == 200, r.text[:160]
    # done is terminal even for an assignee
    r = client.post(f'/api/tasks/{tid}/transition', headers=users['worker'],
                    json={'status': 'todo'})
    assert r.status_code == 400


def test_create_validation(client, users, me, pid):
    r = client.post(f'/api/projects/{pid}/tasks', headers=users['supervisor'],
                    json={'title': 'no crew', 'assignees': []})
    assert r.status_code == 422, r.text[:160]
    r = client.post(f'/api/projects/{pid}/tasks', headers=users['supervisor'],
                    json={'title': 'ghost crew', 'assignees': ['no-such-user']})
    assert r.status_code == 404, r.text[:160]
    # inactive user rejected
    DB.users.update_one({'id': me['worker3']}, {'$set': {'active': False}})
    try:
        r = client.post(f'/api/projects/{pid}/tasks', headers=users['supervisor'],
                        json={'title': 'archived crew', 'assignees': [me['worker3']]})
        assert r.status_code == 404, r.text[:160]
    finally:
        DB.users.update_one({'id': me['worker3']}, {'$set': {'active': True}})


def test_defect_followup_accepts_assignees(client, users, me, pid):
    r = client.post(f'/api/projects/{pid}/defects', headers=users['supervisor'],
                    json={'title': 'PY followup defect', 'severity': 'minor'})
    did = r.json()['id']
    r = client.post(f'/api/defects/{did}/tasks', headers=users['supervisor'],
                    json={'title': 'PY followup task',
                          'assignees': [me['worker'], me['worker2']]})
    assert r.status_code == 200, r.text[:160]
    assert r.json()['assignee_names'] == ['PY worker 2', 'PY worker 3']
    r = client.post(f'/api/defects/{did}/tasks', headers=users['supervisor'],
                    json={'title': 'PY unassigned followup'})
    assert r.status_code == 200 and r.json()['assignees'] == [], r.text[:160]


# ---------- planned tasks (daily work plan) ----------

def _scope_payload(pid):
    block = DB.blocks.find_one({'project_id': pid})
    level = DB.units.find_one({'project_id': pid, 'block_id': block['id']})['level']
    unit_ids = _unit_ids_for_scope(pid, block['id'], level, 3)
    return {'block_id': block['id'], 'level': level,
            'stage_index': 3, 'unit_ids': unit_ids}


def test_create_planned_task(client, users, me, pid):
    scope = _scope_payload(pid)
    r = client.post(f'/api/projects/{pid}/tasks', headers=users['supervisor'],
                    json={'title': "PY today's wire pulling", 'kind': 'planned',
                          'scope': scope, 'plan_date': '2026-10-06',
                          'priority': 'urgent',
                          'assignees': [me['worker'], me['worker2']]})
    assert r.status_code == 200, r.text[:200]
    t = r.json()
    assert t['kind'] == 'planned'
    assert t['plan_date'] == '2026-10-06'
    assert t['scope']['block_id'] == scope['block_id']
    assert t['scope']['stage_index'] == 3
    assert sorted(t['scope']['unit_ids']) == sorted(scope['unit_ids'])
    # assignees see the planned task in their queue
    r = client.get(f'/api/projects/{pid}/tasks?assigned_to=me', headers=users['worker2'])
    assert any(x['id'] == t['id'] and x['kind'] == 'planned' for x in r.json())


def test_planned_task_scope_validation(client, users, me, pid):
    scope = _scope_payload(pid)
    bad = dict(scope, stage_index=99)
    r = client.post(f'/api/projects/{pid}/tasks', headers=users['supervisor'],
                    json={'title': 'bad stage', 'kind': 'planned', 'scope': bad,
                          'assignees': [me['worker']]})
    assert r.status_code == 400, r.text[:160]
    bad = dict(scope, block_id='no-such-block')
    r = client.post(f'/api/projects/{pid}/tasks', headers=users['supervisor'],
                    json={'title': 'bad block', 'kind': 'planned', 'scope': bad,
                          'assignees': [me['worker']]})
    assert r.status_code == 400, r.text[:160]
    bad = dict(scope, unit_ids=['no-such-unit'])
    r = client.post(f'/api/projects/{pid}/tasks', headers=users['supervisor'],
                    json={'title': 'bad units', 'kind': 'planned', 'scope': bad,
                          'assignees': [me['worker']]})
    assert r.status_code == 400, r.text[:160]


def test_worker_cannot_create_planned_task(client, users, me, pid):
    scope = _scope_payload(pid)
    r = client.post(f'/api/projects/{pid}/tasks', headers=users['worker'],
                    json={'title': 'sneaky plan', 'kind': 'planned', 'scope': scope,
                          'assignees': [me['worker']]})
    assert r.status_code == 403


def test_patch_reassignment(client, users, me, pid):
    r = client.post(f'/api/projects/{pid}/tasks', headers=users['supervisor'],
                    json={'title': 'PY reassign me', 'assignees': [me['worker']]})
    tid = r.json()['id']
    r = client.patch(f'/api/tasks/{tid}', headers=users['supervisor'],
                     json={'assignees': [me['worker2'], me['worker3']]})
    assert r.status_code == 200, r.text[:160]
    t = r.json()
    assert t['assignee_names'] == ['PY worker 3', 'PY worker 4']
    assert 'assigned_to' not in t and 'assigned_to_name' not in t
    # newly added assignees notified; removed one sees it no more
    for role in ('worker2', 'worker3'):
        notifs = client.get('/api/notifications?unread_only=true',
                            headers=users[role]).json()
        assert any(n['kind'] == 'task_assigned' and tid in str(n.get('link', {}))
                   for n in notifs), role
    r = client.get(f'/api/projects/{pid}/tasks', headers=users['worker'])
    assert all(x['id'] != tid for x in r.json())
    # empty list rejected
    r = client.patch(f'/api/tasks/{tid}', headers=users['supervisor'],
                     json={'assignees': []})
    assert r.status_code in (400, 422), r.text[:160]


def test_legacy_task_migration():
    """Docs written with the old assigned_to shape migrate to assignees."""
    tid = 'py-legacy-task-1'

    async def go():
        mc = AsyncIOMotorClient(os.environ['MONGO_URL'])
        db = mc[os.environ['DB_NAME']]
        await db.tasks.delete_many({'id': tid})
        await db.tasks.insert_one({
            'id': tid, 'project_id': 'x', 'title': 'legacy',
            'assigned_to': 'user-1', 'assigned_to_name': 'Old Name',
            'status': 'todo'})
        await db.tasks.insert_one({
            'id': tid + '-unassigned', 'project_id': 'x', 'title': 'legacy2',
            'assigned_to': None, 'assigned_to_name': '',
            'status': 'todo'})
        await initialize(db)
        doc = await db.tasks.find_one({'id': tid}, {'_id': 0})
        doc2 = await db.tasks.find_one({'id': tid + '-unassigned'}, {'_id': 0})
        await db.tasks.delete_many({'id': {'$in': [tid, tid + '-unassigned']}})
        return doc, doc2

    doc, doc2 = asyncio.run(go())
    assert doc['assignees'] == ['user-1']
    assert doc['assignee_names'] == ['Old Name']
    assert 'assigned_to' not in doc and 'assigned_to_name' not in doc
    assert doc2['assignees'] == [] and doc2['assignee_names'] == []
    assert 'assigned_to' not in doc2
