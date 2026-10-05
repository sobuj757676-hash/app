"""Defect & rectification endpoints."""
from fastapi import APIRouter, HTTPException, Depends, Query
from models import DefectIn, DefectPatchIn, DefectAssignIn, DefectTransitionIn, Record
from routes import database, get, uid, now, save, log, log_change, is_worker
from auth import get_current_user, require_roles, OPS_ROLES
from notify import notify

router = APIRouter()

# Server-enforced status machine.
TRANSITIONS = {
    'open': {'assigned', 'cancelled'},
    'assigned': {'in_progress', 'open', 'cancelled'},
    'in_progress': {'rectified', 'assigned', 'cancelled'},
    'rectified': {'verified', 'in_progress', 'cancelled'},
    'verified': set(),
    'cancelled': set(),
}
# Defect statuses that count as "still open" for gating purposes.
LIVE_STATUSES = ('open', 'assigned', 'in_progress', 'rectified')


def _may_transition(user: dict, defect: dict, new_status: str) -> bool:
    role = user.get('role')
    if role in ('admin', 'manager', 'engineer'):
        return True
    if role == 'supervisor':
        return new_status != 'verified'  # verification is engineer+
    if role == 'worker':
        return (defect.get('assigned_to') == user.get('id')
                and (defect['status'], new_status) in
                (('assigned', 'in_progress'), ('in_progress', 'rectified')))
    return False


def _label(defect: dict) -> str:
    if defect.get('block'):
        return f"Blk {defect['block']} · #{defect.get('level') or ''}-{defect.get('number') or ''}"
    return 'site-wide'


async def _attach_assignee_names(docs: list[dict]) -> list[dict]:
    """Batch-resolve assigned_to → assigned_to_name, mirroring the pattern
    tasks store at write time. Names only — no new data exposure; every role
    already sees worker names via the directory / workspace."""
    ids = {d.get('assigned_to') for d in docs if d.get('assigned_to')}
    names = {}
    if ids:
        found = await database().users.find(
            {'id': {'$in': list(ids)}},
            {'_id': 0, 'id': 1, 'name': 1}).to_list(1000)
        names = {u['id']: u['name'] for u in found}
    for d in docs:
        aid = d.get('assigned_to')
        d['assigned_to_name'] = names.get(aid, '') if aid else ''
    return docs


async def _history(defect_id: str, status: str, note: str, user: dict):
    entry = {'status': status, 'by_id': user['id'], 'by_name': user['name'],
             'at': now(), 'note': (note or '')[:1000]}
    await database().defects.update_one(
        {'id': defect_id},
        {'$set': {'status': status, 'updated_at': now()},
         '$push': {'history': entry}})


@router.post('/projects/{pid}/defects', response_model=Record)
async def create_defect(pid: str, data: DefectIn,
                        user: dict = Depends(require_roles(*OPS_ROLES, 'worker'))):
    await get('projects', pid)
    block = level = number = ''
    if data.unit_id:
        unit = await get('units', data.unit_id)
        if unit['project_id'] != pid:
            raise HTTPException(400, 'Unit does not belong to this project')
        block, level, number = unit['block'], unit['level'], unit['number']
    doc = {
        'id': uid(), 'project_id': pid, 'unit_id': data.unit_id,
        'block': block, 'level': level, 'number': number,
        'title': data.title.strip(), 'description': (data.description or '').strip(),
        'category': data.category, 'severity': data.severity, 'status': 'open',
        'reported_by': {'id': user['id'], 'name': user['name']},
        'assigned_to': None,
        'due_date': data.due_date.isoformat() if data.due_date else None,
        'photos': [],
        'history': [{'status': 'open', 'by_id': user['id'], 'by_name': user['name'],
                     'at': now(), 'note': 'Reported'}],
        'verified_by': None, 'closed_at': None,
        'created_at': now(), 'updated_at': now(),
    }
    await log(pid, 'defect', f'Defect reported · {_label(doc)} · {doc["title"]}', user)
    return (await _attach_assignee_names([await save('defects', doc)]))[0]


@router.get('/projects/{pid}/defects', response_model=list[Record])
async def list_defects(pid: str, user: dict = Depends(get_current_user),
                       status: str | None = Query(None),
                       severity: str | None = Query(None),
                       block: str | None = Query(None),
                       assigned_to: str | None = Query(None)):
    await get('projects', pid)
    clauses: list[dict] = [{'project_id': pid}]
    if status:
        clauses.append({'status': status})
    if severity:
        clauses.append({'severity': severity})
    if block:
        clauses.append({'block': block})
    if assigned_to == 'me':
        clauses.append({'assigned_to': user['id']})
    elif assigned_to:
        clauses.append({'assigned_to': assigned_to})
    if is_worker(user):
        # Workers see only defects they reported or are assigned to.
        clauses.append({'$or': [{'assigned_to': user['id']},
                                {'reported_by.id': user['id']}]})
    filt = clauses[0] if len(clauses) == 1 else {'$and': clauses}
    docs = await database().defects.find(filt, {'_id': 0}).sort('created_at', -1).to_list(5000)
    return await _attach_assignee_names(docs)


@router.patch('/defects/{id}', response_model=Record)
async def edit_defect(id: str, data: DefectPatchIn,
                      user: dict = Depends(require_roles(*OPS_ROLES, 'worker'))):
    defect = await get('defects', id)
    if user['role'] not in ('admin', 'manager', 'engineer') \
            and defect.get('reported_by', {}).get('id') != user['id']:
        raise HTTPException(403, 'Only the reporter or an engineer can edit this defect')
    patch = {}
    for k, v in data.model_dump(exclude_unset=True).items():
        if k == 'due_date':
            patch[k] = v.isoformat() if v else None
        elif v is not None:
            patch[k] = v
    if 'title' in patch:
        patch['title'] = patch['title'].strip()
    if 'description' in patch:
        patch['description'] = patch['description'].strip()
    if patch:
        patch['updated_at'] = now()
        await database().defects.update_one({'id': id}, {'$set': patch})
        await log_change(defect['project_id'], 'defect',
                         f'Defect updated · {_label(defect)} · {defect["title"]}',
                         user, defect, await get('defects', id))
    return (await _attach_assignee_names([await get('defects', id)]))[0]


@router.post('/defects/{id}/assign', response_model=Record)
async def assign_defect(id: str, data: DefectAssignIn,
                        user: dict = Depends(require_roles('admin', 'manager', 'engineer', 'supervisor'))):
    defect = await get('defects', id)
    assignee = await database().users.find_one({'id': data.assignee_id, 'active': True},
                                               {'_id': 0, 'id': 1, 'name': 1})
    if not assignee:
        raise HTTPException(404, 'Assignee not found or inactive')
    await database().defects.update_one(
        {'id': id},
        {'$set': {'assigned_to': assignee['id'], 'updated_at': now()}})
    # Assigning an open defect moves it to assigned (part of the transition map).
    if defect['status'] == 'open':
        await _history(id, 'assigned', f'Assigned to {assignee["name"]}', user)
    await log(defect['project_id'], 'defect',
              f'Defect assigned · {_label(defect)} · {defect["title"]} → {assignee["name"]}', user)
    await notify(assignee['id'], 'defect_assigned',
                 f'Defect assigned: {defect["title"]}',
                 f'{_label(defect)} · reported by {defect["reported_by"]["name"]}',
                 {'page': 'defects', 'id': id})
    return (await _attach_assignee_names([await get('defects', id)]))[0]


@router.post('/defects/{id}/transition', response_model=Record)
async def transition_defect(id: str, data: DefectTransitionIn,
                            user: dict = Depends(require_roles(*OPS_ROLES, 'worker'))):
    defect = await get('defects', id)
    new = data.status
    if new not in TRANSITIONS.get(defect['status'], set()):
        raise HTTPException(400, f'Cannot move defect from {defect["status"]} to {new}')
    if not _may_transition(user, defect, new):
        raise HTTPException(403, 'You do not have permission for this action')
    await _history(id, new, data.note or f'Status → {new}', user)
    if new == 'verified':
        await database().defects.update_one(
            {'id': id},
            {'$set': {'verified_by': {'id': user['id'], 'name': user['name']},
                      'closed_at': now()}})
        reporter_id = defect.get('reported_by', {}).get('id')
        if reporter_id and reporter_id != user['id']:
            await notify(reporter_id, 'defect_verified',
                         f'Defect verified: {defect["title"]}',
                         f'{_label(defect)} · verified by {user["name"]}',
                         {'page': 'defects', 'id': id})
    await log(defect['project_id'], 'defect',
              f'Defect {new} · {_label(defect)} · {defect["title"]}', user)
    return (await _attach_assignee_names([await get('defects', id)]))[0]
