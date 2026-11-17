"""VoltCraft v2 Milestone 3: 3-tap zone defects (PRD §3.5 / §7.6).

Covers zone-linked defect creation with the verbatim PRD payload shape,
client_defect_id dedupe, idempotency-key replay, tenant isolation, the
OPEN -> FIXED -> CLOSED lifecycle with role rules (workers cannot close),
invalid transitions, and work-zone open_defects_count maintenance (the
matrix KPI that was a static 0 before M3).
"""
import itertools
import os
import sys

import pytest
from pymongo import MongoClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'api'))
from auth import hash_password  # noqa: E402

SYNC = MongoClient(os.environ['MONGO_URL'])
DB = SYNC[os.environ['DB_NAME']]

_keys = itertools.count(1)


def _login(client, identifier, password):
    r = client.post('/api/auth/login',
                    json={'identifier': identifier, 'password': password})
    assert r.status_code == 200, f'login {identifier}: {r.text[:200]}'
    return {'Authorization': f"Bearer {r.json()['token']}"}


def _payload(zone_id, client_defect_id, **over):
    """The PRD §7.6 create payload, verbatim field names."""
    body = {
        'client_defect_id': client_defect_id,
        'work_zone_id': zone_id,
        'room_code': 'KITCHEN',
        'issue_code': 'WRONG_POINT_HEIGHT',
        'local_photo_filename': f'defect_{client_defect_id}.jpg',
        'watermark_text': 'VOLTCRAFT • BLK 401A • #08-101 • KITCHEN',
        'reported_at': '2026-11-16T09:42:18+08:00',
        'idempotency_key': f'm3-key-{next(_keys)}',
    }
    body.update(over)
    return body


@pytest.fixture(scope='module')
def super_h(client):
    return _login(client, 'super@voltcraft.local', 'changeme123')


@pytest.fixture(scope='module')
def tenant(client, super_h):
    """A fresh tenant + company_admin + one spatial project + a worker."""
    payload = {
        'company_name': 'M3 Electrical Pte Ltd',
        'uen_number': '202699988Z', 'bca_grade': 'ME05',
        'subscription_tier': 'PRO', 'max_projects': 5, 'max_users': 100,
        'office_address': 'Singapore', 'contact_phone': '65554444',
        'admin_full_name': 'M3 Admin', 'admin_phone': '93334444',
        'admin_temp_password': 'InitPassword#2026',
    }
    r = client.post('/api/v2/super-admin/tenants', headers=super_h, json=payload)
    assert r.status_code == 201, r.text[:300]
    company_id = r.json()['company_id']
    admin_h = _login(client, '93334444', 'InitPassword#2026')
    proj = {
        'project_code': 'M3-TST', 'project_name': 'M3 Test BTO',
        'project_type': 'HDB_BTO', 'main_contractor_name': 'Main Con Pte Ltd',
        'blocks_config': [{
            'block': '401A', 'floor_from': 8, 'floor_to': 8,
            'stacks': [{'stack': '101', 'unit_type': '4-Room'}],
        }],
    }
    rp = client.post('/api/v2/projects', headers=admin_h, json=proj)
    assert rp.status_code == 201, rp.text[:400]
    pid = rp.json()['project']['id']
    # A worker belonging to this tenant (v1 user creation has no tenant
    # concept, so seed the user doc directly with the tenant company_id).
    DB.users.insert_one({
        'id': 'user-m3-worker', 'name': 'M3 Worker',
        'email': 'm3-worker@l.co', 'password_hash': hash_password('password123'),
        'role': 'worker', 'company_id': company_id, 'worker_id': None,
        'active': True, 'must_change_password': False,
        'created_at': '2026-11-16T00:00:00+08:00', 'last_login_at': None,
    })
    worker_h = _login(client, 'm3-worker@l.co', 'password123')
    return {'company_id': company_id, 'admin_h': admin_h,
            'worker_h': worker_h, 'pid': pid}


def _zone(client, headers, pid):
    r = client.get(f'/api/v2/projects/{pid}/matrix', headers=headers)
    assert r.status_code == 200, r.text[:300]
    zones = r.json()['zones']
    return next(z for z in zones
                if z['zone_category'] == 'ZONE_1_RESIDENTIAL')


def _zone_count(client, headers, pid, zone_id):
    r = client.get(f'/api/v2/projects/{pid}/matrix', headers=headers)
    zone = next(z for z in r.json()['zones'] if z['id'] == zone_id)
    return zone['open_defects_count'], r.json()['kpis']['open_defects']


# (a) create + zone count ----------------------------------------------------

def test_create_zone_defect(client, tenant):
    zone = _zone(client, tenant['admin_h'], tenant['pid'])
    r = client.post(f"/api/v2/projects/{tenant['pid']}/defects",
                    headers=tenant['worker_h'],
                    json=_payload(zone['id'], 'm3-defect-001'))
    assert r.status_code == 201, r.text[:300]
    d = r.json()
    assert d['status'] == 'OPEN'
    assert d['client_defect_id'] == 'm3-defect-001'
    assert d['work_zone_id'] == zone['id']
    assert d['block'] == '401A' and d['floor'] == 'L08'
    assert d['unit_or_zone_code'] == zone['zone_code']
    assert d['room_code'] == 'KITCHEN'
    assert d['issue_code'] == 'WRONG_POINT_HEIGHT'
    assert d['reported_by_user_id'] == 'user-m3-worker'
    count, kpi = _zone_count(client, tenant['admin_h'], tenant['pid'], zone['id'])
    assert count == 1 and kpi == 1


def test_create_dedupe_and_idempotency(client, tenant):
    zone = _zone(client, tenant['admin_h'], tenant['pid'])
    body = _payload(zone['id'], 'm3-defect-002')
    r1 = client.post(f"/api/v2/projects/{tenant['pid']}/defects",
                     headers=tenant['admin_h'], json=body)
    assert r1.status_code == 201, r1.text[:300]
    # Same idempotency key replayed -> stored response, no second defect.
    r2 = client.post(f"/api/v2/projects/{tenant['pid']}/defects",
                     headers=tenant['admin_h'], json=body)
    assert r2.json()['id'] == r1.json()['id']
    # Same client_defect_id under a fresh key -> dedupe returns the original.
    body2 = _payload(zone['id'], 'm3-defect-002')
    r3 = client.post(f"/api/v2/projects/{tenant['pid']}/defects",
                     headers=tenant['admin_h'], json=body2)
    assert r3.json()['id'] == r1.json()['id']
    lst = client.get(f"/api/v2/projects/{tenant['pid']}/defects",
                     headers=tenant['admin_h'])
    mine = [d for d in lst.json() if d['client_defect_id'] == 'm3-defect-002']
    assert len(mine) == 1
    count, _ = _zone_count(client, tenant['admin_h'], tenant['pid'], zone['id'])
    assert count == 2  # defect-001 + defect-002, no duplicates


def test_create_validation_and_zone_scope(client, tenant):
    zone = _zone(client, tenant['admin_h'], tenant['pid'])
    bad = _payload(zone['id'], 'm3-defect-bad', room_code='SAUNA')
    r = client.post(f"/api/v2/projects/{tenant['pid']}/defects",
                    headers=tenant['admin_h'], json=bad)
    assert r.status_code == 422, r.text[:200]
    ghost = _payload('wz-does-not-exist', 'm3-defect-ghost')
    r = client.post(f"/api/v2/projects/{tenant['pid']}/defects",
                    headers=tenant['admin_h'], json=ghost)
    assert r.status_code == 404, r.text[:200]
    assert r.json()['detail']['error_code'] == 'ZONE_NOT_FOUND'


def test_tenant_isolation(client, tenant, admin):
    # The v1 admin belongs to company-default: the tenant's project and its
    # defects are indistinguishable from missing.
    r = client.get(f"/api/v2/projects/{tenant['pid']}/defects", headers=admin)
    assert r.status_code == 404, r.text[:200]
    r = client.put('/api/v2/defects/m3-defect-001/status', headers=admin,
                   json={'target_status': 'FIXED'})
    assert r.status_code == 404, r.text[:200]


def test_worker_visibility(client, tenant):
    # The worker reported defect-001; the admin reported defect-002.
    lst = client.get(f"/api/v2/projects/{tenant['pid']}/defects",
                     headers=tenant['worker_h'])
    assert lst.status_code == 200
    ids = {d['client_defect_id'] for d in lst.json()}
    assert ids == {'m3-defect-001'}


# (b) lifecycle ---------------------------------------------------------------

def test_lifecycle_open_fixed_closed(client, tenant):
    zone = _zone(client, tenant['admin_h'], tenant['pid'])
    # OPEN -> CLOSED directly is not a legal step.
    r = client.put('/api/v2/defects/m3-defect-001/status',
                   headers=tenant['admin_h'], json={'target_status': 'CLOSED'})
    assert r.status_code == 422, r.text[:200]
    assert r.json()['detail']['error_code'] == 'INVALID_DEFECT_TRANSITION'
    # The reporting worker marks it FIXED.
    r = client.put('/api/v2/defects/m3-defect-001/status',
                   headers=tenant['worker_h'], json={'target_status': 'FIXED'})
    assert r.status_code == 200, r.text[:200]
    d = r.json()
    assert d['status'] == 'FIXED' and d['fixed_by_user_id'] == 'user-m3-worker'
    assert d['fixed_at']
    # FIXED still counts as open work on the zone.
    count, _ = _zone_count(client, tenant['admin_h'], tenant['pid'], zone['id'])
    assert count == 2
    # A worker may NOT close, even the reporter (PRD: supervisor or above).
    r = client.put('/api/v2/defects/m3-defect-001/status',
                   headers=tenant['worker_h'], json={'target_status': 'CLOSED'})
    assert r.status_code == 403, r.text[:200]
    # The tenant admin verifies & closes; the zone count drops.
    r = client.put('/api/v2/defects/m3-defect-001/status',
                   headers=tenant['admin_h'], json={'target_status': 'CLOSED'})
    assert r.status_code == 200, r.text[:200]
    d = r.json()
    assert d['status'] == 'CLOSED' and d['closed_at']
    count, kpi = _zone_count(client, tenant['admin_h'], tenant['pid'], zone['id'])
    assert count == 1 and kpi == 1
    # CLOSED is terminal.
    r = client.put('/api/v2/defects/m3-defect-001/status',
                   headers=tenant['admin_h'], json={'target_status': 'FIXED'})
    assert r.status_code == 422, r.text[:200]


def test_status_idempotency_replay(client, tenant):
    body = {'target_status': 'FIXED', 'idempotency_key': 'm3-status-key-1'}
    r1 = client.put('/api/v2/defects/m3-defect-002/status',
                    headers=tenant['admin_h'], json=body)
    assert r1.status_code == 200, r1.text[:200]
    r2 = client.put('/api/v2/defects/m3-defect-002/status',
                    headers=tenant['admin_h'], json=body)
    assert r2.status_code == 200
    assert r2.json()['status'] == 'FIXED'
    assert r2.json()['fixed_at'] == r1.json()['fixed_at']
