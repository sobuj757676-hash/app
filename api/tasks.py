"""Shared task endpoints. Planned work delegates to the authoritative unit service."""
from fastapi import APIRouter, HTTPException, Depends, Query
from models import TaskIn, TaskPatchIn, TaskTransitionIn, DefectTaskIn, Record
from routes import database, get, uid, now, save, log, log_change, is_worker, _project_with_stages
from auth import get_current_user, require_roles, OPS_ROLES
from notify import notify

router = APIRouter()
TRANSITIONS = {'todo': {'in_progress', 'cancelled'}, 'in_progress': {'todo', 'done', 'cancelled'}, 'done': set(), 'cancelled': set()}


def _may_transition(user, task, new_status):
    return user.get('role') in OPS_ROLES or (user.get('role') == 'worker' and user['id'] in task.get('assignees', []) and new_status != 'cancelled')


async def _resolve_assignees(aids):
    docs = []
    for aid in dict.fromkeys(aids or []):
        a = await database().users.find_one({'id': aid, 'active': True}, {'_id': 0, 'id': 1, 'name': 1, 'role': 1, 'worker_id': 1})
        if not a:
            raise HTTPException(404, 'Assignee not found or inactive')
        if a.get('worker_id'):
            worker = await database().workers.find_one({'id': a['worker_id']}, {'_id': 0, 'active': 1})
            if worker and not worker.get('active'):
                raise HTTPException(400, 'Worker is archived')
        docs.append(a)
    return docs


async def _validate_scope(pid, scope):
    from unit_workflow import workflow_signature
    stages = (await _project_with_stages(pid))['workflow_stages']
    if scope.stage_index >= len(stages):
        raise HTTPException(400, 'Scope stage is out of range')
    if not await database().blocks.find_one({'id': scope.block_id, 'project_id': pid}):
        raise HTTPException(400, 'Scope block does not belong to this project')
    ids = list(dict.fromkeys(scope.unit_ids))
    units = await database().units.find({'id': {'$in': ids}, 'project_id': pid}, {'_id': 0}).to_list(500)
    if len(units) != len(ids):
        raise HTTPException(400, 'Scope units must belong to this project')
    if any(u['block_id'] != scope.block_id or u['level'] != scope.level or u['stage'] != scope.stage_index for u in units):
        raise HTTPException(400, 'Scope must match the actual block, level and current stage of every unit')
    return {'block_id': scope.block_id, 'level': scope.level, 'stage_index': scope.stage_index, 'stage_id': stages[scope.stage_index]['id'], 'workflow_signature': workflow_signature(stages), 'unit_ids': ids}


async def _validate_defect_link(pid, defect_id):
    try:
        defect = await get('defects', defect_id)
    except HTTPException:
        raise HTTPException(400, 'Defect not found')
    if defect.get('project_id') != pid:
        raise HTTPException(400, 'Defect does not belong to this project')
    return defect


def _defect_summary(defect):
    return {k: defect[k] for k in ('id', 'title', 'status', 'severity')}


async def _attach_defects(docs):
    ids = {d.get('defect_id') for d in docs if d.get('defect_id')}
    found = await database().defects.find({'id': {'$in': list(ids)}}, {'_id': 0, 'id': 1, 'title': 1, 'status': 1, 'severity': 1}).to_list(10000) if ids else []
    summaries = {d['id']: _defect_summary(d) for d in found}
    for d in docs:
        d['defect'] = summaries.get(d.get('defect_id'))
    from planning import hydrate_tasks
    return await hydrate_tasks(docs)


async def _history(task_id, status, note, user):
    await database().tasks.update_one({'id': task_id}, {'$set': {'status': status, 'updated_at': now(), 'completed_at': now() if status == 'done' else None}, '$push': {'history': {'status': status, 'by_id': user['id'], 'by_name': user['name'], 'at': now(), 'note': (note or '')[:1000]}}})


async def _create_task(*, pid, defect_id, title, description, unit_id, assignees, priority, due_date, user, **kwargs):
    await get('projects', pid)
    people = await _resolve_assignees(assignees)
    unit_label = ''
    if unit_id:
        unit = await get('units', unit_id)
        if unit['project_id'] != pid:
            raise HTTPException(400, 'Unit does not belong to this project')
        unit_label = f'Blk {unit["block"]} · #{unit["level"]:02}-{unit["number"]}'
    defect = await _validate_defect_link(pid, defect_id) if defect_id else None
    doc = {'id': uid(), 'project_id': pid, 'unit_id': unit_id, 'unit_label': unit_label, 'defect_id': defect_id,
           'title': title.strip(), 'description': (description or '').strip(), 'assignees': [a['id'] for a in people], 'assignee_names': [a['name'] for a in people],
           'kind': 'adhoc', 'scope': None, 'completed_unit_ids': [], 'plan_date': None, 'status': 'todo', 'priority': priority,
           'due_date': due_date.isoformat() if due_date else None, 'created_by': {'id': user['id'], 'name': user['name']},
           'photos': [], 'history': [], 'completed_at': None, 'created_at': now(), 'updated_at': now()}
    saved = await save('tasks', doc)
    await log(pid, 'task', f'Task assigned · {title}', user)
    for a in people:
        await notify(a['id'], 'task_assigned', f'Task assigned: {title}', f'Priority: {priority}', {'page': 'tasks', 'id': doc['id']})
    saved['defect'] = _defect_summary(defect) if defect else None
    return saved


@router.post('/projects/{pid}/tasks', response_model=Record)
async def create_task(pid: str, data: TaskIn, user=Depends(require_roles(*OPS_ROLES))):
    if data.kind == 'planned':
        if not data.scope:
            raise HTTPException(400, 'A planned task must reference real units')
        scope = await _validate_scope(pid, data.scope)
        if not data.plan_date:
            raise HTTPException(400, 'A planned date is required')
        if data.completed_unit_ids:
            raise HTTPException(400, 'Completion must update real units. Use Complete selected after starting work.')
        from planning import PlanIn, create_grouped_plan
        result = await create_grouped_plan(pid, PlanIn(unit_ids=scope['unit_ids'], assignees=data.assignees, plan_date=data.plan_date,
                    priority='high' if data.priority == 'urgent' else data.priority, note=data.description,
                    expected_stages={i: scope['stage_index'] for i in scope['unit_ids']}), user)
        if not result['tasks']:
            raise HTTPException(409, result['errors'][0]['error'] if result['errors'] else 'No eligible units')
        return result['tasks'][0]
    if data.scope or data.completed_unit_ids:
        raise HTTPException(400, 'Unit work must be created as a planned task')
    return await _create_task(pid=pid, defect_id=data.defect_id, title=data.title, description=data.description, unit_id=data.unit_id, assignees=data.assignees, priority=data.priority, due_date=data.due_date, user=user)


@router.post('/defects/{id}/tasks', response_model=Record)
async def create_defect_task(id: str, data: DefectTaskIn, user=Depends(require_roles(*OPS_ROLES))):
    defect = await get('defects', id)
    return await _create_task(pid=defect['project_id'], defect_id=id, title=data.title, description=data.description, unit_id=None, assignees=data.assignees, priority=data.priority, due_date=data.due_date, user=user)


@router.get('/defects/{id}/tasks', response_model=list[Record])
async def list_defect_tasks(id: str, user=Depends(get_current_user)):
    defect = await get('defects', id)
    if is_worker(user) and defect.get('assigned_to') != user['id'] and defect.get('reported_by', {}).get('id') != user['id']:
        raise HTTPException(403, 'You do not have permission for this action')
    docs = await database().tasks.find({'defect_id': id}, {'_id': 0}).sort('created_at', -1).to_list(500)
    if is_worker(user):
        docs = [d for d in docs if user['id'] in d.get('assignees', [])]
    return await _attach_defects(docs)


@router.get('/projects/{pid}/tasks', response_model=list[Record])
async def list_tasks(pid: str, user=Depends(get_current_user), status: str | None = Query(None), priority: str | None = Query(None), assigned_to: str | None = Query(None)):
    await get('projects', pid)
    clauses = [{'project_id': pid}]
    if priority:
        clauses.append({'priority': priority})
    if assigned_to:
        clauses.append({'assignees': user['id'] if assigned_to == 'me' else assigned_to})
    if is_worker(user):
        clauses.append({'assignees': user['id']})
    docs = await database().tasks.find({'$and': clauses}, {'_id': 0}).sort('created_at', -1).to_list(5000)
    docs = await _attach_defects(docs)
    return [d for d in docs if not status or d['status'] == status]


@router.patch('/tasks/{id}', response_model=Record)
async def edit_task(id: str, data: TaskPatchIn, user=Depends(require_roles(*OPS_ROLES, 'worker'))):
    from planning import is_plan, task_lock, reschedule_work
    task = await get('tasks', id)
    dump = data.model_dump(exclude_unset=True)
    if is_worker(user):
        if user['id'] not in task.get('assignees', []) or set(dump) - {'completed_unit_ids'}:
            raise HTTPException(403, 'You do not have permission for this action')
    if 'completed_unit_ids' in dump:
        raise HTTPException(400, 'Completion must update real units. Use Complete selected after starting work.')
    if is_plan(task) and set(dump) & {'scope', 'kind', 'due_date'}:
        raise HTTPException(400, 'Unit scope is fixed. Use reschedule for remaining work or cancel and create a new plan.')
    if not is_plan(task) and set(dump) & {'scope', 'kind', 'plan_date'}:
        raise HTTPException(400, 'Create unit work from Unit Tracker')
    if 'plan_date' in dump:
        if len(dump) != 1 or not data.plan_date:
            raise HTTPException(400, 'Reschedule separately from other changes')
        return await reschedule_work(id, data.plan_date, user)
    async with task_lock(id) as task:
        if is_plan(task) and task['status'] == 'cancelled':
            raise HTTPException(400, 'This allocation is cancelled')
        patch = {}
        for k, v in dump.items():
            if k == 'assignees':
                people = await _resolve_assignees(v)
                if not people:
                    raise HTTPException(400, 'Task needs at least one assignee')
                patch.update(assignees=[a['id'] for a in people], assignee_names=[a['name'] for a in people])
            elif k == 'defect_id':
                if v:
                    await _validate_defect_link(task['project_id'], v)
                patch[k] = v
            elif k == 'due_date':
                patch[k] = v.isoformat() if v else None
            elif v is not None:
                patch[k] = v.strip() if isinstance(v, str) else v
        if patch:
            patch['updated_at'] = now()
            await database().tasks.update_one({'id': id}, {'$set': patch, '$unset': {'plan_group_key': ''}})
            await log_change(task['project_id'], 'task', f'Task updated · {task["title"]}', user, task, await get('tasks', id))
            for aid in set(patch.get('assignees', [])) - set(task.get('assignees', [])):
                await notify(aid, 'task_assigned', f'Task assigned: {task["title"]}', f'Reassigned by {user["name"]}', {'page': 'tasks', 'id': id})
    return (await _attach_defects([await get('tasks', id)]))[0]


@router.post('/tasks/{id}/transition', response_model=Record)
async def transition_task(id: str, data: TaskTransitionIn, user=Depends(require_roles(*OPS_ROLES, 'worker'))):
    from planning import is_plan, hydrate_tasks, task_lock, complete_work, today
    task = await get('tasks', id)
    new = data.status
    if not _may_transition(user, task, new):
        raise HTTPException(403, 'You do not have permission for this action')
    if is_plan(task) and new == 'done':
        result = await complete_work(id, task['scope']['unit_ids'], user, data.note)
        result['task']['completion_results'] = result['results']
        return result['task']
    async with task_lock(id) as task:
        if not _may_transition(user, task, new):
            raise HTTPException(403, 'You do not have permission for this action')
        effective = (await hydrate_tasks([task]))[0]
        if new not in TRANSITIONS.get(effective['status'], set()):
            raise HTTPException(400, f'Cannot move task from {effective["status"]} to {new}')
        if is_plan(task) and new == 'in_progress' and task.get('plan_date', '') > today():
            raise HTTPException(400, 'This work is planned for a future date. Reschedule it before starting.')
        await _history(id, new, data.note or f'Status → {new}', user)
        if new == 'cancelled':
            await database().tasks.update_one({'id': id}, {'$unset': {'active_unit_keys': '', 'plan_group_key': ''}})
        if new == 'done':
            creator = task.get('created_by', {}).get('id')
            if creator and creator != user['id']:
                await notify(creator, 'task_completed', f'Task completed: {task["title"]}', f'Completed by {user["name"]}', {'page': 'tasks', 'id': id})
        await log(task['project_id'], 'task', f'Task {new} · {task["title"]}', user)
    return (await _attach_defects([await get('tasks', id)]))[0]
