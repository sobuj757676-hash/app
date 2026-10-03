from datetime import datetime, timezone, timedelta
import random

STAGES = ['Slab PVC', 'Casting complete', 'Point hacking', 'Wire pulling', 'GI/PVC & gang boxes', 'RTO approval', 'Plastering', 'Accessories fitting', 'Insulation testing']

def points_for(uid):
    return [{'id': f'{uid}-p{i}', 'name': n, 'kind': k} for i, (n, k) in enumerate([('P-01 · Living room', 'power'), ('L-01 · Living room', 'light'), ('S-01 · Kitchen', 'socket'), ('SW-01 · Bedroom', 'switch')])]

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
    # TEMP DEBUG (remove after diagnosis)
    print(f"[seed] _seed_admin upsert: matched={res.matched_count} modified={res.modified_count} upserted_id={res.upserted_id}")
    doc = await db.users.find_one({'id': 'user-admin'}, {'password_hash': 0})
    print(f"[seed] admin doc now: {doc}")

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
    for coll in ['projects', 'blocks', 'units', 'workers', 'materials', 'expenses', 'inspections', 'tests', 'activity', 'movements', 'attendance', 'users']:
        await db[coll].create_index('id', unique=True)
    await db.units.create_index([('project_id', 1), ('block_id', 1), ('level', 1), ('number', 1)], unique=True)
    await db.attendance.create_index([('worker_id', 1), ('date', 1)], unique=True)
    await db.users.create_index('email', unique=True, sparse=True)
    await db.users.create_index('phone', unique=True, sparse=True)
    await _seed_admin(db)
    await _seed_demo_worker(db)
    if await db.projects.count_documents({}):
        return
    now = datetime.now(timezone.utc)
    today = now.astimezone(__import__('zoneinfo').ZoneInfo('Asia/Singapore')).date().isoformat()
    project = {'id': 'rail-garden', 'name': 'Rail Garden', 'location': 'Choa Chu Kang, Singapore', 'company': 'VoltCraft Electrical', 'budget': 480000, 'target_date': (now + timedelta(days=180)).date().isoformat(), 'sample': True, 'created_at': now.isoformat()}
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