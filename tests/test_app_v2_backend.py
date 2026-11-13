"""Backend additions for the VoltCraft Site app v2 (approved 2026-11-13):
gzip workspace responses, supervisor batch attendance (roll-call), defect
create dedupe via client_id, app_meta in the workspace payload, and 30-day
tokens for field roles (worker/supervisor) vs 7 days for office roles.
"""
import base64
import json
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from pymongo import MongoClient

SYNC = MongoClient(os.environ['MONGO_URL'])
DB = SYNC[os.environ['DB_NAME']]


def _today_sg():
    return datetime.now(ZoneInfo('Asia/Singapore')).date().isoformat()


def _make_worker(client, headers, pid, name):
    r = client.post(f'/api/projects/{pid}/workers', headers=headers,
                    json={'name': name, 'trade': 'Wireman', 'daily_rate': 120})
    assert r.status_code == 200, r.text[:300]
    return r.json()


def _decode_payload(token):
    part = token.split('.')[1]
    part += '=' * (-len(part) % 4)
    return json.loads(base64.urlsafe_b64decode(part))


def test_batch_attendance_supervisor_rollcall(client, users, me, pid):
    w1 = _make_worker(client, users['supervisor'], pid, 'Roll Call One')
    w2 = _make_worker(client, users['supervisor'], pid, 'Roll Call Two')
    today = _today_sg()
    body = {'entries': [
        {'worker_id': w1['id'], 'date': today, 'status': 'present', 'hours': 10},
        {'worker_id': w2['id'], 'date': today, 'status': 'absent', 'hours': 8},
    ]}
    r = client.post(f'/api/projects/{pid}/attendance/batch',
                    headers=users['supervisor'], json=body)
    assert r.status_code == 200, r.text[:300]
    assert r.json()['saved'] == 2
    d1 = DB.attendance.find_one({'worker_id': w1['id'], 'date': today})
    d2 = DB.attendance.find_one({'worker_id': w2['id'], 'date': today})
    assert d1['status'] == 'present' and d1['hours'] == 10
    assert d1['marked_by'] == me['supervisor']
    assert d2['status'] == 'absent' and d2['hours'] == 0  # hours zeroed unless present

    # Re-submit (supervisor correction) upserts — still exactly one doc.
    body['entries'][0]['status'] = 'leave'
    r = client.post(f'/api/projects/{pid}/attendance/batch',
                    headers=users['supervisor'], json=body)
    assert r.status_code == 200, r.text[:300]
    assert DB.attendance.count_documents({'worker_id': w1['id'], 'date': today}) == 1
    assert DB.attendance.find_one({'worker_id': w1['id'], 'date': today})['status'] == 'leave'


def test_batch_attendance_forbidden_for_workers(client, users, pid):
    body = {'entries': [{'worker_id': 'whoever', 'date': _today_sg(),
                         'status': 'present', 'hours': 8}]}
    r = client.post(f'/api/projects/{pid}/attendance/batch',
                    headers=users['worker'], json=body)
    assert r.status_code == 403, r.text[:200]


def test_batch_attendance_unknown_worker_rejected(client, users, pid):
    body = {'entries': [{'worker_id': 'no-such-worker', 'date': _today_sg(),
                         'status': 'present', 'hours': 8}]}
    r = client.post(f'/api/projects/{pid}/attendance/batch',
                    headers=users['supervisor'], json=body)
    assert r.status_code == 400, r.text[:200]


def test_defect_create_dedupes_on_client_id(client, users, pid):
    payload = {'title': 'Choked conduit', 'description': '[ROOM:KITCHEN][ISSUE:CHOKED_CONDUIT]',
               'category': 'workmanship', 'severity': 'major',
               'client_id': 'v2-test-client-1'}
    r1 = client.post(f'/api/projects/{pid}/defects', headers=users['worker'], json=payload)
    assert r1.status_code == 200, r1.text[:300]
    r2 = client.post(f'/api/projects/{pid}/defects', headers=users['worker'], json=payload)
    assert r2.status_code == 200, r2.text[:300]
    assert r2.json()['id'] == r1.json()['id']
    assert DB.defects.count_documents({'project_id': pid, 'client_id': 'v2-test-client-1'}) == 1

    # Without client_id there is no dedupe — two reports, two defects.
    plain = {'title': 'Damaged backbox', 'category': 'workmanship', 'severity': 'minor'}
    ra = client.post(f'/api/projects/{pid}/defects', headers=users['worker'], json=plain)
    rb = client.post(f'/api/projects/{pid}/defects', headers=users['worker'], json=plain)
    assert ra.json()['id'] != rb.json()['id']


def test_workspace_carries_app_meta_and_gzip(client, admin, pid):
    r = client.get(f'/api/projects/{pid}/workspace', headers=admin)
    assert r.status_code == 200, r.text[:200]
    meta = r.json()['app_meta']
    assert meta['latest_version_code'] == 2
    assert meta['min_version_code'] == 1
    assert 'apk_url' in meta

    r2 = client.get(f'/api/projects/{pid}/workspace',
                    headers={**admin, 'Accept-Encoding': 'gzip'})
    assert r2.status_code == 200
    assert r2.headers.get('content-encoding') == 'gzip'


def test_field_roles_get_30_day_tokens_office_roles_7(client):
    def login(identifier):
        r = client.post('/api/auth/login',
                        json={'identifier': identifier, 'password': 'password123'})
        assert r.status_code == 200, r.text[:200]
        return _decode_payload(r.json()['token'])

    for ident in ('py-wk@l.co', 'py-sup@l.co'):
        p = login(ident)
        span = timedelta(seconds=p['exp'] - p['iat'])
        assert span == timedelta(days=30), (ident, span)
    r = client.post('/api/auth/login', json={'identifier': 'admin@voltcraft.local',
                                             'password': 'changeme123'})
    p = _decode_payload(r.json()['token'])
    assert timedelta(seconds=p['exp'] - p['iat']) == timedelta(days=7)
