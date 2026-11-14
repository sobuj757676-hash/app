"""VoltCraft v2 Milestone 1: multi-tenant SaaS core + 4-zone spatial engine.

Covers tenant provisioning (super admin), tenant isolation, project zone
generation, the Smart Sub-Main Dependency interlock (409 on S6 before
Corridor C3 + LV Riser R3 are locked), idempotent batch advance,
409_STAGE_LOCKED conflicts, APK release publishing, and gzip on the matrix.
"""
import itertools
import os

import pytest
from pymongo import MongoClient

SYNC = MongoClient(os.environ['MONGO_URL'])
DB = SYNC[os.environ['DB_NAME']]

READINESS = {'work_physically_verified': True,
             'backboxes_conduits_labels_checked': True,
             'no_open_critical_blockers': True}

_keys = itertools.count(1)


def _login(client, identifier, password):
    r = client.post('/api/auth/login', json={'identifier': identifier, 'password': password})
    assert r.status_code == 200, f'login {identifier}: {r.text[:200]}'
    return {'Authorization': f"Bearer {r.json()['token']}"}


def _advance(client, headers, pid, zone_ids, frm, to, key=None):
    return client.post(
        f'/api/v2/projects/{pid}/zones/batch-advance', headers=headers,
        json={'work_zone_ids': zone_ids, 'from_stage_code': frm,
              'to_stage_code': to, 'lock_completed_stage': True,
              'pre_rto_readiness': READINESS,
              'idempotency_key': key or f'test-key-{next(_keys)}'})


@pytest.fixture(scope='module')
def super_h(client):
    return _login(client, 'super@voltcraft.local', 'changeme123')


@pytest.fixture(scope='module')
def prospect(client, super_h):
    """Prospect Electrical Engineering tenant + its company_admin + project."""
    payload = {
        'company_name': 'Prospect Electrical Engineering Pte Ltd',
        'uen_number': '201812345K', 'bca_grade': 'ME05',
        'subscription_tier': 'ENTERPRISE', 'max_projects': 5, 'max_users': 100,
        'office_address': 'Singapore', 'contact_phone': '61234567',
        'admin_full_name': 'Prospect Admin', 'admin_phone': '91112222',
        'admin_temp_password': 'InitPassword#2026',
    }
    r = client.post('/api/v2/super-admin/tenants', headers=super_h, json=payload)
    assert r.status_code == 201, r.text[:300]
    created = r.json()
    admin_h = _login(client, '91112222', 'InitPassword#2026')
    proj = {
        'project_code': 'TGH-C12', 'project_name': 'Tengah BTO C12',
        'project_type': 'HDB_BTO', 'main_contractor_name': 'Main Con Pte Ltd',
        'blocks_config': [{
            'block': '401A', 'floor_from': 1, 'floor_to': 2,
            'stacks': [{'stack': '101', 'unit_type': '4-Room'},
                       {'stack': '103', 'unit_type': '3-Room'}],
        }],
    }
    rp = client.post('/api/v2/projects', headers=admin_h, json=proj)
    assert rp.status_code == 201, rp.text[:400]
    body = rp.json()
    return {'tenant': created, 'admin_h': admin_h,
            'project': body['project'], 'generation': body['generation']}


def _zones(client, headers, pid):
    r = client.get(f'/api/v2/projects/{pid}/matrix', headers=headers)
    assert r.status_code == 200, r.text[:300]
    return r.json()['zones']


def _pick(zones, category, floor, code_part=None):
    for z in zones:
        if z['zone_category'] == category and z['floor'] == floor:
            if code_part is None or code_part in z['zone_code']:
                return z
    raise AssertionError(f'zone not found: {category} {floor} {code_part}')


# (a) tenant provisioning ----------------------------------------------------

def test_tenant_provisioning(client, super_h, admin, prospect):
    company = prospect['tenant']['company']
    assert prospect['tenant']['status'] == 'ACTIVE'
    assert company['subscription_tier'] == 'ENTERPRISE'
    assert len(company['enabled_modules']) == 14
    assert 'QS_PROGRESS_PROFIT' in company['enabled_modules']

    dup = {
        'company_name': 'Copycat Electrical Pte Ltd',
        'uen_number': '201812345K', 'subscription_tier': 'STARTER',
        'admin_full_name': 'Copy Cat', 'admin_phone': '96667777',
        'admin_temp_password': 'InitPassword#2026',
    }
    r = client.post('/api/v2/super-admin/tenants', headers=super_h, json=dup)
    assert r.status_code == 409, r.text[:200]
    assert r.json()['detail']['error_code'] == 'UEN_EXISTS'

    # The v1 admin is not a platform super admin.
    r = client.post('/api/v2/super-admin/tenants', headers=admin, json=dup)
    assert r.status_code == 403, r.text[:200]

    r = client.get('/api/v2/super-admin/tenants', headers=super_h)
    assert r.status_code == 200
    row = next(c for c in r.json() if c['id'] == company['id'])
    assert row['project_count'] == 1 and row['user_count'] == 1


# (b) spatial generation -----------------------------------------------------

def test_project_zone_generation(prospect):
    gen = prospect['generation']
    assert gen['by_category']['ZONE_1_RESIDENTIAL'] == 4   # 2 floors x 2 stacks
    assert gen['by_category']['ZONE_2_CORRIDOR'] == 2      # 1 per floor
    assert gen['by_category']['ZONE_3_RISER'] == 4         # LV + ELV per floor
    assert gen['by_category']['ZONE_4_EXTERNAL'] == 4      # default set per block
    assert gen['total'] == 14
    pid = prospect['project']['id']
    # One zone_task per zone per stage: 4*6 + 2*5 + 4*5 + 4*5 = 74.
    assert DB.zone_tasks.count_documents({'project_id': pid}) == 74
    zones = list(DB.work_zones.find({'project_id': pid}))
    res = next(z for z in zones if z['zone_category'] == 'ZONE_1_RESIDENTIAL')
    assert res['current_stage_code'] == 'S1'
    assert res['submain_ready'] is False
    assert len(res['parent_dependency_zone_ids']) == 2
    assert set(res['stage_status_map']) == {'S1', 'S2', 'S3', 'S4', 'S5', 'S6'}


# (c) tenant isolation ---------------------------------------------------------

def test_tenant_isolation(client, super_h, prospect):
    payload = {
        'company_name': 'Rival Electrical Pte Ltd', 'uen_number': '202099888Z',
        'subscription_tier': 'STARTER',
        'admin_full_name': 'Rival Admin', 'admin_phone': '92223333',
        'admin_temp_password': 'InitPassword#2026',
    }
    r = client.post('/api/v2/super-admin/tenants', headers=super_h, json=payload)
    assert r.status_code == 201, r.text[:300]
    rival_h = _login(client, '92223333', 'InitPassword#2026')
    pid = prospect['project']['id']

    r = client.get(f'/api/v2/projects/{pid}/matrix', headers=rival_h)
    assert r.status_code == 404, r.text[:200]

    zones = _zones(client, prospect['admin_h'], pid)
    res = _pick(zones, 'ZONE_1_RESIDENTIAL', 'L01', '101')
    r = _advance(client, rival_h, pid, [res['id']], 'S1', 'S2')
    assert r.status_code == 404, r.text[:200]

    r = client.get('/api/v2/projects', headers=rival_h)
    assert r.status_code == 200 and r.json() == []


# (d) sub-main interlock -----------------------------------------------------

def test_submain_interlock(client, prospect):
    h, pid = prospect['admin_h'], prospect['project']['id']
    zones = _zones(client, h, pid)
    res = _pick(zones, 'ZONE_1_RESIDENTIAL', 'L01', '101')
    corridor = _pick(zones, 'ZONE_2_CORRIDOR', 'L01')
    riser = _pick(zones, 'ZONE_3_RISER', 'L01', 'LV-RISER')

    for frm, to in [('S1', 'S2'), ('S2', 'S3'), ('S3', 'S4'), ('S4', 'S5')]:
        r = _advance(client, h, pid, [res['id']], frm, to)
        assert r.status_code == 200, r.text[:300]

    # S6 is hard-locked while Corridor C3 / LV Riser R3 are incomplete.
    r = _advance(client, h, pid, [res['id']], 'S5', 'S6')
    assert r.status_code == 409, r.text[:300]
    assert r.json()['detail']['error_code'] == '409_SUBMAIN_DEPENDENCY_UNMET'
    assert r.json()['detail']['work_zone_id'] == res['id']

    for zone, frm, to in [(corridor, 'C1', 'C2'), (corridor, 'C2', 'C3'),
                          (riser, 'R1', 'R2'), (riser, 'R2', 'R3')]:
        r = _advance(client, h, pid, [zone['id']], frm, to)
        assert r.status_code == 200, r.text[:300]

    r = client.get(f"/api/v2/zones/{res['id']}", headers=h)
    assert r.status_code == 200, r.text[:200]
    body = r.json()
    assert body['submain_ready'] is True
    assert len(body['dependencies']) == 2
    assert all(d['dependency_completed'] for d in body['dependencies'])
    codes = {d['dependency_stage_code'] for d in body['dependencies']}
    assert codes == {'C3', 'R3'}

    r = _advance(client, h, pid, [res['id']], 'S5', 'S6')
    assert r.status_code == 200, r.text[:300]
    assert r.json()['advanced'] == [res['id']]
    r = client.get(f"/api/v2/zones/{res['id']}", headers=h)
    assert r.json()['current_stage_code'] == 'S6'


# (e) idempotency --------------------------------------------------------------

def test_batch_advance_idempotency(client, prospect):
    h, pid = prospect['admin_h'], prospect['project']['id']
    corridor = _pick(_zones(client, h, pid), 'ZONE_2_CORRIDOR', 'L02')
    r1 = _advance(client, h, pid, [corridor['id']], 'C1', 'C2', key='idem-fixed-1')
    assert r1.status_code == 200, r1.text[:300]
    r2 = _advance(client, h, pid, [corridor['id']], 'C1', 'C2', key='idem-fixed-1')
    assert r2.status_code == 200, r2.text[:300]
    assert r2.json() == r1.json()
    # The zone advanced exactly once (a real second C1->C2 would 409).
    r = client.get(f"/api/v2/zones/{corridor['id']}", headers=h)
    assert r.json()['current_stage_code'] == 'C2'


# (f) stage-locked conflict ------------------------------------------------------

def test_batch_advance_stage_locked(client, prospect):
    h, pid = prospect['admin_h'], prospect['project']['id']
    res = _pick(_zones(client, h, pid), 'ZONE_1_RESIDENTIAL', 'L01', '103')
    assert res['current_stage_code'] == 'S1'
    r = _advance(client, h, pid, [res['id']], 'S3', 'S4')
    assert r.status_code == 409, r.text[:300]
    detail = r.json()['detail']
    assert detail['error_code'] == '409_STAGE_LOCKED'
    assert detail['server_state']['current_stage_code'] == 'S1'
    # Skipping a stage is also rejected.
    r = _advance(client, h, pid, [res['id']], 'S1', 'S3')
    assert r.status_code == 422, r.text[:300]
    assert r.json()['detail']['error_code'] == 'INVALID_STAGE_TRANSITION'
    # Incomplete Pre-RTO checklist is rejected.
    r = client.post(f'/api/v2/projects/{pid}/zones/batch-advance', headers=h,
                    json={'work_zone_ids': [res['id']], 'from_stage_code': 'S1',
                          'to_stage_code': 'S2',
                          'pre_rto_readiness': {'a': True, 'b': True, 'c': False},
                          'idempotency_key': 'bad-readiness-1'})
    assert r.status_code == 422, r.text[:300]
    assert r.json()['detail']['error_code'] == 'PRE_RTO_CHECKLIST_INCOMPLETE'


# (g) APK release ------------------------------------------------------------------

def test_apk_release_publish_and_fetch(client, super_h, prospect):
    payload = {'version_code': 205, 'version_name': '2.0.5',
               'min_required_version_code': 200,
               'apk_download_url': 'https://example.com/voltcraft-205.apk',
               'sha256_checksum': 'a' * 64, 'release_notes_en': 'Milestone 1 test'}
    r = client.post('/api/v2/super-admin/apk-releases', headers=super_h, json=payload)
    assert r.status_code == 201, r.text[:300]
    assert r.json()['version_code'] == 205
    r = client.get('/api/v2/app-release', headers=prospect['admin_h'])
    assert r.status_code == 200, r.text[:200]
    assert r.json()['version_code'] == 205
    assert r.json()['min_required_version_code'] == 200


# (h) gzip ---------------------------------------------------------------------------

def test_matrix_gzip(client, prospect):
    pid = prospect['project']['id']
    r = client.get(f'/api/v2/projects/{pid}/matrix',
                   headers={**prospect['admin_h'], 'Accept-Encoding': 'gzip'})
    assert r.status_code == 200, r.text[:200]
    assert r.headers.get('content-encoding') == 'gzip'
    body = r.json()
    assert body['kpis']['total_zones'] == 14
    assert body['kpis']['by_category']['ZONE_1_RESIDENTIAL']['total'] == 4
