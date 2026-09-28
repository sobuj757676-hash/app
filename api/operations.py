from fastapi import APIRouter, HTTPException
from models import Record, WorkerIn, AttendanceIn, MaterialIn, MovementIn, ExpenseIn
from routes import database, get, uid, now, save, log

router = APIRouter()

@router.post('/projects/{pid}/workers', response_model=Record)
async def add_worker(pid: str, data: WorkerIn):
    await get('projects', pid)
    await log(pid, 'workforce', f'{data.name} · Added to workforce')
    return await save('workers', {'id': uid(), 'project_id': pid, **data.model_dump(), 'active': True})

@router.patch('/workers/{id}', response_model=Record)
async def edit_worker(id: str, data: WorkerIn):
    await get('workers', id)
    await database().workers.update_one({'id': id}, {'$set': data.model_dump()})
    return await get('workers', id)

@router.delete('/workers/{id}')
async def archive_worker(id: str):
    await get('workers', id)
    await database().workers.update_one({'id': id}, {'$set': {'active': False}})
    return {'ok': True}

@router.put('/workers/{id}/attendance', response_model=Record)
async def attendance(id: str, data: AttendanceIn):
    worker = await get('workers', id)
    if not worker.get('active'): raise HTTPException(400, 'Worker is archived')
    doc = {'id': f'{id}-{data.date.isoformat()}', 'project_id': worker['project_id'], 'worker_id': id, **data.model_dump(mode='json'), 'hours': data.hours if data.status == 'present' else 0, 'daily_rate': worker['daily_rate']}
    # Upsert by worker and date; preserve existing identifier to keep it stable.
    existing = await database().attendance.find_one({'worker_id': id, 'date': doc['date']}, {'_id': 0})
    if existing: doc['id'] = existing['id']
    await database().attendance.update_one({'worker_id': id, 'date': doc['date']}, {'$set': doc}, upsert=True)
    return doc

@router.post('/projects/{pid}/materials', response_model=Record)
async def material(pid: str, data: MaterialIn):
    await get('projects', pid)
    await log(pid, 'material', f'{data.name} · Added to inventory')
    return await save('materials', {'id': uid(), 'project_id': pid, **data.model_dump()})

@router.post('/materials/{id}/movements', response_model=Record)
async def movement(id: str, data: MovementIn):
    material = await get('materials', id)
    query = {'id': id}
    if data.kind == 'issue': query['stock'] = {'$gte': data.quantity}
    result = await database().materials.update_one(query, {'$inc': {'stock': data.quantity if data.kind == 'receive' else -data.quantity}})
    if not result.modified_count: raise HTTPException(400, 'Insufficient stock')
    doc = {'id': uid(), 'project_id': material['project_id'], 'material_id': id, 'material_name': material['name'], **data.model_dump(), 'created_at': now()}
    await log(material['project_id'], 'material', f'{material["name"]} · {data.kind} {data.quantity:g} {material["unit"]}')
    return await save('movements', doc)

@router.patch('/materials/{id}', response_model=Record)
async def edit_material(id: str, data: MaterialIn):
    await get('materials', id)
    await database().materials.update_one({'id': id}, {'$set': data.model_dump(exclude={'stock'})})
    return await get('materials', id)

@router.post('/projects/{pid}/expenses', response_model=Record)
async def expense(pid: str, data: ExpenseIn):
    await get('projects', pid)
    await log(pid, 'expense', f'{data.description} · S${data.amount:,.2f}')
    return await save('expenses', {'id': uid(), 'project_id': pid, **data.model_dump(mode='json'), 'created_at': now()})

@router.patch('/expenses/{id}', response_model=Record)
async def edit_expense(id: str, data: ExpenseIn):
    await get('expenses', id)
    await database().expenses.update_one({'id': id}, {'$set': data.model_dump(mode='json')})
    return await get('expenses', id)

@router.delete('/expenses/{id}')
async def delete_expense(id: str):
    expense = await get('expenses', id)
    await database().expenses.delete_one({'id': id})
    await log(expense['project_id'], 'expense', f'{expense["description"]} · Expense removed')
    return {'ok': True}