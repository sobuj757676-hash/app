import uuid
import csv
import io
import json
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi.responses import Response
from models import Record, Workspace, ProjectIn, BlockIn, UnitIn, AdvanceIn, InspectionIn, DecisionIn, PointIn, TestIn, RtoChecklistIn
from seed import STAGES, points_for, DEFAULT_RTO_CHECKLIST
from auth import get_current_user, require_roles, OPS_ROLES, DECIDE_ROLES, MONEY_ROLES

router = APIRouter()
def database():
    from server import db
    return db
def uid(): return str(uuid.uuid4())
def now(): return datetime.now(timezone.utc).isoformat()
def is_worker(user): return user.get('role') == 'worker'
async def get(collection, id):
    item = await database()[collection].find_one({'id': id}, {'_id': 0})
    if not item: raise HTTPException(404, 'Record not found')
    return item

def _short(value):
    text = value if isinstance(value, str) else json.dumps(value, default=str)
    return text if len(text) <= 400 else text[:397] + '…'

def _changes(before, after):
    diff = {}
    for key in set(before or {}) | set(after or {}):
        if key.startswith('_'):
            continue
        b, a = (before or {}).get(key), (after or {}).get(key)
        if b != a:
            diff[key] = {'before': _short(b), 'after': _short(a)}
    return diff

async def log(project_id, kind, message, user=None):
    entry = {'id': uid(), 'project_id': project_id, 'kind': kind, 'message': message, 'created_at': now()}
    if user:
        entry['user_id'] = user.get('id')
        entry['user_name'] = user.get('name')
    await database().activity.insert_one(entry)

async def log_change(project_id, kind, message, user, before, after):
    entry = {'id': uid(), 'project_id': project_id, 'kind': kind, 'message': message,
             'created_at': now(), 'user_id': user.get('id'), 'user_name': user.get('name'),
             'changes': _changes(before, after)}
    await database().activity.insert_one(entry)

async def save(collection, doc):
    await database()[collection].insert_one(doc.copy())
    return doc

@router.get('/')
async def health(): return {'status': 'ok', 'app': 'VoltCraft'}

@router.get('/projects', response_model=list[Record])
async def projects(user: dict = Depends(get_current_user)):
    docs = await database().projects.find({}, {'_id': 0}).to_list(1000)
    if is_worker(user):
        for d in docs:
            d.pop('budget', None)
    return docs

@router.post('/projects', response_model=Record)
async def create_project(data: ProjectIn, user: dict = Depends(require_roles(*MONEY_ROLES))):
    payload = data.model_dump(mode='json')
    if not payload.get('rto_checklist_template'):
        payload['rto_checklist_template'] = DEFAULT_RTO_CHECKLIST
    doc = await save('projects', {'id': uid(), **payload, 'sample': False, 'created_at': now()})
    await log(doc['id'], 'project', f'Project created · {data.name}', user)
    return doc

@router.patch('/projects/{id}', response_model=Record)
async def edit_project(id: str, data: ProjectIn, user: dict = Depends(require_roles(*MONEY_ROLES))):
    before = await get('projects', id)
    patch = data.model_dump(mode='json', exclude_unset=True)
    if patch.get('rto_checklist_template') is not None:
        patch['rto_checklist_template'] = [s.strip() for s in patch['rto_checklist_template'] if s.strip()][:30]
        if not patch['rto_checklist_template']:
            raise HTTPException(400, 'Checklist template needs at least one item')
    await database().projects.update_one({'id': id}, {'$set': patch})
    after = await get('projects', id)
    await log_change(id, 'project', f'Project updated · {after["name"]}', user, before, after)
    return after

@router.get('/projects/{pid}/settings/rto-checklist')
async def get_rto_checklist(pid: str, user: dict = Depends(get_current_user)):
    project = await get('projects', pid)
    return {'template': project.get('rto_checklist_template') or DEFAULT_RTO_CHECKLIST}

@router.put('/projects/{pid}/settings/rto-checklist')
async def set_rto_checklist(pid: str, data: RtoChecklistIn,
                            user: dict = Depends(require_roles('admin', 'manager'))):
    await get('projects', pid)
    items = [s.strip() for s in data.template if s.strip()]
    if not items:
        raise HTTPException(400, 'Checklist template needs at least one item')
    if len(set(items)) != len(items):
        raise HTTPException(400, 'Checklist items must be unique')
    before = await get('projects', pid)
    await database().projects.update_one({'id': pid}, {'$set': {'rto_checklist_template': items[:30]}})
    after = await get('projects', pid)
    await log_change(pid, 'project', 'RTO readiness checklist updated', user, before, after)
    return {'template': items[:30]}

PAGINATED = ('units', 'attendance', 'movements')

@router.get('/projects/{pid}/workspace', response_model=Workspace)
async def workspace(pid: str, user: dict = Depends(get_current_user),
                    page: int = Query(1, ge=1), page_size: int | None = Query(None, ge=1, le=1000)):
    project = await get('projects', pid)
    if is_worker(user):
        project = {**project}
        project.pop('budget', None)
    result = {'project': project}
    pagination = {}
    for coll in ['blocks', 'units', 'workers', 'materials', 'expenses', 'inspections', 'tests', 'defects', 'tasks', 'attendance', 'movements']:
        filt = {'project_id': pid}
        if coll == 'expenses':
            filt['deleted'] = {'$ne': True}
        if page_size is None or coll not in PAGINATED:
            result[coll] = await database()[coll].find(filt, {'_id': 0}).to_list(50000)
            if coll in PAGINATED:
                total = len(result[coll])
                pagination[coll] = {'page': 1, 'page_size': total, 'total': total}
        else:
            total = await database()[coll].count_documents(filt)
            result[coll] = await database()[coll].find(filt, {'_id': 0}).skip((page - 1) * page_size).limit(page_size).to_list(page_size)
            pagination[coll] = {'page': page, 'page_size': page_size, 'total': total}
    if is_worker(user):
        result['expenses'] = []
        for m in result['materials']:
            m.pop('unit_cost', None)
        for w in result['workers']:
            if w.get('id') != user.get('worker_id'):
                w.pop('daily_rate', None)
                w.pop('phone', None)
        # Workers see only defects they reported or are assigned to, and their own tasks.
        result['defects'] = [d for d in result['defects']
                             if d.get('assigned_to') == user['id']
                             or d.get('reported_by', {}).get('id') == user['id']]
        result['tasks'] = [t for t in result['tasks'] if t.get('assigned_to') == user['id']]
    # Embed linked-defect summaries so task cards / worker queue can show defect chips.
    from tasks import _attach_defects
    result['tasks'] = await _attach_defects(result['tasks'])
    result['activity'] = await database().activity.find({'project_id': pid}, {'_id': 0}).sort('created_at', -1).limit(20).to_list(20)
    result['pagination'] = pagination
    return result

@router.post('/projects/{pid}/blocks', response_model=Record)
async def create_block(pid: str, data: BlockIn, user: dict = Depends(require_roles(*MONEY_ROLES))):
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
    await log(pid, 'project', f'Blk {name} · {len(units)} units added', user)
    return block

@router.post('/blocks/{bid}/units', response_model=Record)
async def create_unit(bid: str, data: UnitIn, user: dict = Depends(require_roles(*OPS_ROLES))):
    block = await get('blocks', bid)
    if data.level > block['levels']: raise HTTPException(400, 'Level exceeds block height')
    existing = {'block_id': bid, 'level': data.level, 'number': data.number}
    if await database().units.find_one(existing): raise HTTPException(409, 'Unit already exists')
    id = uid()
    doc = await save('units', {'id': id, 'project_id': block['project_id'], 'block_id': bid, 'block': block['name'], **data.model_dump(), 'stage': 0, 'rto': 'none', 'points': points_for(id), 'history': [], 'updated_at': now(), 'sample': False})
    await log(block['project_id'], 'unit', f'Blk {block["name"]} · Unit #{data.level:02}-{data.number} added', user)
    return doc

@router.patch('/units/{id}', response_model=Record)
async def edit_unit(id: str, data: UnitIn, user: dict = Depends(require_roles(*OPS_ROLES))):
    before = await get('units', id)
    block = await get('blocks', before['block_id'])
    if data.level > block['levels']: raise HTTPException(400, 'Level exceeds block height')
    if await database().units.find_one({'block_id': block['id'], 'level': data.level, 'number': data.number, 'id': {'$ne': id}}): raise HTTPException(409, 'Unit already exists')
    await database().units.update_one({'id': id}, {'$set': {**data.model_dump(), 'updated_at': now()}})
    after = await get('units', id)
    await log_change(before['project_id'], 'unit', f'Blk {block["name"]} · #{data.level:02}-{data.number} updated', user, before, after)
    return after

@router.post('/units/{id}/reset-sample', response_model=Record)
async def reset_sample(id: str, user: dict = Depends(require_roles(*OPS_ROLES))):
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
    await log(unit['project_id'], 'stage', f'Blk {unit["block"]} · #{unit["level"]:02}-{unit["number"]} · Sample progress reset', user)
    return await get('units', id)

@router.post('/units/{id}/advance', response_model=Record)
async def advance(id: str, data: AdvanceIn, user: dict = Depends(require_roles(*OPS_ROLES))):
    unit = await get('units', id)
    stage = unit['stage']
    if stage != data.expected_stage: raise HTTPException(409, 'Unit changed. Refresh and retry.')
    if stage >= 9: raise HTTPException(400, 'Unit already complete')
    if stage == 5: raise HTTPException(400, 'RTO approval required before plastering')
    # Phase 2: a critical defect blocks any stage advancement until verified/cancelled.
    blocker = await database().defects.find_one(
        {'unit_id': id, 'severity': 'critical', 'status': {'$nin': ['verified', 'cancelled']}},
        {'_id': 0, 'title': 1})
    if blocker: raise HTTPException(400, f"Blocked by critical defect: {blocker['title']}")
    if stage == 8:
        tests = await database().tests.find({'unit_id': id}, {'_id': 0}).sort('created_at', 1).to_list(10000)
        latest = {t['point_id']: t for t in tests}
        if not unit['points'] or any(latest.get(p['id'], {}).get('result') != 'pass' for p in unit['points']): raise HTTPException(400, 'A passing test is required for every point')
    update = await database().units.update_one({'id': id, 'stage': stage}, {'$set': {'stage': stage+1, 'sample': False, 'updated_at': now()}, '$push': {'history': {'stage': stage, 'note': data.note, 'at': now()}}})
    if not update.modified_count: raise HTTPException(409, 'Unit changed. Refresh and retry.')
    await log(unit['project_id'], 'stage', f'Blk {unit["block"]} · #{unit["level"]:02}-{unit["number"]} · {STAGES[stage]} completed', user)
    return await get('units', id)

@router.post('/units/{id}/inspections', response_model=Record)
async def request_inspection(id: str, data: InspectionIn, user: dict = Depends(require_roles(*OPS_ROLES))):
    unit = await get('units', id)
    # Validate the readiness checklist BEFORE touching the unit, so a rejected
    # request never leaves the unit in a half-updated state.
    project = await get('projects', unit['project_id'])
    template = project.get('rto_checklist_template') or DEFAULT_RTO_CHECKLIST
    if not data.checklist:
        raise HTTPException(400, 'RTO readiness checklist is required — confirm every item before requesting')
    submitted = [c.item for c in data.checklist]
    if submitted != template:
        raise HTTPException(400, 'Readiness checklist does not match the project template')
    if not all(c.checked for c in data.checklist):
        raise HTTPException(400, 'All readiness checklist items must be confirmed')
    result = await database().units.update_one({'id': id, 'stage': 5, 'rto': {'$in': ['none', 'rework']}}, {'$set': {'rto': 'pending', 'sample': False, 'updated_at': now()}})
    if not result.modified_count: raise HTTPException(400, 'Complete installation first; only one pending inspection is allowed')
    checklist = [{'item': c.item, 'checked': True,
                  'checked_by': {'id': user['id'], 'name': user['name']},
                  'checked_at': now()} for c in data.checklist]
    doc = {'id': uid(), 'project_id': unit['project_id'], 'unit_id': id, 'block': unit['block'], 'unit_label': f'#{unit["level"]:02}-{unit["number"]}', **data.model_dump(mode='json', exclude={'checklist'}), 'checklist': checklist, 'requested_by': {'id': user['id'], 'name': user['name']}, 'decided_by': None, 'decided_at': None, 'status': 'pending', 'created_at': now()}
    await log(unit['project_id'], 'inspection', f'Blk {unit["block"]} · {doc["unit_label"]} · RTO inspection requested', user)
    return await save('inspections', doc)

@router.post('/inspections/{id}/decision', response_model=Record)
async def decide(id: str, data: DecisionIn, user: dict = Depends(require_roles(*DECIDE_ROLES))):
    inspection = await get('inspections', id)
    if inspection['status'] != 'pending': raise HTTPException(400, 'Inspection is already closed')
    unit = await get('units', inspection['unit_id'])
    changed = await database().units.update_one({'id': unit['id'], 'stage': 5, 'rto': 'pending'}, {'$set': {'stage': 6 if data.result == 'approved' else 5, 'rto': data.result, 'sample': False, 'updated_at': now()}, '$push': {'history': {'stage': 5, 'note': data.note, 'inspector': data.inspector, 'result': data.result, 'at': now()}}})
    if not changed.modified_count: raise HTTPException(409, 'Unit is not awaiting this inspection')
    await database().inspections.update_one({'id': id}, {'$set': {'status': data.result, 'inspector': data.inspector, 'note': data.note, 'decided_by': {'id': user['id'], 'name': user['name']}, 'decided_at': now()}})
    await log(unit['project_id'], 'inspection', f'Blk {unit["block"]} · {inspection["unit_label"]} · RTO {data.result}', user)
    requester_id = (inspection.get('requested_by') or {}).get('id')
    if requester_id and requester_id != user['id']:
        from notify import notify
        await notify(requester_id, 'rto_decided',
                     f'RTO {data.result}: Blk {unit["block"]} · {inspection["unit_label"]}',
                     f'Decided by {user["name"]}' + (f' · {data.note[:200]}' if data.note else ''),
                     {'page': 'inspections', 'id': id})
    return await get('inspections', id)

@router.post('/units/{id}/points', response_model=Record)
async def add_point(id: str, data: PointIn, user: dict = Depends(require_roles(*OPS_ROLES))):
    unit = await get('units', id)
    if unit['stage'] == 9: raise HTTPException(400, 'Completed unit cannot accept new points')
    if any(p['name'].lower() == data.name.lower() for p in unit['points']): raise HTTPException(409, 'Point already exists')
    await database().units.update_one({'id': id}, {'$push': {'points': {'id': uid(), **data.model_dump()}}})
    await log(unit['project_id'], 'unit', f'Blk {unit["block"]} · {data.name} point added', user)
    return await get('units', id)

@router.post('/units/{id}/tests', response_model=Record)
async def record_test(id: str, data: TestIn, user: dict = Depends(require_roles(*OPS_ROLES))):
    unit = await get('units', id)
    if unit['stage'] != 8: raise HTTPException(400, 'Tests are recorded at the insulation testing stage')
    point = next((p for p in unit['points'] if p['id'] == data.point_id), None)
    if not point: raise HTTPException(404, 'Point not found')
    claimed = await database().units.update_one({'id': id, 'stage': 8, 'updated_at': unit['updated_at']}, {'$set': {'sample': False, 'updated_at': now()}})
    if not claimed.modified_count: raise HTTPException(409, 'Unit changed. Refresh and retry.')
    doc = {'id': uid(), 'project_id': unit['project_id'], 'unit_id': id, 'point_name': point['name'], 'block': unit['block'], 'unit_label': f'#{unit["level"]:02}-{unit["number"]}', **data.model_dump(), 'created_at': now()}
    await log(unit['project_id'], 'test', f'Blk {unit["block"]} · {point["name"]} · Test {data.result}', user)
    return await save('tests', doc)

@router.get('/projects/{pid}/export/{kind}')
async def export(pid: str, kind: str, user: dict = Depends(get_current_user)):
    await get('projects', pid)
    fields = {'units': ['block','level','number','unit_type','stage','rto','assigned_to','note'], 'workers':['name','trade','block','daily_rate','phone'], 'materials':['name','unit','stock','minimum','unit_cost'], 'expenses':['date','description','category','amount','block','reference'], 'inspections':['block','unit_label','inspector','date','status','note'], 'tests':['block','unit_label','point_name','voltage','l_n','l_e','n_e','result','tested_by'], 'attendance':['worker_id','date','status','hours','daily_rate']}
    if kind not in fields: raise HTTPException(400, 'Invalid export type')
    if is_worker(user) and kind == 'expenses': raise HTTPException(403, 'You do not have permission for this action')
    filt = {'project_id': pid}
    if kind == 'expenses':
        filt['deleted'] = {'$ne': True}
    docs = await database()[kind].find(filt, {'_id': 0}).to_list(50000)
    if is_worker(user):
        if kind == 'materials':
            for d in docs: d.pop('unit_cost', None)
        elif kind == 'workers':
            for d in docs: d.pop('daily_rate', None); d.pop('phone', None)
        elif kind == 'attendance':
            for d in docs: d.pop('daily_rate', None)
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
    return Response('﻿'+stream.getvalue(), media_type='text/csv; charset=utf-8', headers={'Content-Disposition': f'attachment; filename="voltcraft-{kind}.csv"'})
