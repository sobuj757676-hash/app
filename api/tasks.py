"""Task assignment endpoints."""
from fastapi import APIRouter, HTTPException, Depends, Query
from models import TaskIn, TaskPatchIn, TaskTransitionIn, DefectTaskIn, Record
from routes import database, get, uid, now, save, log, log_change, is_worker
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
        return task.get('assigned_to') == user.get('id') and new_status != 'cancelled'
    return False


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
                       assignee_id: str | None, priority: str,
                       due_date, user: dict) -> dict:
    """Shared task creation used by both POST endpoints. assignee_id optional."""
    await get('projects', pid)
    assignee = None
    if assignee_id:
        assignee = await database().users.find_one({'id': assignee_id, 'active': True},
                                                   {'_id': 0, 'id': 1, 'name': 1})
        if not assignee:
            raise HTTPException(404, 'Assignee not found or inactive')
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
        'assigned_to': assignee['id'] if assignee else None,
        'assigned_to_name': assignee['name'] if assignee else '',
        'status': 'todo', 'priority': priority,
        'due_date': due_date.isoformat() if due_date else None,
        'created_by': {'id': user['id'], 'name': user['name']},
        'photos': [], 'history': [], 'completed_at': None,
        'created_at': now(), 'updated_at': now(),
    }
    await log(pid, 'task',
              f'Task assigned · {title}' + (f' → {assignee["name"]}' if assignee else ''), user)
    if assignee:
        await notify(assignee['id'], 'task_assigned',
                     f'Task assigned: {title}',
                     f'Priority: {priority}' + (f' · due {due_date.isoformat()}' if due_date else ''),
                     {'page': 'tasks', 'id': doc['id']})
    saved = await save('tasks', doc)
    saved['defect'] = _defect_summary(defect) if defect else None
    return saved


@router.post('/projects/{pid}/tasks', response_model=Record)
async def create_task(pid: str, data: TaskIn,
                      user: dict = Depends(require_roles('admin', 'manager', 'engineer', 'supervisor'))):
    return await _create_task(pid=pid, defect_id=data.defect_id, title=data.title,
                              description=data.description, unit_id=data.unit_id,
                              assignee_id=data.assigned_to, priority=data.priority,
                              due_date=data.due_date, user=user)


@router.post('/defects/{id}/tasks', response_model=Record)
async def create_defect_task(id: str, data: DefectTaskIn,
                             user: dict = Depends(require_roles('admin', 'manager', 'engineer', 'supervisor'))):
    """One-tap follow-up task from a defect. project_id is taken from the defect."""
    defect = await get('defects', id)
    return await _create_task(pid=defect['project_id'], defect_id=id, title=data.title,
                              description=data.description, unit_id=None,
                              assignee_id=data.assigned_to, priority=data.priority,
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
        clauses.append({'assigned_to': user['id']})
    elif assigned_to:
        clauses.append({'assigned_to': assigned_to})
    if is_worker(user):
        clauses.append({'assigned_to': user['id']})
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
        if k == 'due_date':
            patch[k] = v.isoformat() if v else None
        elif k == 'defect_id':
            continue  # handled below (None clears the link)
        elif v is not None:
            patch[k] = v
    if 'defect_id' in dump:
        new_did = dump['defect_id']
        if new_did:
            await _validate_defect_link(task['project_id'], new_did)
        patch['defect_id'] = new_did
    if 'assigned_to' in patch:
        assignee = await database().users.find_one({'id': patch['assigned_to'], 'active': True},
                                                   {'_id': 0, 'id': 1, 'name': 1})
        if not assignee:
            raise HTTPException(404, 'Assignee not found or inactive')
        patch['assigned_to_name'] = assignee['name']
        if assignee['id'] != task['assigned_to']:
            await notify(assignee['id'], 'task_assigned',
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
