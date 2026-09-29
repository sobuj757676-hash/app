from datetime import datetime
from zoneinfo import ZoneInfo
from fastapi import APIRouter, HTTPException, Depends
from models import Record, WorkerIn, AttendanceIn, MaterialIn, MovementIn, ExpenseIn, AttendanceMeIn
from routes import database, get, uid, now, save, log, log_change
from auth import get_current_user, require_roles, OPS_ROLES, MONEY_ROLES

router = APIRouter()

def _sg_today():
    return datetime.now(ZoneInfo('Asia/Singapore')).date().isoformat()

@router.post('/projects/{pid}/workers', response_model=Record)
async def add_worker(pid: str, data: WorkerIn, user: dict = Depends(require_roles(*OPS_ROLES))):
    await get('projects', pid)
    await log(pid, 'workforce', f'{data.name} · Added to workforce', user)
    return await save('workers', {'id': uid(), 'project_id': pid, **data.model_dump(), 'active': True})

@router.patch('/workers/{id}', response_model=Record)
async def edit_worker(id: str, data: WorkerIn, user: dict = Depends(require_roles(*OPS_ROLES))):
    before = await get('workers', id)
    await database().workers.update_one({'id': id}, {'$set': data.model_dump()})
    after = await get('workers', id)
    await log_change(before['project_id'], 'workforce', f'{data.name} · Worker updated', user, before, after)
    return after

@router.delete('/workers/{id}')
async def archive_worker(id: str, user: dict = Depends(require_roles(*OPS_ROLES))):
    before = await get('workers', id)
    await database().workers.update_one({'id': id}, {'$set': {'active': False}})
    await log_change(before['project_id'], 'workforce', f'{before["name"]} · Worker archived', user, before, {**before, 'active': False})
    return {'ok': True}

@router.put('/workers/me/attendance', response_model=Record)
async def my_attendance(data: AttendanceMeIn, user: dict = Depends(require_roles('worker'))):
    if not user.get('worker_id'): raise HTTPException(404, 'No worker record linked to this account')
    worker = await get('workers', user['worker_id'])
    if not worker.get('active'): raise HTTPException(400, 'Worker is archived')
    date = _sg_today()
    doc = {'id': f'{worker["id"]}-{date}', 'project_id': worker['project_id'], 'worker_id': worker['id'],
           'date': date, 'status': data.status, 'hours': data.hours if data.status == 'present' else 0,
           'daily_rate': worker['daily_rate']}
    existing = await database().attendance.find_one({'worker_id': worker['id'], 'date': date}, {'_id': 0})
    if existing: doc['id'] = existing['id']
    await database().attendance.update_one({'worker_id': worker['id'], 'date': date}, {'$set': doc}, upsert=True)
    await log(worker['project_id'], 'workforce', f'{worker["name"]} · Marked {data.status} for today', user)
    return doc

@router.get('/workers/me')
async def my_worker(user: dict = Depends(require_roles('worker'))):
    if not user.get('worker_id'): raise HTTPException(404, 'No worker record linked to this account')
    worker = await get('workers', user['worker_id'])
    today_att = await database().attendance.find_one({'worker_id': worker['id'], 'date': _sg_today()}, {'_id': 0})
    return {**worker, 'today_attendance': today_att}

@router.put('/workers/{id}/attendance', response_model=Record)
async def attendance(id: str, data: AttendanceIn, user: dict = Depends(require_roles(*OPS_ROLES))):
    worker = await get('workers', id)
    if not worker.get('active'): raise HTTPException(400, 'Worker is archived')
    doc = {'id': f'{id}-{data.date.isoformat()}', 'project_id': worker['project_id'], 'worker_id': id, **data.model_dump(mode='json'), 'hours': data.hours if data.status == 'present' else 0, 'daily_rate': worker['daily_rate']}
    # Upsert by worker and date; preserve existing identifier to keep it stable.
    existing = await database().attendance.find_one({'worker_id': id, 'date': doc['date']}, {'_id': 0})
    if existing: doc['id'] = existing['id']
    await database().attendance.update_one({'worker_id': id, 'date': doc['date']}, {'$set': doc}, upsert=True)
    await log(worker['project_id'], 'workforce', f'{worker["name"]} · Attendance marked {data.status} ({doc["date"]})', user)
    return doc

@router.post('/projects/{pid}/materials', response_model=Record)
async def material(pid: str, data: MaterialIn, user: dict = Depends(require_roles(*OPS_ROLES))):
    await get('projects', pid)
    await log(pid, 'material', f'{data.name} · Added to inventory', user)
    return await save('materials', {'id': uid(), 'project_id': pid, **data.model_dump()})

@router.post('/materials/{id}/movements', response_model=Record)
async def movement(id: str, data: MovementIn, user: dict = Depends(require_roles(*OPS_ROLES))):
    material = await get('materials', id)
    query = {'id': id}
    if data.kind == 'issue': query['stock'] = {'$gte': data.quantity}
    result = await database().materials.update_one(query, {'$inc': {'stock': data.quantity if data.kind == 'receive' else -data.quantity}})
    if not result.modified_count: raise HTTPException(400, 'Insufficient stock')
    doc = {'id': uid(), 'project_id': material['project_id'], 'material_id': id, 'material_name': material['name'], **data.model_dump(), 'created_at': now()}
    await log(material['project_id'], 'material', f'{material["name"]} · {data.kind} {data.quantity:g} {material["unit"]}', user)
    return await save('movements', doc)

@router.patch('/materials/{id}', response_model=Record)
async def edit_material(id: str, data: MaterialIn, user: dict = Depends(require_roles(*OPS_ROLES))):
    before = await get('materials', id)
    await database().materials.update_one({'id': id}, {'$set': data.model_dump(exclude={'stock'})})
    after = await get('materials', id)
    await log_change(before['project_id'], 'material', f'{data.name} · Material updated', user, before, after)
    return after

@router.post('/projects/{pid}/expenses', response_model=Record)
async def expense(pid: str, data: ExpenseIn, user: dict = Depends(require_roles(*MONEY_ROLES))):
    await get('projects', pid)
    await log(pid, 'expense', f'{data.description} · S${data.amount:,.2f}', user)
    return await save('expenses', {'id': uid(), 'project_id': pid, **data.model_dump(mode='json'), 'created_at': now()})

@router.patch('/expenses/{id}', response_model=Record)
async def edit_expense(id: str, data: ExpenseIn, user: dict = Depends(require_roles(*MONEY_ROLES))):
    before = await get('expenses', id)
    await database().expenses.update_one({'id': id}, {'$set': data.model_dump(mode='json')})
    after = await get('expenses', id)
    await log_change(before['project_id'], 'expense', f'{data.description} · Expense updated', user, before, after)
    return after

@router.delete('/expenses/{id}')
async def delete_expense(id: str, user: dict = Depends(require_roles(*MONEY_ROLES))):
    expense = await get('expenses', id)
    await database().expenses.update_one({'id': id}, {'$set': {'deleted': True, 'deleted_at': now(), 'deleted_by': user['id']}})
    await log_change(expense['project_id'], 'expense', f'{expense["description"]} · Expense removed', user, expense, {**expense, 'deleted': True, 'deleted_at': now(), 'deleted_by': user['id']})
    return {'ok': True}
