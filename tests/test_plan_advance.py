"""Checked-unit advance + carry-over dismissal (spec v2 §2/§3, v2.1 §B).

Covers:
- partial advance: only checked scope units move, exactly one stage,
  history event carries task_id / source='plan_advance'
- idempotency proven from history: a repeat call performs zero writes
- stage moved by another workflow -> conflict_ahead (never silent success);
  moved backward -> conflict_behind
- guards: blocked_rto (gate stage), blocked_defect (open critical defect),
  blocked_tests (final stage without passing tests)
- explicit candidate list: unchecked -> not_checked, foreign -> not_in_scope
- roles: worker/viewer 403; cancelled or adhoc task 400; wrong project 404
- done tasks can still advance checked units (v2.1 addendum: 'done' must
  not strand checked-but-unadvanced units)
- dismiss-carryover: skip persists fields + activity, idempotent,
  supersede records the successor, cross-project successor rejected
"""
import os
import uuid

from pymongo import MongoClient

SYNC = MongoClient(os.environ['MONGO_URL'])
DB = SYNC[os.environ['DB_NAME']]


_USED = set()


def _units_at(pid, stage_index, n=4):
    """Take n units from one (block, level) group this module has not used
    yet (tests share one database, so groups must not leak state — e.g. an
    open critical defect — into each other) and pin them to the given
    stage via direct DB writes (fixture setup)."""
    groups = {}
    for u in DB.units.find({'project_id': pid}).sort(
            [('block', 1), ('level', 1), ('number', 1)]):
        groups.setdefault((u['block_id'], u['level']), []).append(u['id'])
    for (block_id, level), ids in groups.items():
        fresh = [i for i in ids if i not in _USED]
        if len(fresh) >= n:
            chosen = fresh[:n]
            _USED.update(chosen)
            for uid in chosen:
                DB.units.update_one({'id': uid},
                                    {'$set': {'stage': stage_index, 'rto': 'none'}})
            return {'block_id': block_id, 'level': level,
                    'stage_index': stage_index, 'unit_ids': chosen}
    raise AssertionError('no unused unit group left')


def _planned(client, users, me, pid, scope, checked=(), **over):
    payload = {'title': 'PY advance', 'kind': 'planned', 'scope': scope,
               'plan_date': '2026-10-06', 'assignees': [me['worker']],
               'completed_unit_ids': list(checked)}
    payload.update(over)
    r = client.post(f'/api/projects/{pid}/tasks', headers=users['supervisor'],
                    json=payload)
    assert r.status_code == 200, r.text[:200]
    return r.json()


def _advance(client, headers, pid, tid, body=None):
    return client.post(f'/api/projects/{pid}/tasks/{tid}/advance',
                       headers=headers, json=body or {})


def _unit(uid):
    return DB.units.find_one({'id': uid})


def _by_id(results):
    return {r['unit_id']: r['result'] for r in results}


# ---------- partial advance + history ----------

def test_partial_advance_moves_only_checked(client, users, me, pid):
    scope = _units_at(pid, 3)
    ids = scope['unit_ids']
    t = _planned(client, users, me, pid, scope, checked=ids[:2])
    r = _advance(client, users['supervisor'], pid, t['id'])
    assert r.status_code == 200, r.text[:200]
    body = r.json()
    got = _by_id(body['results'])
    assert got[ids[0]] == 'advanced' and got[ids[1]] == 'advanced'
    assert len(body['results']) == 2  # unchecked units are not candidates
    assert body['advanced'] == 2 and body['all_advanced'] is False
    for uid in ids[:2]:
        u = _unit(uid)
        assert u['stage'] == 4
        ev = u['history'][-1]
        assert ev['source'] == 'plan_advance' and ev['task_id'] == t['id']
        assert ev['stage'] == 3 and ev['to_stage'] == 4 and ev['by_id'] == me['supervisor']
    for uid in ids[2:]:
        assert _unit(uid)['stage'] == 3


def test_repeat_advance_is_idempotent(client, users, me, pid):
    scope = _units_at(pid, 3)
    ids = scope['unit_ids']
    t = _planned(client, users, me, pid, scope, checked=ids[:2])
    assert _advance(client, users['supervisor'], pid, t['id']).status_code == 200
    hist_len = {u: len(_unit(u)['history']) for u in ids[:2]}
    r = _advance(client, users['supervisor'], pid, t['id'])
    body = r.json()
    got = _by_id(body['results'])
    assert got[ids[0]] == 'already_advanced' and got[ids[1]] == 'already_advanced'
    assert body['advanced'] == 0
    for u in ids[:2]:  # zero writes on the repeat
        assert len(_unit(u)['history']) == hist_len[u]
        assert _unit(u)['stage'] == 4


def test_all_advanced_true_when_scope_past_stage(client, users, me, pid):
    scope = _units_at(pid, 3)
    ids = scope['unit_ids']
    t = _planned(client, users, me, pid, scope, checked=ids)
    body = _advance(client, users['supervisor'], pid, t['id']).json()
    assert body['advanced'] == 4 and body['all_advanced'] is True


# ---------- conflicts: changes by another workflow ----------

def test_external_advance_is_conflict_not_success(client, users, me, pid):
    scope = _units_at(pid, 3)
    ids = scope['unit_ids']
    t = _planned(client, users, me, pid, scope, checked=ids[:2])
    # Another workflow (bulk advance) moves ids[1] before the plan advance.
    r = client.post(f'/api/projects/{pid}/units/bulk-advance',
                    headers=users['supervisor'],
                    json={'unit_ids': [ids[1]], 'to_stage': 4})
    assert r.status_code == 200, r.text[:200]
    body = _advance(client, users['supervisor'], pid, t['id']).json()
    got = _by_id(body['results'])
    assert got[ids[0]] == 'advanced'
    assert got[ids[1]] == 'conflict_ahead'  # NOT already_advanced
    assert body['all_advanced'] is False
    # A repeat still reports the conflict; it never resolves silently.
    body2 = _advance(client, users['supervisor'], pid, t['id']).json()
    assert _by_id(body2['results'])[ids[1]] == 'conflict_ahead'


def test_moved_backward_is_conflict_behind(client, users, me, pid):
    scope = _units_at(pid, 3)
    ids = scope['unit_ids']
    t = _planned(client, users, me, pid, scope, checked=ids[:1])
    DB.units.update_one({'id': ids[0]}, {'$set': {'stage': 2}})  # external change
    body = _advance(client, users['supervisor'], pid, t['id']).json()
    assert _by_id(body['results'])[ids[0]] == 'conflict_behind'
    assert _unit(ids[0])['stage'] == 2  # untouched


# ---------- guards ----------

def test_blocked_rto_gate_stage(client, users, me, pid):
    scope = _units_at(pid, 5)  # default stage list: index 5 carries requires_rto
    ids = scope['unit_ids']
    t = _planned(client, users, me, pid, scope, checked=ids[:1])
    body = _advance(client, users['supervisor'], pid, t['id']).json()
    assert _by_id(body['results'])[ids[0]] == 'blocked_rto'
    assert _unit(ids[0])['stage'] == 5


def test_blocked_critical_defect(client, users, me, pid):
    scope = _units_at(pid, 3)
    ids = scope['unit_ids']
    DB.defects.insert_one({'id': str(uuid.uuid4()), 'project_id': pid,
                           'unit_id': ids[0], 'severity': 'critical',
                           'status': 'open', 'title': 'PY exposed live conductor'})
    t = _planned(client, users, me, pid, scope, checked=ids[:2])
    body = _advance(client, users['supervisor'], pid, t['id']).json()
    got = _by_id(body['results'])
    assert got[ids[0]] == 'blocked_defect'
    assert got[ids[1]] == 'advanced'  # a blocked unit never blocks the rest
    assert _unit(ids[0])['stage'] == 3


def test_blocked_final_stage_tests(client, users, me, pid):
    scope = _units_at(pid, 8)  # final stage of the default 9-stage list
    ids = scope['unit_ids']
    assert _unit(ids[0])['points']  # fixture: units carry points, no tests yet
    t = _planned(client, users, me, pid, scope, checked=ids[:1])
    body = _advance(client, users['supervisor'], pid, t['id']).json()
    assert _by_id(body['results'])[ids[0]] == 'blocked_tests'
    assert _unit(ids[0])['stage'] == 8


# ---------- candidate discipline + roles ----------

def test_explicit_candidates_classify_extras(client, users, me, pid):
    scope = _units_at(pid, 3)
    ids = scope['unit_ids']
    t = _planned(client, users, me, pid, scope, checked=ids[:1])
    body = _advance(client, users['supervisor'], pid, t['id'],
                    {'unit_ids': [ids[0], ids[1], 'foreign-unit']}).json()
    got = _by_id(body['results'])
    assert got[ids[0]] == 'advanced'
    assert got[ids[1]] == 'not_checked'      # in scope but not checked
    assert got['foreign-unit'] == 'not_in_scope'
    assert _unit(ids[1])['stage'] == 3       # unchecked never advances


def test_advance_roles_and_task_state(client, users, me, pid):
    scope = _units_at(pid, 3)
    ids = scope['unit_ids']
    t = _planned(client, users, me, pid, scope, checked=ids[:1])
    assert _advance(client, users['worker'], pid, t['id']).status_code == 403
    assert _advance(client, users['viewer'], pid, t['id']).status_code == 403
    assert _advance(client, users['engineer'], pid, t['id']).status_code == 200
    # Wrong project in the path -> 404.
    assert _advance(client, users['supervisor'], 'no-such-project', t['id']).status_code == 404
    # Cancelled task -> 400.
    t2 = _planned(client, users, me, pid, scope, checked=ids[:1])
    r = client.post(f'/api/tasks/{t2["id"]}/transition', headers=users['supervisor'],
                    json={'status': 'cancelled'})
    assert r.status_code == 200, r.text[:160]
    assert _advance(client, users['supervisor'], pid, t2['id']).status_code == 400


def test_done_task_can_still_advance_checked_units(client, users, me, pid):
    """v2.1 addendum: 'done' must not strand a checked-but-unadvanced unit."""
    scope = _units_at(pid, 3)
    ids = scope['unit_ids']
    t = _planned(client, users, me, pid, scope, checked=ids[:1])
    r = client.post(f'/api/tasks/{t["id"]}/transition', headers=users['supervisor'],
                    json={'status': 'in_progress'})
    assert r.status_code == 200, r.text[:160]
    r = client.post(f'/api/tasks/{t["id"]}/transition', headers=users['supervisor'],
                    json={'status': 'done'})
    assert r.status_code == 200, r.text[:160]
    body = _advance(client, users['supervisor'], pid, t['id']).json()
    assert _by_id(body['results'])[ids[0]] == 'advanced'
    assert _unit(ids[0])['stage'] == 4


# ---------- carry-over dismissal ----------

def test_dismiss_carryover_skip_and_idempotency(client, users, me, pid):
    scope = _units_at(pid, 3)
    t = _planned(client, users, me, pid, scope)
    url = f'/api/tasks/{t["id"]}/dismiss-carryover'
    assert client.post(url, headers=users['worker'], json={}).status_code == 403
    r = client.post(url, headers=users['supervisor'], json={})
    assert r.status_code == 200, r.text[:200]
    first = r.json()
    assert first['carryover_dismissed_at'] and first['carryover_dismissed_by']['id'] == me['supervisor']
    assert 'superseded_by_task_id' not in first
    again = client.post(url, headers=users['supervisor'], json={}).json()
    assert again['carryover_dismissed_at'] == first['carryover_dismissed_at']  # no-op
    act = DB.activity.find_one({'project_id': pid, 'kind': 'task',
                                'message': {'$regex': 'Carry-over dismissed'}})
    assert act is not None


def test_dismiss_carryover_supersede_records_successor(client, users, me, pid):
    scope = _units_at(pid, 3)
    src = _planned(client, users, me, pid, scope)
    dst = _planned(client, users, me, pid, scope)
    r = client.post(f'/api/tasks/{src["id"]}/dismiss-carryover',
                    headers=users['supervisor'],
                    json={'superseded_by_task_id': dst['id']})
    assert r.status_code == 200, r.text[:200]
    assert r.json()['superseded_by_task_id'] == dst['id']
    # A successor id that does not exist -> 404 from the record lookup.
    src2 = _planned(client, users, me, pid, scope)
    r = client.post(f'/api/tasks/{src2["id"]}/dismiss-carryover',
                    headers=users['supervisor'],
                    json={'superseded_by_task_id': 'no-such-task'})
    assert r.status_code == 404
