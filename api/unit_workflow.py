"""Authoritative, one-stage unit advancement shared by Tracker and planned work."""
import hashlib
import json
from fastapi import HTTPException
from routes import database, get, now, log, _project_with_stages


def workflow_signature(stages):
    # Labels may change without changing the meaning of a planned stage.
    return hashlib.sha256(json.dumps([(s['id'], bool(s.get('requires_rto'))) for s in stages]).encode()).hexdigest()[:20]


async def blocking_reason(unit, stages, *, completion=False):
    stage = unit.get('stage', 0)
    if stage >= len(stages):
        return 'Unit is already complete'
    if unit.get('rto') == 'rework':
        return 'RTO rework must be resolved through inspections'
    if stages[stage].get('requires_rto'):
        return 'RTO approval required through inspections'
    blocker = await database().defects.find_one({'unit_id': unit['id'], 'severity': 'critical', 'status': {'$nin': ['verified', 'cancelled']}}, {'_id': 0, 'title': 1})
    if blocker:
        return f"Blocked by critical defect: {blocker['title']}"
    if completion and stage == len(stages) - 1:
        tests = await database().tests.find({'unit_id': unit['id']}, {'_id': 0}).sort('created_at', 1).to_list(10000)
        latest = {t['point_id']: t for t in tests}
        if not unit.get('points') or any(latest.get(p['id'], {}).get('result') != 'pass' for p in unit['points']):
            return 'A passing test is required for every point'
    return None


async def advance_unit(unit_id, expected_stage, user, note='', plan_task=None):
    unit = await get('units', unit_id)
    if plan_task and any(h.get('plan_task_id') == plan_task['id'] for h in unit.get('history', [])):
        return unit  # durable idempotency receipt, even after later stage advances
    stages = (await _project_with_stages(unit['project_id']))['workflow_stages']
    if unit.get('stage') != expected_stage:
        raise HTTPException(409, 'Unit changed. Refresh and retry.')
    if plan_task:
        s = plan_task['scope']
        if unit.get('project_id') != plan_task['project_id'] or unit.get('block_id') != s['block_id'] or unit.get('level') != s['level']:
            raise HTTPException(409, 'Unit location changed. Review this plan in Unit Tracker.')
        if s.get('workflow_signature') and s['workflow_signature'] != workflow_signature(stages):
            raise HTTPException(409, 'Workflow changed. Cancel the remaining allocation and plan it again.')
        if s.get('stage_id') and (expected_stage >= len(stages) or stages[expected_stage]['id'] != s['stage_id']):
            raise HTTPException(409, 'Planned stage changed. Review this plan in Unit Tracker.')
    error = await blocking_reason(unit, stages, completion=True)
    if error:
        raise HTTPException(400, error)
    receipt = {'stage': expected_stage, 'to_stage': expected_stage + 1, 'stage_id': stages[expected_stage]['id'], 'note': note, 'at': now(), 'by_id': user['id'], 'by': user['name']}
    if plan_task:
        receipt.update(plan_task_id=plan_task['id'], plan_date=plan_task['plan_date'])
    query = {'id': unit_id, 'stage': expected_stage, 'updated_at': unit.get('updated_at'), 'rto': unit.get('rto', 'none')}
    changed = await database().units.update_one(query, {'$set': {'stage': expected_stage + 1, 'sample': False, 'updated_at': now()}, '$push': {'history': receipt}})
    if not changed.modified_count:
        current = await get('units', unit_id)
        if plan_task and any(h.get('plan_task_id') == plan_task['id'] for h in current.get('history', [])):
            return current
        raise HTTPException(409, 'Unit changed. Refresh and retry.')
    await log(unit['project_id'], 'stage', f'Blk {unit["block"]} · #{unit["level"]:02}-{unit["number"]} · {stages[expected_stage]["name"]} completed', user)
    return await get('units', unit_id)
