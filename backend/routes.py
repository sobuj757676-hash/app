import uuid
import csv
import io
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from models import Record, Workspace, ProjectIn, BlockIn, UnitIn, AdvanceIn, InspectionIn, DecisionIn, PointIn, TestIn
from seed import STAGES, points_for

router = APIRouter()
def database():
    from server import db
    return db
def uid(): return str(uuid.uuid4())
def now(): return datetime.now(timezone.utc).isoformat()
async def get(collection, id):
    item = await database()[collection].find_one({'id': id}, {'_id': 0})
    if not item: raise HTTPException(404, 'Record not found')
    return item
async def log(project_id, kind, message):
    await database().activity.insert_one({'id': uid(), 'project_id': project_id, 'kind': kind, 'message': message, 'created_at': now()})
async def save(collection, doc):
    await database()[collection].insert_one(doc.copy())
    return doc

@router.get('/')
async def health(): return {'status': 'ok', 'app': 'VoltCraft'}

@router.get('/projects', response_model=list[Record])
async def projects(): return await database().projects.find({}, {'_id': 0}).to_list(1000)

@router.post('/projects', response_model=Record)
async def create_project(data: ProjectIn):
    return await save('projects', {'id': uid(), **data.model_dump(mode='json'), 'sample': False, 'created_at': now()})

@router.patch('/projects/{id}', response_model=Record)
async def edit_project(id: str, data: ProjectIn):
    await get('projects', id)
    await database().projects.update_one({'id': id}, {'$set': data.model_dump(mode='json')})
    return await get('projects', id)

@router.get('/projects/{pid}/workspace', response_model=Workspace)
async def workspace(pid: str):
    project = await get('projects', pid)
    result = {'project': project}
    for coll in ['blocks', 'units', 'workers', 'materials', 'expenses', 'inspections', 'tests', 'attendance', 'movements']:
        result[coll] = await database()[coll].find({'project_id': pid}, {'_id': 0}).to_list(50000)
    result['activity'] = await database().activity.find({'project_id': pid}, {'_id': 0}).sort('created_at', -1).limit(20).to_list(20)
    return result

@router.post('/projects/{pid}/blocks', response_model=Record)
async def create_block(pid: str, data: BlockIn):
    await get('projects', pid)
    name = data.name.strip().upper()
    if await database().blocks.find_one({'project_id': pid, 'name': name}): raise HTTPException(409, 'Block already exists')
    block = {'id': uid(), 'project_id': pid, 'name': name, 'levels': data.levels, 'planned_units': data.levels * data.units_per_level, 'sample_layout': False}
    await save('blocks', block)
    units = []
    for level in range(1, data.levels + 1):
        for n in range(data.units_per_level):
            id = uid()
            units.append({'id': id, 'project_id': pid, 'block_id': block['id'], 'block': name, 'level': level, 'number': str(data.first_unit+n), 'unit_type': '4-room', 'assigned_to': '', 'note': '', 'stage': 0, 'rto': 'none', 'points': points_for(id), 'history': [], 'updated_at': now(), 'sample': False})
    await database().units.insert_many(units)
    await log(pid, 'project', f'Blk {name} · {len(units)} units added')
    return block

@router.post('/blocks/{bid}/units', response_model=Record)
async def create_unit(bid: str, data: UnitIn):
    block = await get('blocks', bid)
    if data.level > block['levels']: raise HTTPException(400, 'Level exceeds block height')
    existing = {'block_id': bid, 'level': data.level, 'number': data.number}
    if await database().units.find_one(existing): raise HTTPException(409, 'Unit already exists')
    id = uid()
    return await save('units', {'id': id, 'project_id': block['project_id'], 'block_id': bid, 'block': block['name'], **data.model_dump(), 'stage': 0, 'rto': 'none', 'points': points_for(id), 'history': [], 'updated_at': now(), 'sample': False})

@router.patch('/units/{id}', response_model=Record)
async def edit_unit(id: str, data: UnitIn):
    unit = await get('units', id)
    block = await get('blocks', unit['block_id'])
    if data.level > block['levels']: raise HTTPException(400, 'Level exceeds block height')
    if await database().units.find_one({'block_id': block['id'], 'level': data.level, 'number': data.number, 'id': {'$ne': id}}): raise HTTPException(409, 'Unit already exists')
    await database().units.update_one({'id': id}, {'$set': {**data.model_dump(), 'updated_at': now()}})
    return await get('units', id)

@router.post('/units/{id}/reset-sample', response_model=Record)
async def reset_sample(id: str):
    unit = await get('units', id)
    if not unit.get('sample'): raise HTTPException(400, 'Only sample units can be reset')
    real_records = {'unit_id': id, 'sample': {'$ne': True}}
    if unit.get('history') or await database().tests.count_documents(real_records) or await database().inspections.count_documents(real_records):
        raise HTTPException(400, 'Unit has real inspection or test records and cannot be reset')
    # Claim only the untouched version. All real workflow writes clear sample,
    # so a concurrent real update prevents this reset before any deletion.
    changed = await database().units.update_one({'id': id, 'sample': True, 'updated_at': unit['updated_at']}, {'$set': {'stage': 0, 'rto': 'none', 'sample': False, 'history': [], 'updated_at': now()}})
    if not changed.modified_count: raise HTTPException(409, 'Unit changed. Refresh and retry.')
    await database().tests.delete_many({'unit_id': id, 'sample': True})
    await database().inspections.delete_many({'unit_id': id, 'sample': True})
    await log(unit['project_id'], 'stage', f'Blk {unit["block"]} · #{unit["level"]:02}-{unit["number"]} · Sample progress reset')
    return await get('units', id)

@router.post('/units/{id}/advance', response_model=Record)
async def advance(id: str, data: AdvanceIn):
    unit = await get('units', id)
    stage = unit['stage']
    if stage != data.expected_stage: raise HTTPException(409, 'Unit changed. Refresh and retry.')
    if stage >= 9: raise HTTPException(400, 'Unit already complete')
    if stage == 5: raise HTTPException(400, 'RTO approval required before plastering')
    if stage == 8:
        tests = await database().tests.find({'unit_id': id}, {'_id': 0}).sort('created_at', 1).to_list(10000)
        latest = {t['point_id']: t for t in tests}
        if not unit['points'] or any(latest.get(p['id'], {}).get('result') != 'pass' for p in unit['points']): raise HTTPException(400, 'A passing test is required for every point')
    update = await database().units.update_one({'id': id, 'stage': stage}, {'$set': {'stage': stage+1, 'sample': False, 'updated_at': now()}, '$push': {'history': {'stage': stage, 'note': data.note, 'at': now()}}})
    if not update.modified_count: raise HTTPException(409, 'Unit changed. Refresh and retry.')
    await log(unit['project_id'], 'stage', f'Blk {unit["block"]} · #{unit["level"]:02}-{unit["number"]} · {STAGES[stage]} completed')
    return await get('units', id)

@router.post('/units/{id}/inspections', response_model=Record)
async def request_inspection(id: str, data: InspectionIn):
    unit = await get('units', id)
    result = await database().units.update_one({'id': id, 'stage': 5, 'rto': {'$in': ['none', 'rework']}}, {'$set': {'rto': 'pending', 'sample': False, 'updated_at': now()}})
    if not result.modified_count: raise HTTPException(400, 'Complete installation first; only one pending inspection is allowed')
    doc = {'id': uid(), 'project_id': unit['project_id'], 'unit_id': id, 'block': unit['block'], 'unit_label': f'#{unit["level"]:02}-{unit["number"]}', **data.model_dump(mode='json'), 'status': 'pending', 'created_at': now()}
    await log(unit['project_id'], 'inspection', f'Blk {unit["block"]} · {doc["unit_label"]} · RTO inspection requested')
    return await save('inspections', doc)

@router.post('/inspections/{id}/decision', response_model=Record)
async def decide(id: str, data: DecisionIn):
    inspection = await get('inspections', id)
    if inspection['status'] != 'pending': raise HTTPException(400, 'Inspection is already closed')
    unit = await get('units', inspection['unit_id'])
    changed = await database().units.update_one({'id': unit['id'], 'stage': 5, 'rto': 'pending'}, {'$set': {'stage': 6 if data.result == 'approved' else 5, 'rto': data.result, 'sample': False, 'updated_at': now()}, '$push': {'history': {'stage': 5, 'note': data.note, 'inspector': data.inspector, 'result': data.result, 'at': now()}}})
    if not changed.modified_count: raise HTTPException(409, 'Unit is not awaiting this inspection')
    await database().inspections.update_one({'id': id}, {'$set': {'status': data.result, 'inspector': data.inspector, 'note': data.note, 'decided_at': now()}})
    await log(unit['project_id'], 'inspection', f'Blk {unit["block"]} · {inspection["unit_label"]} · RTO {data.result}')
    return await get('inspections', id)

@router.post('/units/{id}/points', response_model=Record)
async def add_point(id: str, data: PointIn):
    unit = await get('units', id)
    if unit['stage'] == 9: raise HTTPException(400, 'Completed unit cannot accept new points')
    if any(p['name'].lower() == data.name.lower() for p in unit['points']): raise HTTPException(409, 'Point already exists')
    await database().units.update_one({'id': id}, {'$push': {'points': {'id': uid(), **data.model_dump()}}})
    return await get('units', id)

@router.post('/units/{id}/tests', response_model=Record)
async def record_test(id: str, data: TestIn):
    unit = await get('units', id)
    if unit['stage'] != 8: raise HTTPException(400, 'Tests are recorded at the insulation testing stage')
    point = next((p for p in unit['points'] if p['id'] == data.point_id), None)
    if not point: raise HTTPException(404, 'Point not found')
    claimed = await database().units.update_one({'id': id, 'stage': 8, 'updated_at': unit['updated_at']}, {'$set': {'sample': False, 'updated_at': now()}})
    if not claimed.modified_count: raise HTTPException(409, 'Unit changed. Refresh and retry.')
    doc = {'id': uid(), 'project_id': unit['project_id'], 'unit_id': id, 'point_name': point['name'], 'block': unit['block'], 'unit_label': f'#{unit["level"]:02}-{unit["number"]}', **data.model_dump(), 'created_at': now()}
    await log(unit['project_id'], 'test', f'Blk {unit["block"]} · {point["name"]} · Test {data.result}')
    return await save('tests', doc)

@router.get('/projects/{pid}/export/{kind}')
async def export(pid: str, kind: str):
    await get('projects', pid)
    fields = {'units': ['block','level','number','unit_type','stage','rto','assigned_to','note'], 'workers':['name','trade','block','daily_rate','phone'], 'materials':['name','unit','stock','minimum','unit_cost'], 'expenses':['date','description','category','amount','block','reference'], 'inspections':['block','unit_label','inspector','date','status','note'], 'tests':['block','unit_label','point_name','voltage','l_n','l_e','n_e','result','tested_by'], 'attendance':['worker_id','date','status','hours','daily_rate']}
    if kind not in fields: raise HTTPException(400, 'Invalid export type')
    docs = await database()[kind].find({'project_id': pid}, {'_id': 0}).to_list(50000)
    stream = io.StringIO()
    writer = csv.writer(stream)
    writer.writerow(fields[kind])
    for doc in docs:
        row = []
        for field in fields[kind]:
            value = doc.get(field, '')
            if isinstance(value, str) and value.startswith(('=', '+', '-', '@', '\t', '\r')): value = "'" + value
            row.append(value)
        writer.writerow(row)
    return Response('\ufeff'+stream.getvalue(), media_type='text/csv; charset=utf-8', headers={'Content-Disposition': f'attachment; filename="voltcraft-{kind}.csv"'})