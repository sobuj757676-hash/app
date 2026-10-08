"""A dated allocation layer on existing tasks and real units. No shadow unit states."""
import hashlib
import json
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError
from models import BaseModel
from auth import get_current_user, require_roles, OPS_ROLES
from routes import database, get, uid, now, log, _project_with_stages
from unit_workflow import advance_unit, blocking_reason, workflow_signature

router = APIRouter()
LIVE = ('todo', 'in_progress')


def today():
    return datetime.now(ZoneInfo('Asia/Singapore')).date().isoformat()


def is_plan(t):
    return (t.get('kind') == 'planned' or bool(t.get('plan_date'))) and bool(t.get('scope'))


def allocation_key(pid, unit_id, stage_id):
    return f'{pid}:{unit_id}:{stage_id}'


class PlanIn(BaseModel):
    unit_ids: list[str] = Field(min_length=1, max_length=500)
    assignees: list[str] = Field(min_length=1, max_length=50)
    plan_date: date
    priority: str = Field(default='medium', pattern='^(low|medium|high)$')
    team_label: str = Field(default='', max_length=80)
    target: str = Field(default='', max_length=200)
    note: str = Field(default='', max_length=2000)
    expected_stages: dict[str, int] = Field(default_factory=dict)
    workflow_signature: str | None = None


class CompleteIn(BaseModel):
    unit_ids: list[str] = Field(min_length=1, max_length=500)
    note: str = Field(default='', max_length=1000)


class RescheduleIn(BaseModel):
    plan_date: date


@asynccontextmanager
async def task_lock(task_id):
    token = uid()
    lock = await database().tasks.find_one_and_update(
        {'id': task_id, '$or': [{'execution_lock': {'$exists': False}}, {'execution_lock.until': {'$lt': now()}}]},
        {'$set': {'execution_lock': {'token': token, 'until': (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()}}},
        return_document=ReturnDocument.AFTER)
    if not lock:
        raise HTTPException(409, 'This work is being updated. Please try again shortly.')
    try:
        lock.pop('_id', None)
        yield lock
    finally:
        await database().tasks.update_one({'id': task_id, 'execution_lock.token': token}, {'$unset': {'execution_lock': ''}})


async def project_context(pid):
    project = await _project_with_stages(pid)
    units = await database().units.find({'project_id': pid}, {'_id': 0}).to_list(100000)
    defects = await database().defects.find({'project_id': pid, 'severity': 'critical', 'status': {'$nin': ['verified', 'cancelled']}}, {'_id': 0, 'unit_id': 1, 'title': 1}).to_list(10000)
    return project, {u['id']: u for u in units}, {d['unit_id']: d['title'] for d in defects if d.get('unit_id')}


def project_task(task, project, units, blockers):
    t = dict(task)
    t.pop('execution_lock', None)
    t.pop('active_unit_keys', None)
    t.pop('plan_group_key', None)
    if not is_plan(t):
        return t
    s = t['scope']
    stages = project['workflow_stages']
    index = s.get('stage_index', -1)
    valid = 0 <= index < len(stages)
    changed = not valid or (s.get('workflow_signature') and s['workflow_signature'] != workflow_signature(stages)) or (s.get('stage_id') and valid and stages[index]['id'] != s['stage_id'])
    items, done = [], []
    for unit_id in s.get('unit_ids', []):
        u = units.get(unit_id)
        receipts = [h for h in (u or {}).get('history', []) if h.get('plan_task_id') == t['id']]
        error = None
        complete = bool(receipts) or bool(u and not changed and u.get('stage', 0) > index)
        if complete:
            done.append(unit_id)
        elif not u:
            error = 'Unit no longer exists'
        elif changed:
            error = 'Workflow changed. Review and replan remaining work.'
        elif u.get('block_id') != s.get('block_id') or u.get('level') != s.get('level'):
            error = 'Unit location changed. Review and replan remaining work.'
        elif u.get('stage') != index:
            error = 'Unit stage changed. Review and replan remaining work.'
        elif u.get('rto') == 'rework':
            error = 'RTO rework must be resolved through inspections'
        elif valid and stages[index].get('requires_rto'):
            error = 'RTO approval required through inspections'
        elif unit_id in blockers:
            error = 'Blocked by critical defect: ' + blockers[unit_id]
        item = {'unit_id': unit_id, 'number': (u or {}).get('number', '?'), 'level': (u or {}).get('level', s.get('level')), 'complete': complete, 'error': error, 'external': complete and not bool(receipts), 'completed_date': receipts[-1].get('plan_date') if receipts else None}
        items.append(item)
    remaining = [i['unit_id'] for i in items if not i['complete']]
    status = t.get('status', 'todo')
    if not remaining and items and status != 'cancelled':
        status = 'done'
    elif remaining and status == 'done':
        # Legacy task 'done' never authorizes stage advancement.
        status = 'in_progress'
    t.update(status=status, completed_unit_ids=done, remaining_unit_ids=remaining, unit_work=items,
             attention_count=sum(bool(i['error']) for i in items if not i['complete']),
             legacy_unverified=bool(set(task.get('completed_unit_ids', [])) - set(done)) or (task.get('status') == 'done' and bool(remaining)))
    t['work_name'] = stages[index]['name'] if valid and not changed else 'Work needs review'
    t['work_name_key'] = stages[index].get('name_key') if valid and not changed else None
    t['next_stage'] = stages[index + 1] if valid and index + 1 < len(stages) else None
    prior_done = {unit_id for h in t.get('schedule_history', []) for unit_id in h.get('completed_unit_ids', [])}
    t['current_unit_ids'] = [i for i in s.get('unit_ids', []) if i not in prior_done]
    return t


async def hydrate_tasks(tasks, context=None):
    if not tasks:
        return tasks
    contexts = {}
    result = []
    for t in tasks:
        if not is_plan(t):
            result.append(t)
            continue
        pid = t['project_id']
        if pid not in contexts:
            contexts[pid] = context or await project_context(pid)
        result.append(project_task(t, *contexts[pid]))
    user_ids = list({aid for t in tasks if is_plan(t) for aid in t.get('assignees', [])})
    people = {p['id']: p for p in await database().users.find({'id': {'$in': user_ids}}, {'_id': 0, 'id': 1, 'name': 1, 'active': 1, 'worker_id': 1}).to_list(10000)} if user_ids else {}
    worker_ids = [p['worker_id'] for p in people.values() if p.get('worker_id')]
    workers = {w['id']: w for w in await database().workers.find({'id': {'$in': worker_ids}}, {'_id': 0, 'id': 1, 'active': 1}).to_list(10000)} if worker_ids else {}
    attendance = await database().attendance.find({'worker_id': {'$in': worker_ids}, 'status': {'$in': ['absent', 'leave']}, 'date': {'$in': list({t.get('plan_date') for t in tasks if is_plan(t)})}}, {'_id': 0, 'worker_id': 1, 'date': 1, 'status': 1}).to_list(10000) if worker_ids else []
    for t in result:
        if not is_plan(t):
            continue
        warnings = []
        for aid in t.get('assignees', []):
            p = people.get(aid)
            if not p or not p.get('active') or (p.get('worker_id') in workers and not workers[p['worker_id']].get('active')):
                warnings.append(f"{p['name'] if p else 'Assigned worker'}: inactive; reassign remaining work")
            elif any(a['worker_id'] == p.get('worker_id') and a['date'] == t.get('plan_date') for a in attendance):
                warnings.append(f"{p['name']}: absent or on leave on planned date")
        if not t.get('assignees'):
            warnings.append('No crew assigned; choose an active worker')
        t['crew_warnings'] = warnings
    return result


async def reconcile(pid):
    """Recover task allocation bookkeeping from real units, including interrupted responses."""
    context = await project_context(pid)
    tasks = await database().tasks.find({'project_id': pid, 'kind': 'planned'}, {'_id': 0}).to_list(10000)
    projected = await hydrate_tasks(tasks, context)
    for raw, t in zip(tasks, projected):
        if raw.get('execution_lock'):
            continue
        if raw.get('plan_version') != 2:
            continue  # preserve legacy data until deliberate action
        patch, unset = {}, {}
        if t['status'] != raw['status']:
            patch['status'] = t['status']
        keys = [allocation_key(pid, i, t['scope']['stage_id']) for i in t['remaining_unit_ids']] if t['status'] in LIVE else []
        if keys:
            patch['active_unit_keys'] = keys
        else:
            unset.update(active_unit_keys='', plan_group_key='')
        update = {}
        if patch:
            update['$set'] = patch
        if unset:
            update['$unset'] = unset
        if update:
            await database().tasks.update_one({'id': t['id'], 'updated_at': raw.get('updated_at'), 'execution_lock': {'$exists': False}}, update)
    return context, projected


@router.get('/projects/{pid}/planning')
async def planning_state(pid: str, user=Depends(require_roles(*OPS_ROLES))):
    context, tasks = await reconcile(pid)
    project, units, blockers = context
    stages = project['workflow_stages']
    allocations = {}
    for t in tasks:
        if t['status'] in LIVE:
            for unit_id in t['remaining_unit_ids']:
                allocations.setdefault(unit_id, []).append({'task_id': t['id'], 'plan_date': t.get('plan_date'), 'stage_index': t['scope']['stage_index']})
    result = []
    for u in units.values():
        stage = u['stage']
        error = 'Unit is already complete' if stage >= len(stages) else 'RTO rework must be resolved through inspections' if u.get('rto') == 'rework' else 'RTO approval required through inspections' if stages[stage].get('requires_rto') else ('Blocked by critical defect: ' + blockers[u['id']]) if u['id'] in blockers else None
        planned = allocations.get(u['id'], [])
        result.append({'unit_id': u['id'], 'ready': not error, 'reason': error, 'allocations': planned, 'unplanned': not planned})
    return {'units': result, 'workflow_signature': workflow_signature(stages)}


async def create_grouped_plan(pid, data, user):
    from tasks import _resolve_assignees
    from notify import notify
    people = await _resolve_assignees(data.assignees)
    if not people:
        raise HTTPException(400, 'Choose at least one worker')
    if data.plan_date.isoformat() < today():
        raise HTTPException(400, 'Choose today or a future date for new work')
    context, tasks = await reconcile(pid)
    project, units, blockers = context
    stages = project['workflow_stages']
    signature = workflow_signature(stages)
    if data.workflow_signature and data.workflow_signature != signature:
        raise HTTPException(409, 'Workflow changed. Refresh Unit Tracker and select units again.')
    groups, errors = {}, []
    for unit_id in dict.fromkeys(data.unit_ids):
        u = units.get(unit_id)
        error = None
        if not u:
            error = 'Unit does not belong to this project'
        elif unit_id in data.expected_stages and data.expected_stages[unit_id] != u['stage']:
            error = 'Unit stage changed. Select it again from Unit Tracker.'
        else:
            error = await blocking_reason(u, stages)
        if error:
            errors.append({'unit_id': unit_id, 'error': error})
            continue
        k = (u['block_id'], u['level'], u['stage'])
        groups.setdefault(k, []).append(u)
    saved = []
    for (block_id, level, stage), us in groups.items():
        aids = sorted(a['id'] for a in people)
        raw_key = [pid, block_id, level, stages[stage]['id'], signature, data.plan_date.isoformat(), aids, data.priority, data.team_label, data.target, data.note]
        group_key = hashlib.sha256(json.dumps(raw_key).encode()).hexdigest()
        existing = await database().tasks.find_one({'plan_group_key': group_key}, {'_id': 0})
        ids = [u['id'] for u in us]
        conflicts = {i for t in tasks if t['status'] in LIVE and (not existing or t['id'] != existing['id']) for i in t['remaining_unit_ids']}
        for i in ids:
            if i in conflicts:
                errors.append({'unit_id': i, 'error': 'Already allocated. Open the existing plan to reschedule or reassign.'})
        ids = [i for i in ids if i not in conflicts]
        if not ids:
            continue
        keys = [allocation_key(pid, i, stages[stage]['id']) for i in ids]
        try:
            if existing:
                async with task_lock(existing['id']) as current:
                    if current.get('status') not in LIVE:
                        raise HTTPException(409, 'Plan changed. Please try again.')
                    await database().tasks.update_one({'id': current['id']}, {'$addToSet': {'scope.unit_ids': {'$each': ids}, 'active_unit_keys': {'$each': keys}}, '$set': {'updated_at': now()}})
                saved.append(await get('tasks', existing['id']))
            else:
                stamp = now()
                doc = {'id': uid(), 'project_id': pid, 'kind': 'planned', 'plan_version': 2,
                       'scope': {'block_id': block_id, 'level': level, 'stage_index': stage, 'stage_id': stages[stage]['id'], 'workflow_signature': signature, 'unit_ids': ids},
                       'title': f'{stages[stage]["name"]} · Blk {us[0]["block"]} · L{level}',
                       'description': data.note, 'team_label': data.team_label, 'target': data.target,
                       'plan_date': data.plan_date.isoformat(), 'due_date': data.plan_date.isoformat(),
                       'assignees': aids, 'assignee_names': [next(p['name'] for p in people if p['id'] == a) for a in aids],
                       'priority': data.priority, 'status': 'todo', 'unit_id': None, 'unit_label': '', 'defect_id': None,
                       'photos': [], 'history': [], 'schedule_history': [], 'created_by': {'id': user['id'], 'name': user['name']},
                       'completed_at': None, 'created_at': stamp, 'updated_at': stamp, 'plan_group_key': group_key, 'active_unit_keys': keys}
                await database().tasks.insert_one(dict(doc))
                saved.append(doc)
                for a in people:
                    await notify(a['id'], 'task_assigned', f'Planned work: {doc["title"]}', f'{len(ids)} units · {doc["plan_date"]}', {'page': 'tasks', 'id': doc['id']})
        except DuplicateKeyError:
            # Another request may have just created the identical group. A retry
            # merges into it; never silently advances or creates duplicate allocation.
            errors.extend({'unit_id': i, 'error': 'Already allocated by another request. Refresh to see the plan.'} for i in ids)
    if saved:
        await log(pid, 'task', f'{len(saved)} work group(s) planned for {data.plan_date.isoformat()}', user)
    return {'tasks': await hydrate_tasks(saved), 'errors': errors}


@router.post('/projects/{pid}/plans')
async def create_plan(pid: str, data: PlanIn, user=Depends(require_roles(*OPS_ROLES))):
    return await create_grouped_plan(pid, data, user)


def authorize_execution(task, user):
    if user.get('role') not in OPS_ROLES and not (user.get('role') == 'worker' and user['id'] in task.get('assignees', [])):
        raise HTTPException(403, 'You do not have permission for this action')
    if not is_plan(task):
        raise HTTPException(400, 'This action requires a unit plan')


async def complete_work(task_id, ids, user, note=''):
    task = await get('tasks', task_id)
    authorize_execution(task, user)
    ids = list(dict.fromkeys(ids))
    if not ids or any(i not in task['scope']['unit_ids'] for i in ids):
        raise HTTPException(400, 'Choose units from this work group only')
    if task.get('plan_date', '') > today():
        raise HTTPException(400, 'This work is planned for a future date. Reschedule it before starting.')
    results = []
    async with task_lock(task_id) as task:
        authorize_execution(task, user)
        if task.get('plan_date', '') > today():
            raise HTTPException(400, 'This work is planned for a future date. Reschedule it before starting.')
        projected = (await hydrate_tasks([task]))[0]
        if task['status'] == 'cancelled':
            raise HTTPException(400, 'This allocation is cancelled')
        if projected['status'] == 'todo':
            raise HTTPException(400, 'Start work before completing units')
        for unit_id in ids:
            if unit_id in projected['completed_unit_ids']:
                results.append({'unit_id': unit_id, 'ok': True, 'already_complete': True})
                continue
            try:
                await advance_unit(unit_id, task['scope']['stage_index'], user, note or 'Completed from Daily Plan', task)
                results.append({'unit_id': unit_id, 'ok': True})
            except HTTPException as e:
                results.append({'unit_id': unit_id, 'ok': False, 'error': e.detail})
        projected = (await hydrate_tasks([await get('tasks', task_id)]))[0]
        new_status = 'done' if not projected['remaining_unit_ids'] else 'in_progress'
        patch = {'status': new_status, 'updated_at': now(), 'completed_at': now() if new_status == 'done' else None}
        unset = {'plan_group_key': ''}
        if projected['remaining_unit_ids'] and task.get('plan_version') == 2:
            patch['active_unit_keys'] = [allocation_key(task['project_id'], i, task['scope']['stage_id']) for i in projected['remaining_unit_ids']]
        else:
            unset['active_unit_keys'] = ''
        await database().tasks.update_one({'id': task_id}, {'$set': patch, '$unset': unset, '$push': {'history': {'status': new_status, 'by_id': user['id'], 'by_name': user['name'], 'at': now(), 'note': f'{sum(r["ok"] for r in results)} unit(s) confirmed'}}})
    return {'task': (await hydrate_tasks([await get('tasks', task_id)]))[0], 'results': results}


@router.post('/tasks/{id}/complete-units')
async def complete_units(id: str, data: CompleteIn, user=Depends(require_roles(*OPS_ROLES, 'worker'))):
    return await complete_work(id, data.unit_ids, user, data.note)


async def reschedule_work(task_id, plan_date, user):
    new_date = plan_date.isoformat()
    if new_date < today():
        raise HTTPException(400, 'Choose today or a future date')
    async with task_lock(task_id) as task:
        if not is_plan(task):
            raise HTTPException(400, 'This action requires a unit plan')
        t = (await hydrate_tasks([task]))[0]
        if t['status'] not in LIVE or not t['remaining_unit_ids']:
            raise HTTPException(400, 'No unfinished work to reschedule')
        if task['plan_date'] != new_date:
            prior_done = {i for h in task.get('schedule_history', []) for i in h.get('completed_unit_ids', [])}
            entry = {'from_date': task['plan_date'], 'to_date': new_date, 'at': now(), 'by_id': user['id'], 'by_name': user['name'],
                     'completed_unit_ids': [i for i in t['completed_unit_ids'] if i not in prior_done], 'remaining_unit_ids': t['remaining_unit_ids']}
            await database().tasks.update_one({'id': task_id}, {'$set': {'plan_date': new_date, 'due_date': new_date, 'status': 'todo', 'updated_at': now()}, '$unset': {'plan_group_key': ''}, '$push': {'schedule_history': entry}})
            await log(task['project_id'], 'task', f'Rescheduled {len(t["remaining_unit_ids"])} remaining units from {task["plan_date"]} to {new_date}', user)
    return (await hydrate_tasks([await get('tasks', task_id)]))[0]


@router.post('/tasks/{id}/reschedule')
async def reschedule(id: str, data: RescheduleIn, user=Depends(require_roles(*OPS_ROLES))):
    return await reschedule_work(id, data.plan_date, user)
