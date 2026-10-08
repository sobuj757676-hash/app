from datetime import datetime, timezone, timedelta
import copy
import random

STAGES = ['Slab PVC', 'Casting complete', 'Point hacking', 'Wire pulling', 'GI/PVC & gang boxes', 'RTO approval', 'Plastering', 'Accessories fitting', 'Insulation testing']

# Default workflow stages. Stored per project as `workflow_stages` (ordered
# list of {id, name, name_key, requires_rto}); seeded onto any project missing
# it (same backfill pattern as the RTO checklist). The RTO approval gate lives
# on index 5; name_key keeps the built-in bn/zh translations working.
DEFAULT_WORKFLOW_STAGES = [
    {'id': f's{i}', 'name': name, 'name_key': f'stage{i}', 'requires_rto': i == 5}
    for i, name in enumerate(STAGES)
]

# Default RTO readiness checklist template. Stored per project as
# `rto_checklist_template`; seeded onto any project missing it so older
# projects (incl. the Rail Garden demo) get it automatically.
DEFAULT_RTO_CHECKLIST = [
    'All conduit points hacked / exposed',
    'Wires pulled and labeled',
    'Gang boxes installed where required',
    'Work area cleaned and accessible',
    'Relevant drawing revision available on site',
    'Previous defects on this unit verified closed',
]

def points_for(uid):
    return [{'id': f'{uid}-p{i}', 'name': n, 'kind': k} for i, (n, k) in enumerate([('P-01 · Living room', 'power'), ('L-01 · Living room', 'light'), ('S-01 · Kitchen', 'socket'), ('SW-01 · Bedroom', 'switch')])]

# Room mix + point templates (Phase: room mix builder).
# Templates live per project as `point_templates: {room_type: [{room, kind, count}]}`;
# seeded onto any project missing them (same pattern as the RTO checklist).
ROOM_TYPES = ['2-room', '3-room', '4-room', '5-room', 'executive']
POINT_KINDS = ['power', 'light', 'socket', 'switch', 'aircon', 'heater', 'fan', 'data']
KIND_PREFIX = {'power': 'P', 'light': 'L', 'socket': 'S', 'switch': 'SW',
               'aircon': 'AC', 'heater': 'H', 'fan': 'F', 'data': 'D'}

def _mk(rows):
    """rows: list of (room, kind, count) -> template row dicts."""
    return [{'room': r, 'kind': k, 'count': c} for r, k, c in rows]

def _rep(label, n, kinds):
    """Repeat (kind, count) pairs across n numbered rooms."""
    out = []
    for i in range(1, n + 1):
        for kind, count in kinds:
            out.append((f'{label} {i}', kind, count))
    return out

DEFAULT_POINT_TEMPLATES = {
    '2-room': _mk([
        ('Living/Bedroom', 'power', 4), ('Living/Bedroom', 'light', 2), ('Living/Bedroom', 'switch', 2),
        ('Bedroom', 'power', 3), ('Bedroom', 'light', 1), ('Bedroom', 'switch', 1),
        ('Kitchen', 'power', 3), ('Kitchen', 'light', 1), ('Kitchen', 'socket', 1),
        ('Bathroom', 'light', 1), ('Bathroom', 'switch', 1), ('Bathroom', 'heater', 1),
    ]),
    '3-room': _mk([
        ('Living', 'power', 5), ('Living', 'light', 2), ('Living', 'switch', 2), ('Living', 'fan', 1),
        *_rep('Bedroom', 2, [('power', 4), ('light', 1), ('switch', 1)]),
        ('Kitchen', 'power', 4), ('Kitchen', 'light', 1), ('Kitchen', 'socket', 2),
        *_rep('Bathroom', 2, [('light', 1), ('switch', 1), ('heater', 1)]),
        ('Yard', 'power', 1), ('Yard', 'light', 1),
    ]),
    '4-room': _mk([
        ('Living', 'power', 6), ('Living', 'light', 2), ('Living', 'switch', 2), ('Living', 'fan', 1), ('Living', 'data', 1),
        *_rep('Bedroom', 3, [('power', 4), ('light', 1), ('switch', 1), ('fan', 1)]),
        ('Kitchen', 'power', 4), ('Kitchen', 'light', 1), ('Kitchen', 'socket', 2), ('Kitchen', 'switch', 1),
        *_rep('Bathroom', 2, [('light', 1), ('switch', 1), ('heater', 1)]),
        ('Yard', 'power', 1), ('Yard', 'light', 1),
    ]),
    '5-room': _mk([
        ('Living', 'power', 8), ('Living', 'light', 3), ('Living', 'switch', 3), ('Living', 'fan', 1), ('Living', 'data', 2),
        *_rep('Bedroom', 3, [('power', 4), ('light', 1), ('switch', 1), ('fan', 1), ('aircon', 1)]),
        ('Kitchen', 'power', 5), ('Kitchen', 'light', 2), ('Kitchen', 'socket', 2), ('Kitchen', 'switch', 1),
        *_rep('Bathroom', 2, [('light', 1), ('switch', 1), ('heater', 1)]),
        ('Yard', 'power', 2), ('Yard', 'light', 1),
    ]),
    'executive': _mk([
        ('Living', 'power', 8), ('Living', 'light', 3), ('Living', 'switch', 3), ('Living', 'fan', 1), ('Living', 'data', 2),
        *_rep('Bedroom', 4, [('power', 4), ('light', 1), ('switch', 1), ('fan', 1), ('aircon', 1)]),
        ('Kitchen', 'power', 5), ('Kitchen', 'light', 2), ('Kitchen', 'socket', 2), ('Kitchen', 'switch', 1),
        *_rep('Bathroom', 3, [('light', 1), ('switch', 1), ('heater', 1)]),
        ('Yard', 'power', 2), ('Yard', 'light', 1),
    ]),
}

GENERIC_TEMPLATE = _mk([('Living', 'power', 2), ('Living', 'light', 1), ('Living', 'switch', 1)])

def points_for_template(room_type, unit_id, templates):
    """Expand a room type's point template into unit points.

    Point name format: {PREFIX}-{nn} · {room}, numbering per kind across the
    unit; point id {unit_id}-p{i}. Falls back to a small generic template when
    the room type has no template. Never touches existing units — callers use
    this only when creating new units.
    """
    rows = (templates or {}).get(room_type) or GENERIC_TEMPLATE
    counters, points, i = {}, [], 0
    for row in rows:
        kind = (row.get('kind') or '').strip()
        if kind not in KIND_PREFIX:
            continue
        try:
            count = int(row.get('count', 0))
        except (TypeError, ValueError):
            continue
        room = str(row.get('room') or 'General').strip()[:40] or 'General'
        for _ in range(max(0, min(count, 50))):
            counters[kind] = counters.get(kind, 0) + 1
            points.append({'id': f'{unit_id}-p{i}',
                           'name': f"{KIND_PREFIX[kind]}-{counters[kind]:02d} · {room}",
                           'kind': kind})
            i += 1
    return points

async def _seed_admin(db):
    """Bootstrap admin login. Upsert by id: never overwrites an existing admin,
    and never skipped just because other users exist (serverless instances can
    otherwise race and leave the admin missing)."""
    from auth import hash_password
    now = datetime.now(timezone.utc).isoformat()
    res = await db.users.update_one(
        {'id': 'user-admin'},
        {'$setOnInsert': {
            'id': 'user-admin', 'email': 'admin@voltcraft.local',
            'name': 'Site Admin', 'password_hash': hash_password('changeme123'),
            'role': 'admin', 'worker_id': None, 'active': True,
            'must_change_password': True, 'created_at': now, 'last_login_at': None,
        }},
        upsert=True,
    )

async def _seed_demo_worker(db):
    """Demo worker login linked to the first active worker. Upsert by id."""
    from auth import hash_password
    worker = await db.workers.find_one({'active': True}, sort=[('id', 1)])
    if not worker:
        return
    # Login identifier: the worker's phone when set, else a fixed handle stored
    # in the phone field so the identifier-based login lookup finds it.
    phone = (worker.get('phone') or '').strip() or 'worker-demo'
    now = datetime.now(timezone.utc).isoformat()
    await db.users.update_one(
        {'id': 'user-worker-demo'},
        {'$setOnInsert': {
            'id': 'user-worker-demo', 'phone': phone,
            'name': worker['name'], 'password_hash': hash_password('worker123'),
            'role': 'worker', 'worker_id': worker['id'], 'active': True,
            'must_change_password': False, 'created_at': now, 'last_login_at': None,
        }},
        upsert=True,
    )

async def initialize(db):
    for coll in ['projects', 'blocks', 'units', 'workers', 'materials', 'expenses', 'inspections', 'tests', 'activity', 'movements', 'attendance', 'users', 'defects', 'tasks', 'photos', 'notifications']:
        await db[coll].create_index('id', unique=True)
    await db.units.create_index([('project_id', 1), ('block_id', 1), ('level', 1), ('number', 1)], unique=True)
    await db.attendance.create_index([('worker_id', 1), ('date', 1)], unique=True)
    await db.users.create_index('email', unique=True, sparse=True)
    await db.users.create_index('phone', unique=True, sparse=True)
    await db.defects.create_index([('project_id', 1), ('status', 1)])
    await db.defects.create_index([('project_id', 1), ('assigned_to', 1)])
    await db.tasks.create_index([('project_id', 1), ('assignees', 1), ('status', 1)])
    await db.tasks.create_index('active_unit_keys', unique=True, sparse=True)
    await db.tasks.create_index('plan_group_key', unique=True, sparse=True)
    await db.tasks.create_index([('project_id', 1), ('plan_date', 1)])
    await db.photos.create_index([('project_id', 1), ('entity_type', 1), ('entity_id', 1)])
    await db.notifications.create_index([('user_id', 1), ('read', 1), ('created_at', -1)])
    await _seed_admin(db)
    await _seed_demo_worker(db)
    # Backfill the RTO checklist template onto projects created before Phase 2.
    await db.projects.update_many(
        {'rto_checklist_template': {'$exists': False}},
        {'$set': {'rto_checklist_template': DEFAULT_RTO_CHECKLIST}})
    # Backfill point templates onto projects created before the room-mix feature.
    await db.projects.update_many(
        {'point_templates': {'$exists': False}},
        {'$set': {'point_templates': DEFAULT_POINT_TEMPLATES}})
    # Backfill workflow stages onto projects created before dynamic stages.
    await db.projects.update_many(
        {'workflow_stages': {'$exists': False}},
        {'$set': {'workflow_stages': copy.deepcopy(DEFAULT_WORKFLOW_STAGES)}})
    # Migrate legacy tasks: assigned_to -> assignees:[assigned_to],
    # assigned_to_name -> assignee_names:[name]; old keys dropped.
    legacy = await db.tasks.find(
        {'assignees': {'$exists': False}},
        {'_id': 0, 'id': 1, 'assigned_to': 1, 'assigned_to_name': 1}).to_list(100000)
    for t in legacy:
        aid = t.get('assigned_to')
        aname = (t.get('assigned_to_name') or '').strip()
        await db.tasks.update_one(
            {'id': t['id']},
            {'$set': {'assignees': [aid] if aid else [],
                      'assignee_names': [aname] if aname else []},
             '$unset': {'assigned_to': '', 'assigned_to_name': ''}})
    if await db.projects.count_documents({}):
        return
    import os
    if os.environ.get('SEED_SAMPLE_DATA', 'true').lower() == 'false':
        return
    now = datetime.now(timezone.utc)
    today = now.astimezone(__import__('zoneinfo').ZoneInfo('Asia/Singapore')).date().isoformat()
    project = {'id': 'rail-garden', 'name': 'Rail Garden', 'location': 'Choa Chu Kang, Singapore', 'company': 'VoltCraft Electrical', 'budget': 480000, 'target_date': (now + timedelta(days=180)).date().isoformat(), 'rto_checklist_template': DEFAULT_RTO_CHECKLIST, 'point_templates': DEFAULT_POINT_TEMPLATES, 'workflow_stages': copy.deepcopy(DEFAULT_WORKFLOW_STAGES), 'sample': True, 'created_at': now.isoformat()}
    await db.projects.insert_one(project)
    rng = random.Random(46)
    units, blocks, inspections, tests = [], [], [], []
    specs = [('35A', 11, 90, 401), ('35B', 11, 122, 419), ('35C', 10, 109, 445), ('36A', 9, 64, 471), ('36B', 7, 48, 487), ('36C', 5, 32, 503)]
    for bi, (name, levels, total, start) in enumerate(specs):
        bid = f'blk-{name.lower()}'
        blocks.append({'id': bid, 'project_id': 'rail-garden', 'name': name, 'levels': levels, 'planned_units': total, 'sample_layout': True})
        per_floor, extra = divmod(total, levels - 1)
        for level in range(2, levels + 1):
            count = per_floor + (1 if level - 2 < extra else 0)
            for j in range(count):
                number = str(start + j * 2)
                uid = f'{bid}-{level:02}-{number}'
                stage = max(0, min(9, 11 - level + rng.choice([-2, -1, 0, 1, 2]) - bi // 2))
                rto = 'approved' if stage >= 6 else ('pending' if stage == 5 else 'none')
                if stage == 5 and rng.random() < .16:
                    rto = 'rework'
                unit = {'id': uid, 'project_id': 'rail-garden', 'block_id': bid, 'block': name, 'level': level, 'number': number, 'unit_type': ['4-room', '3-room', '2-room Flexi'][j % 3], 'stage': stage, 'rto': rto, 'assigned_to': ['Team Alpha', 'Team Bravo', 'Team Delta'][bi % 3], 'note': '', 'points': points_for(uid), 'history': [], 'updated_at': now.isoformat(), 'sample': True}
                units.append(unit)
                if stage >= 5:
                    inspections.append({'id': f'insp-{uid}', 'project_id': 'rail-garden', 'unit_id': uid, 'block': name, 'unit_label': f'#{level:02}-{number}', 'inspector': 'Lim Wei Ming', 'date': today, 'status': rto, 'note': 'Gang box alignment to be rectified.' if rto == 'rework' else 'Concealed conduit and gang box inspection.', 'created_at': now.isoformat(), 'sample': True})
                if stage == 9:
                    for point in unit['points']:
                        tests.append({'id': f'test-{point["id"]}', 'project_id': 'rail-garden', 'unit_id': uid, 'point_id': point['id'], 'point_name': point['name'], 'block': name, 'unit_label': f'#{level:02}-{number}', 'voltage': 500, 'l_n': 200, 'l_e': 200, 'n_e': 200, 'result': 'pass', 'tested_by': 'Tan Jun Jie', 'note': 'Sample test record', 'created_at': now.isoformat(), 'sample': True})
    await db.blocks.insert_many(blocks)
    await db.units.insert_many(units)
    if inspections: await db.inspections.insert_many(inspections)
    if tests: await db.tests.insert_many(tests)
    workers = []
    for i, name in enumerate(['Mohammad Sobuj', 'Tan Jun Jie', 'Abdul Rahman', 'Chen Wei', 'Mohammad Rakib', 'Lim Wei Ming', 'Arif Hossain', 'Li Ming', 'Sohail Ahmed', 'Rahim Uddin', 'Wang Lei', 'Kumar Raj']):
        workers.append({'id': f'worker-{i+1}', 'project_id': 'rail-garden', 'name': name, 'trade': ['Electrician', 'Electrician', 'Supervisor', 'Wireman'][i % 4], 'block': specs[i % 6][0], 'daily_rate': [95, 110, 140, 100][i % 4], 'phone': '', 'active': True})
    await db.workers.insert_many(workers)
    await db.attendance.insert_many([{'id': f'att-{w["id"]}-{today}', 'project_id': 'rail-garden', 'worker_id': w['id'], 'date': today, 'status': 'present' if i < 10 else 'absent', 'hours': 8 if i < 10 else 0, 'daily_rate': w['daily_rate']} for i, w in enumerate(workers)])
    materials = [('PVC conduit · 20 mm', 'lengths', 480, 100, 2.4), ('GI conduit · 25 mm', 'lengths', 160, 50, 6.8), ('Single gang box', 'pcs', 42, 80, 1.5), ('2.5 mm² cable · Red', 'rolls', 32, 10, 68), ('13A switched socket', 'pcs', 240, 60, 5.8), ('CAT6 data cable', 'rolls', 6, 8, 120), ('Light switch · 1 gang', 'pcs', 320, 80, 3.2)]
    await db.materials.insert_many([{'id': f'material-{i+1}', 'project_id': 'rail-garden', 'name': n, 'unit': u, 'stock': s, 'minimum': m, 'unit_cost': c} for i, (n,u,s,m,c) in enumerate(materials)])
    expenses = [('PVC conduit & fittings', 'materials', 12480, '35A'), ('September site wages', 'labour', 28400, ''), ('Cable delivery · Batch 04', 'materials', 18250, '35B'), ('Scissor lift rental', 'equipment', 3800, '36A'), ('Site transport', 'transport', 1450, ''), ('GI gang boxes · Supply', 'materials', 6200, '35C')]
    await db.expenses.insert_many([{'id': f'expense-{i+1}', 'project_id': 'rail-garden', 'description': n, 'category': c, 'amount': a, 'date': (now-timedelta(days=i)).date().isoformat(), 'block': b, 'reference': f'INV-2026-{104+i}', 'created_at': now.isoformat()} for i,(n,c,a,b) in enumerate(expenses)])
    await db.activity.insert_many([{'id': f'activity-{i}', 'project_id': 'rail-garden', 'kind': kind, 'message': msg, 'created_at': (now-timedelta(minutes=i*27+12)).isoformat()} for i,(kind,msg) in enumerate([('inspection','Blk 35A · RTO inspection records added'), ('stage','Blk 36A · Wire pulling progress updated'), ('material','Single gang box · Stock below minimum'), ('workforce','Daily attendance recorded for 12 workers')])])
    # Fresh databases seed workers above; link the demo worker login now.
    await _seed_demo_worker(db)