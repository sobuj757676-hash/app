"""Task assignment endpoints."""
from fastapi import APIRouter, HTTPException, Depends, Query
from models import TaskIn, TaskPatchIn, TaskTransitionIn, DefectTaskIn, Record, TaskAdvanceIn, DismissCarryoverIn
from routes import database, get, uid, now, save, log, log_change, is_worker, _project_with_stages, _advance_blocker, _advanced_by_task
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


def _validate_completed_unit_ids(scope: dict | None, ids: list[str]) -> list[str]:
    """Dedupe (order preserved) and validate completed unit ids against the
    task scope. Raises 400 if any id is not in scope.unit_ids (when scope
    is present)."""
    deduped = list(dict.fromkeys(ids))
    if scope:
        allowed = set(scope.get('unit_ids') or [])
        for uid in deduped:
            if uid not in allowed:
                raise HTTPException(400, f'Completed unit not in task scope: {uid}')
    return deduped


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
                       plan_date=None, completed_unit_ids: list[str] | None = None) -> dict:
    """Shared task creation used by both POST endpoints. assignees optional
    (empty = unassigned). All assignees are notified."""
    await get('projects', pid)
    # Planned tasks carry a single date: due_date defaults to plan_date.
    if kind == 'planned' and due_date is None and plan_date is not None:
        due_date = plan_date
    people = await _resolve_assignees(assignees)
    unit_label = ''
    if unit_id:
        unit = await get('units', unit_id)
        if unit['project_id'] != pid:
            raise HTTPException(400, 'Unit does not belong to this project')
        unit_label = f'Blk {unit["block"]} · #{unit["level"]:02}-{unit["number"]}'
    defect = await _validate_defect_link(pid, defect_id) if defect_id else None
    done_ids = _validate_completed_unit_ids(scope, completed_unit_ids or [])
    doc = {
        'id': uid(), 'project_id': pid, 'unit_id': unit_id, 'unit_label': unit_label,
        'defect_id': defect_id,
        'title': title.strip(), 'description': (description or '').strip(),
        'assignees': [a['id'] for a in people],
        'assignee_names': [a['name'] for a in people],
        'kind': kind, 'scope': scope,
        'completed_unit_ids': done_ids,
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
                              kind=data.kind, scope=scope, plan_date=data.plan_date,
                              completed_unit_ids=data.completed_unit_ids)


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
                    user: dict = Depends(require_roles(*OPS_ROLES, 'worker'))):
    task = await get('tasks', id)
    dump = data.model_dump(exclude_unset=True)
    # Workers may PATCH only completed_unit_ids, and only on tasks where
    # they are an assignee. Any other field (or an unassigned task) → 403.
    if is_worker(user):
        if set(dump) - {'completed_unit_ids'}:
            raise HTTPException(403, 'You do not have permission for this action')
        if user.get('id') not in (task.get('assignees') or []):
            raise HTTPException(403, 'You do not have permission for this action')
    patch = {}
    scope_now = task.get('scope')  # scope completed ids are validated against
    for k, v in dump.items():
        if k in ('due_date', 'plan_date'):
            patch[k] = v.isoformat() if v else None
        elif k == 'defect_id':
            continue  # handled below (None clears the link)
        elif k == 'assignees':
            continue  # handled below (validated + denormalized)
        elif k == 'scope':
            scope_now = await _validate_scope(task['project_id'], data.scope) \
                if v is not None else None
            patch[k] = scope_now
        elif k == 'completed_unit_ids':
            # Replaces the whole list; validated against the (possibly new) scope.
            patch[k] = _validate_completed_unit_ids(scope_now, v or [])
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


# ---------- Daily Plan top-notch (spec v2 + v2.1): checked-unit advance ----------

async def _advance_one_checked(pid: str, task: dict, unit_id: str,
                               si: int, stages: list, user: dict) -> dict:
    """Classify one checked scope unit against its LIVE stage and advance it
    by exactly one stage when eligible (spec v2.1 §B). The write is a
    compare-and-swap on {id, stage}; losing a race re-reads and reclassifies.
    Stage-ahead units count as already_advanced only when the transition
    into the current stage was this task's own plan advance (history-proven);
    anything else is a conflict requiring review."""
    for _attempt in range(2):
        unit = await database().units.find_one({'id': unit_id}, {'_id': 0})
        if not unit or unit.get('project_id') != pid:
            return {'unit_id': unit_id, 'result': 'not_in_scope'}
        stage = unit.get('stage', 0)
        if stage > si:
            if _advanced_by_task(unit, stage, task['id']):
                return {'unit_id': unit_id, 'result': 'already_advanced', 'stage': stage}
            return {'unit_id': unit_id, 'result': 'conflict_ahead', 'stage': stage}
        if stage < si:
            return {'unit_id': unit_id, 'result': 'conflict_behind', 'stage': stage}
        guard = await _advance_blocker(unit, stages)
        if guard:
            code, detail = guard
            out = {'unit_id': unit_id, 'result': code}
            if detail:
                out['detail'] = detail
            return out
        upd = await database().units.update_one(
            {'id': unit_id, 'stage': si},
            {'$set': {'stage': si + 1, 'sample': False, 'updated_at': now()},
             '$push': {'history': {
                 'stage': si, 'to_stage': si + 1, 'note': 'Plan advance',
                 'by': user['name'], 'by_id': user['id'],
                 'task_id': task['id'], 'source': 'plan_advance',
                 'at': now()}}})
        if upd.modified_count:
            return {'unit_id': unit_id, 'result': 'advanced',
                    'from_stage': si, 'to_stage': si + 1}
        # CAS lost a race: loop re-reads the unit and reclassifies it.
    unit = await database().units.find_one({'id': unit_id}, {'_id': 0})
    stage = (unit or {}).get('stage', 0)
    if unit and stage > si and _advanced_by_task(unit, stage, task['id']):
        return {'unit_id': unit_id, 'result': 'already_advanced', 'stage': stage}
    if unit and stage != si:
        return {'unit_id': unit_id,
                'result': 'conflict_ahead' if stage > si else 'conflict_behind',
                'stage': stage}
    return {'unit_id': unit_id, 'result': 'conflict_behind', 'stage': stage,
            'detail': 'Unit changed during advance; review and retry'}


async def _scope_all_advanced(task: dict, scope_ids: list[str],
                              completed: set, si: int) -> bool:
    """True when every scope unit's live stage is past the scope stage and
    no checked unit is unresolved (still at/behind the scope stage, or ahead
    via another workflow). Drives the client's offer to mark the task done."""
    if not scope_ids:
        return False
    units = {u['id']: u for u in await database().units.find(
        {'id': {'$in': scope_ids}}, {'_id': 0}).to_list(len(scope_ids))}
    for unit_id in scope_ids:
        unit = units.get(unit_id)
        if not unit:
            return False
        stage = unit.get('stage', 0)
        if stage <= si:
            return False
        if unit_id in completed and not _advanced_by_task(unit, stage, task['id']):
            return False
    return True


@router.post('/projects/{pid}/tasks/{tid}/advance')
async def advance_checked_units(pid: str, tid: str, data: TaskAdvanceIn,
                                user: dict = Depends(require_roles(*OPS_ROLES))):
    """Advance a planned task's checked units by one stage (spec v2 §2 as
    corrected by v2.1 §B). Per-unit partial success; unchecked units are
    never advanced; the call is idempotent (a repeat performs zero writes).
    Task status is never changed here — closing the task stays the
    supervisor's explicit transition. Works on done tasks too: a done
    status must not strand checked-but-unadvanced units (v2.1 addendum)."""
    task = await get('tasks', tid)
    if task.get('project_id') != pid:
        raise HTTPException(404, 'Task not found')
    scope = task.get('scope')
    if task.get('kind') != 'planned' or not scope:
        raise HTTPException(400, 'Only planned tasks with a scope can advance checked units')
    if task.get('status') == 'cancelled':
        raise HTTPException(400, 'A cancelled task cannot advance units')
    stages = (await _project_with_stages(pid))['workflow_stages']
    si = scope.get('stage_index', 0)
    if si >= len(stages):
        raise HTTPException(400, 'Scope stage is out of range')
    scope_ids = list(dict.fromkeys(scope.get('unit_ids') or []))
    scope_set = set(scope_ids)
    completed = set(task.get('completed_unit_ids') or [])
    if data.unit_ids is not None:
        requested = list(dict.fromkeys(data.unit_ids))
        candidates = [u for u in requested if u in scope_set and u in completed]
        extras = [u for u in requested if u not in scope_set or u not in completed]
    else:
        candidates = [u for u in scope_ids if u in completed]
        extras = []
    results = [await _advance_one_checked(pid, task, u, si, stages, user)
               for u in candidates]
    for u in extras:
        results.append({'unit_id': u,
                        'result': 'not_in_scope' if u not in scope_set else 'not_checked'})
    counts = {}
    for r in results:
        counts[r['result']] = counts.get(r['result'], 0) + 1
    all_advanced = await _scope_all_advanced(task, scope_ids, completed, si)
    if counts.get('advanced') or counts.get('conflict_ahead') or counts.get('conflict_behind'):
        await log(pid, 'stage',
                  f"Plan advance · {task['title']} · {counts.get('advanced', 0)} advanced"
                  f" · {counts.get('already_advanced', 0)} already"
                  f" · {counts.get('conflict_ahead', 0) + counts.get('conflict_behind', 0)} conflict"
                  f" · {sum(counts.get(k, 0) for k in ('blocked_rto', 'blocked_defect', 'blocked_tests'))} blocked",
                  user)
    return {'task_id': tid, 'results': results,
            'advanced': counts.get('advanced', 0),
            'already_advanced': counts.get('already_advanced', 0),
            'conflict_ahead': counts.get('conflict_ahead', 0),
            'conflict_behind': counts.get('conflict_behind', 0),
            'blocked': sum(counts.get(k, 0)
                           for k in ('blocked_rto', 'blocked_defect', 'blocked_tests')),
            'all_advanced': all_advanced}


@router.post('/tasks/{id}/dismiss-carryover', response_model=Record)
async def dismiss_carryover(id: str, data: DismissCarryoverIn,
                            user: dict = Depends(require_roles(*OPS_ROLES))):
    """Persistently dismiss a planned task's carry-over offer (spec v2 §3).
    Used by Skip (no successor) and by Add to Today (successor recorded, so
    the lineage closes exactly once and the same units are never offered
    twice). Idempotent: dismissing an already-dismissed task is a no-op.
    The task's units are never touched — dismissal hides the offer, not
    the work; units stay visible in the Unit Tracker."""
    task = await get('tasks', id)
    if task.get('carryover_dismissed_at'):
        return task
    patch = {'carryover_dismissed_at': now(),
             'carryover_dismissed_by': {'id': user['id'], 'name': user['name']},
             'updated_at': now()}
    if data.superseded_by_task_id:
        successor = await get('tasks', data.superseded_by_task_id)
        if successor.get('project_id') != task.get('project_id'):
            raise HTTPException(400, 'Successor task belongs to another project')
        patch['superseded_by_task_id'] = data.superseded_by_task_id
    await database().tasks.update_one({'id': id}, {'$set': patch})
    note = ' · re-planned' if data.superseded_by_task_id else ' · skipped'
    await log(task['project_id'], 'task',
              f"Carry-over dismissed · {task['title']}{note}", user)
    return await get('tasks', id)
