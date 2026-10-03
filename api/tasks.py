"""Task assignment endpoints."""
from fastapi import APIRouter, HTTPException, Depends, Query
from models import TaskIn, TaskPatchIn, TaskTransitionIn, Record
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


async def _history(task_id: str, status: str, note: str, user: dict):
    entry = {'status': status, 'by_id': user['id'], 'by_name': user['name'],
             'at': now(), 'note': (note or '')[:1000]}
    await database().tasks.update_one(
        {'id': task_id},
        {'$set': {'status': status, 'updated_at': now(),
                  'completed_at': now() if status == 'done' else None},
         '$push': {'history': entry}})


@router.post('/projects/{pid}/tasks', response_model=Record)
async def create_task(pid: str, data: TaskIn,
                      user: dict = Depends(require_roles('admin', 'manager', 'engineer', 'supervisor'))):
    await get('projects', pid)
    assignee = await database().users.find_one({'id': data.assigned_to, 'active': True},
                                               {'_id': 0, 'id': 1, 'name': 1})
    if not assignee:
        raise HTTPException(404, 'Assignee not found or inactive')
    unit_label = ''
    if data.unit_id:
        unit = await get('units', data.unit_id)
        if unit['project_id'] != pid:
            raise HTTPException(400, 'Unit does not belong to this project')
        unit_label = f'Blk {unit["block"]} · #{unit["level"]:02}-{unit["number"]}'
    doc = {
        'id': uid(), 'project_id': pid, 'unit_id': data.unit_id, 'unit_label': unit_label,
        'title': data.title.strip(), 'description': (data.description or '').strip(),
        'assigned_to': assignee['id'], 'assigned_to_name': assignee['name'],
        'status': 'todo', 'priority': data.priority,
        'due_date': data.due_date.isoformat() if data.due_date else None,
        'created_by': {'id': user['id'], 'name': user['name']},
        'photos': [], 'history': [], 'completed_at': None,
        'created_at': now(), 'updated_at': now(),
    }
    await log(pid, 'task', f'Task assigned · {data.title} → {assignee["name"]}', user)
    await notify(assignee['id'], 'task_assigned',
                 f'Task assigned: {data.title}',
                 f'Priority: {data.priority}' + (f' · due {data.due_date.isoformat()}' if data.due_date else ''),
                 {'page': 'tasks', 'id': doc['id']})
    return await save('tasks', doc)


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
    return await database().tasks.find(filt, {'_id': 0}).sort('created_at', -1).to_list(5000)


@router.patch('/tasks/{id}', response_model=Record)
async def edit_task(id: str, data: TaskPatchIn,
                    user: dict = Depends(require_roles('admin', 'manager', 'engineer', 'supervisor'))):
    task = await get('tasks', id)
    patch = {}
    for k, v in data.model_dump(exclude_unset=True).items():
        if k == 'due_date':
            patch[k] = v.isoformat() if v else None
        elif v is not None:
            patch[k] = v
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
    return await get('tasks', id)


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
    return await get('tasks', id)
