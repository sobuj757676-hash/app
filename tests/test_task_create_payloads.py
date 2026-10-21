"""Task creation must accept the exact payloads the web client sends.

Regression (found by the Phase 1 production walkthrough, 2026-10-21):
the tracker PlanSheet and TaskModal send `description: null` when the
note/description field is empty, but TaskIn/DefectTaskIn declared
`description: str` (non-optional), so every task creation with an empty
description failed with 422 in production — silently, because the
compose sheet swallows the error. The older suites never sent the field
at all, so they stayed green while the real client payload failed.
These tests pin the client-shaped payloads.
"""
import os

from pymongo import MongoClient

SYNC = MongoClient(os.environ['MONGO_URL'])
DB = SYNC[os.environ['DB_NAME']]


def _scope(pid, stage_index=2):
    groups = {}
    for u in DB.units.find({'project_id': pid}).sort(
            [('block', 1), ('level', 1), ('number', 1)]):
        groups.setdefault((u['block_id'], u['level']), []).append(u['id'])
    for (block_id, level), ids in groups.items():
        if len(ids) >= 2:
            chosen = ids[:2]
            for uid in chosen:
                DB.units.update_one({'id': uid},
                                    {'$set': {'stage': stage_index,
                                              'rto': 'none'}})
            return {'block_id': block_id, 'level': level,
                    'stage_index': stage_index, 'unit_ids': chosen}
    raise AssertionError('no unit group with >= 2 units')


def test_planned_compose_payload_with_null_description(client, users, me, pid):
    """UnitTracker PlanSheet submit body, verbatim shape (note empty)."""
    payload = {'title': 'Cement plastering — Blk 35A L3 (2 units)',
               'description': None, 'kind': 'planned', 'scope': _scope(pid),
               'plan_date': '2026-10-21', 'due_date': '2026-10-21',
               'assignees': [me['worker']], 'priority': 'medium',
               'completed_unit_ids': []}
    r = client.post(f'/api/projects/{pid}/tasks',
                    headers=users['supervisor'], json=payload)
    assert r.status_code == 200, r.text[:300]
    assert r.json()['description'] == ''
    assert r.json()['kind'] == 'planned'


def test_adhoc_payload_with_null_description(client, users, me, pid):
    """TaskModal create body, verbatim shape (description/unit/due empty)."""
    payload = {'title': 'Adhoc payload parity', 'description': None,
               'unit_id': None, 'defect_id': None,
               'assignees': [me['worker']], 'priority': 'medium',
               'due_date': None}
    r = client.post(f'/api/projects/{pid}/tasks',
                    headers=users['supervisor'], json=payload)
    assert r.status_code == 200, r.text[:300]
    assert r.json()['description'] == ''


def test_defect_followup_payload_with_nulls(client, users, pid):
    """TaskModal follow-up body: description null AND assignees null."""
    d = client.post(f'/api/projects/{pid}/defects',
                    headers=users['supervisor'],
                    json={'title': 'Payload parity defect',
                          'description': 'cracked conduit',
                          'severity': 'major'})
    assert d.status_code == 200, d.text[:300]
    payload = {'title': 'Follow-up payload parity', 'description': None,
               'assignees': None, 'priority': 'medium', 'due_date': None}
    r = client.post(f"/api/defects/{d.json()['id']}/tasks",
                    headers=users['supervisor'], json=payload)
    assert r.status_code == 200, r.text[:300]
    assert r.json()['description'] == ''
    assert r.json()['assignees'] == []
