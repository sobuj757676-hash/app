"""Task assignment endpoints."""
from fastapi import APIRouter, HTTPException, Depends, Query
from models import TaskIn, TaskPatchIn, TaskTransitionIn, DefectTaskIn, Record
from routes import database, get, uid, now, save, log, log_change, is_worker, _project_with_stages
from auth import get_current_user, require_roles, OPS_ROLES
from notify import notify

router = APIRouter()

# Server-enforced status machine: todo→in_progress→done, any→cancelled.
TRANSITIONS = {
    'todo': {'in_progress', 'cancelled'},
    'in_progress': {'todo', 'done', 'cancelled'},
    'done': set(),
    'cancelled': set(),
}


def _may_transition(user: dict, task: dict, new_status: str) -> bool:
    if user.get('role') in ('admin', 'manager', 'engineer', 'supervisor'):
        return True
    if user.get('role') == 'worker':
        return user.get('id') in task.get('assignees', []) and new_status != 'cancelled'
    return False


async def _resolve_assignees(aids: list[str] | None) -> list[dict]:
    """Validate assignee ids (deduped, order preserved); all must be active
    users. Raises 404 naming the bad id."""
    docs = []
    for aid in dict.fromkeys(aids or []):
        a = await database().users.find_one({'id': aid, 'active': True},
                                            {'_id': 0, 'id': 1, 'name': 1})
        if not a:
            raise HTTPException(404, f'Assignee not found or inactive: {aid}')
        docs.append(a)
    return docs


async def _validate_scope(pid: str, scope) -> dict:
    """Validate a planned-task scope against the project; return the stored dict."""
    stages = (await _project_with_stages(pid)).get('workflow_stages') or []
    if scope.stage_index >= len(stages):
        raise HTTPException(400, 'Scope stage is out of range')
    block = await database().blocks.find_one({'id': scope.block_id, 'project_id': pid},
                                             {'_id': 0, 'id': 1})
    if not block:
        raise HTTPException(400, 'Scope block does not belong to this project')
    unit_ids = list(dict.fromkeys(scope.unit_ids))
    n = await database().units.count_documents(
        {'id': {'$in': unit_ids}, 'project_id': pid})
    if n != len(unit_ids):
        raise HTTPException(400, 'Scope units must belong to this project')
    return {'block_id': scope.block_id, 'level': scope.level,
            'stage_index': scope.stage_index, 'unit_ids': unit_ids}


async def _validate_defect_link(pid: str, defect_id: str) -> dict:
    """Fetch the defect and ensure it belongs to this project. Raises 400."""
    try:
        defect = await get('defects', defect_id)
    except HTTPException as e:
        if e.status_code == 404:
            raise HTTPException(400, 'Defect not found')
        raise
    if defect.get('project_id') != pid:
        raise HTTPException(400, 'Defect does not belong to this project')
    return defect


def _defect_summary(defect: dict) -> dict:
    return {'id': defect['id'], 'title': defect['title'],
            'status': defect['status'], 'severity': defect['severity']}


async def _attach_defects(docs: list[dict]) -> list[dict]:
    """Embed defect:{id,title,status,severity} on tasks that link one. Batched."""
    ids = {d.get('defect_id') for d in docs if d.get('defect_id')}
    summaries = {}
    if ids:
        found = await database().defects.find(
            {'id': {'$in': list(ids)}},
            {'_id': 0, 'id': 1, 'title': 1, 'status': 1, 'severity': 1}).to_list(1000)
        summaries = {d['id']: _defect_summary(d) for d in found}
    for d in docs:
        did = d.get('defect_id')
        d['defect'] = summaries.get(did) if did else None
    return docs


async def _history(task_id: str, status: str, note: str, user: dict):
    entry = {'status': status, 'by_id': user['id'], 'by_name': user['name'],
             'at': now(), 'note': (note or '')[:1000]}
    await database().tasks.update_one(
        {'id': task_id},
        {'$set': {'status': status, 'updated_at': now(),
                  'completed_at': now() if status == 'done' else None},
         '$push': {'history': entry}})


async def _create_task(*, pid: str, defect_id: str | None, title: str,
                       description: str | None, unit_id: str | None,
                       assignees: list[str] | None, priority: str,
                       due_date, user: dict,
                       kind: str = 'adhoc', scope: dict | None = None,
                       plan_date=None) -> dict:
    """Shared task creation used by both POST endpoints. assignees optional
    (empty = unassigned). All assignees are notified."""
    await get('projects', pid)
    people = await _resolve_assignees(assignees)
    unit_label = ''
    if unit_id:
        unit = await get('units', unit_id)
        if unit['project_id'] != pid:
            raise HTTPException(400, 'Unit does not belong to this project')
        unit_label = f'Blk {unit["block"]} · #{unit["level"]:02}-{unit["number"]}'
    defect = await _validate_defect_link(pid, defect_id) if defect_id else None
    doc = {
        'id': uid(), 'project_id': pid, 'unit_id': unit_id, 'unit_label': unit_label,
        'defect_id': defect_id,
        'title': title.strip(), 'description': (description or '').strip(),
        'assignees': [a['id'] for a in people],
        'assignee_names': [a['name'] for a in people],
        'kind': kind, 'scope': scope,
        'plan_date': plan_date.isoformat() if plan_date else None,
        'status': 'todo', 'priority': priority,
        'due_date': due_date.isoformat() if due_date else None,
        'created_by': {'id': user['id'], 'name': user['name']},
        'photos': [], 'history': [], 'completed_at': None,
        'created_at': now(), 'updated_at': now(),
    }
    await log(pid, 'task',
              f'Task assigned · {title}' + (f" → {', '.join(a['name'] for a in people)}" if people else ''), user)
    for a in people:
        await notify(a['id'], 'task_assigned',
                     f'Task assigned: {title}',
                     f'Priority: {priority}' + (f' · due {due_date.isoformat()}' if due_date else ''),
                     {'page': 'tasks', 'id': doc['id']})
    saved = await save('tasks', doc)
    saved['defect'] = _defect_summary(defect) if defect else None
    return saved


@router.post('/projects/{pid}/tasks', response_model=Record)
async def create_task(pid: str, data: TaskIn,
                      user: dict = Depends(require_roles('admin', 'manager', 'engineer', 'supervisor'))):
    if data.kind == 'planned' and is_worker(user):
        raise HTTPException(403, 'You do not have permission for this action')
    scope = await _validate_scope(pid, data.scope) if data.scope else None
    return await _create_task(pid=pid, defect_id=data.defect_id, title=data.title,
                              description=data.description, unit_id=data.unit_id,
                              assignees=data.assignees, priority=data.priority,
                              due_date=data.due_date, user=user,
                              kind=data.kind, scope=scope, plan_date=data.plan_date)


@router.post('/defects/{id}/tasks', response_model=Record)
async def create_defect_task(id: str, data: DefectTaskIn,
                             user: dict = Depends(require_roles('admin', 'manager', 'engineer', 'supervisor'))):
    """One-tap follow-up task from a defect. project_id is taken from the defect."""
    defect = await get('defects', id)
    return await _create_task(pid=defect['project_id'], defect_id=id, title=data.title,
                              description=data.description, unit_id=None,
                              assignees=data.assignees, priority=data.priority,
                              due_date=data.due_date, user=user)


@router.get('/defects/{id}/tasks', response_model=list[Record])
async def list_defect_tasks(id: str, user: dict = Depends(get_current_user)):
    """Tasks linked to a defect, newest first. Same visibility as the defect itself."""
    defect = await get('defects', id)
    if is_worker(user):
        mine = defect.get('assigned_to') == user['id'] \
            or defect.get('reported_by', {}).get('id') == user['id']
        if not mine:
            raise HTTPException(403, 'You do not have permission for this action')
    docs = await database().tasks.find({'defect_id': id}, {'_id': 0}) \
        .sort('created_at', -1).to_list(500)
    return await _attach_defects(docs)


@router.get('/projects/{pid}/tasks', response_model=list[Record])
async def list_tasks(pid: str, user: dict = Depends(get_current_user),
                     status: str | None = Query(None),
                     priority: str | None = Query(None),
                     assigned_to: str | None = Query(None)):
    await get('projects', pid)
    clauses: list[dict] = [{'project_id': pid}]
    if status:
        clauses.append({'status': status})
    if priority:
        clauses.append({'priority': priority})
    if assigned_to == 'me':
        clauses.append({'assignees': user['id']})
    elif assigned_to:
        clauses.append({'assignees': assigned_to})
    if is_worker(user):
        clauses.append({'assignees': user['id']})
    filt = clauses[0] if len(clauses) == 1 else {'$and': clauses}
    docs = await database().tasks.find(filt, {'_id': 0}).sort('created_at', -1).to_list(5000)
    return await _attach_defects(docs)


@router.patch('/tasks/{id}', response_model=Record)
async def edit_task(id: str, data: TaskPatchIn,
                    user: dict = Depends(require_roles('admin', 'manager', 'engineer', 'supervisor'))):
    task = await get('tasks', id)
    dump = data.model_dump(exclude_unset=True)
    patch = {}
    for k, v in dump.items():
        if k in ('due_date', 'plan_date'):
            patch[k] = v.isoformat() if v else None
        elif k == 'defect_id':
            continue  # handled below (None clears the link)
        elif k == 'assignees':
            continue  # handled below (validated + denormalized)
        elif k == 'scope':
            patch[k] = await _validate_scope(task['project_id'], data.scope) if v is not None else None
        elif v is not None:
            patch[k] = v
    if 'defect_id' in dump:
        new_did = dump['defect_id']
        if new_did:
            await _validate_defect_link(task['project_id'], new_did)
        patch['defect_id'] = new_did
    if 'assignees' in dump:
        people = await _resolve_assignees(dump['assignees'])
        if not people:
            raise HTTPException(400, 'Task needs at least one assignee')
        patch['assignees'] = [a['id'] for a in people]
        patch['assignee_names'] = [a['name'] for a in people]
        old_ids = set(task.get('assignees') or [])
        for a in people:
            if a['id'] not in old_ids:
                await notify(a['id'], 'task_assigned',
                             f'Task assigned: {task["title"]}',
                             f'Reassigned by {user["name"]}',
                             {'page': 'tasks', 'id': id})
    if 'title' in patch:
        patch['title'] = patch['title'].strip()
    if 'description' in patch:
        patch['description'] = patch['description'].strip()
    if patch:
        patch['updated_at'] = now()
        await database().tasks.update_one({'id': id}, {'$set': patch})
        await log_change(task['project_id'], 'task', f'Task updated · {task["title"]}',
                         user, task, await get('tasks', id))
    return (await _attach_defects([await get('tasks', id)]))[0]


@router.post('/tasks/{id}/transition', response_model=Record)
async def transition_task(id: str, data: TaskTransitionIn,
                          user: dict = Depends(require_roles(*OPS_ROLES, 'worker'))):
    task = await get('tasks', id)
    new = data.status
    if new not in TRANSITIONS.get(task['status'], set()):
        raise HTTPException(400, f'Cannot move task from {task["status"]} to {new}')
    if not _may_transition(user, task, new):
        raise HTTPException(403, 'You do not have permission for this action')
    await _history(id, new, data.note or f'Status → {new}', user)
    if new == 'done':
        creator_id = task.get('created_by', {}).get('id')
        if creator_id and creator_id != user['id']:
            await notify(creator_id, 'task_completed',
                         f'Task completed: {task["title"]}',
                         f'Completed by {user["name"]}',
                         {'page': 'tasks', 'id': id})
    await log(task['project_id'], 'task', f'Task {new} · {task["title"]}', user)
    return (await _attach_defects([await get('tasks', id)]))[0]
