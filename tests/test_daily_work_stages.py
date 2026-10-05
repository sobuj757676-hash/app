"""Dynamic workflow stages + daily work plan backend tests (pytest).

Covers: stage defaults + read migration, PUT validation, delete guard,
reorder warning count, stage-groups derivation, bulk-advance with RTO gate.
"""
import os

from pymongo import MongoClient

SYNC = MongoClient(os.environ['MONGO_URL'])
DB = SYNC[os.environ['DB_NAME']]

DEFAULT_NAMES = ['Slab PVC', 'Casting complete', 'Point hacking', 'Wire pulling',
                 'GI/PVC & gang boxes', 'RTO approval', 'Plastering',
                 'Accessories fitting', 'Insulation testing']


def _default_stages_payload():
    return [{'id': f's{i}', 'name': n, 'name_key': f'stage{i}', 'requires_rto': i == 5}
            for i, n in enumerate(DEFAULT_NAMES)]


def _restore(pid, client, admin):
    # Move any units sitting at/past the end back inside first, otherwise the
    # delete guard (correctly) refuses to shrink the list.
    DB.units.update_many({'project_id': pid, 'stage': {'$gte': 9}},
                         {'$set': {'stage': 8}})
    r = client.put(f'/api/projects/{pid}/stages', headers=admin,
                   json={'stages': _default_stages_payload()})
    assert r.status_code == 200, r.text[:200]
    return r.json()


# ---------- defaults & migration ----------

def test_stages_defaults(client, users, pid):
    r = client.get(f'/api/projects/{pid}/stages', headers=users['viewer'])
    assert r.status_code == 200, r.text[:160]
    stages = r.json()
    assert [s['id'] for s in stages] == [f's{i}' for i in range(9)]
    assert [s['name'] for s in stages] == DEFAULT_NAMES
    assert [s['name_key'] for s in stages] == [f'stage{i}' for i in range(9)]
    assert [i for i, s in enumerate(stages) if s['requires_rto']] == [5]


def test_stages_in_workspace_payload(client, users, pid):
    ws = client.get(f'/api/projects/{pid}/workspace', headers=users['supervisor']).json()
    assert len(ws['project'].get('workflow_stages') or []) == 9


def test_stages_read_migration_backfills(client, users, pid):
    DB.projects.update_one({'id': pid}, {'$unset': {'workflow_stages': ''}})
    assert 'workflow_stages' not in DB.projects.find_one({'id': pid})
    r = client.get(f'/api/projects/{pid}/stages', headers=users['viewer'])
    assert r.status_code == 200 and len(r.json()) == 9
    # persisted, not just returned
    assert len(DB.projects.find_one({'id': pid})['workflow_stages']) == 9


# ---------- PUT validation & roles ----------

def test_put_stages_roles(client, users, pid):
    body = {'stages': _default_stages_payload()}
    r = client.put(f'/api/projects/{pid}/stages', headers=users['supervisor'], json=body)
    assert r.status_code == 403
    r = client.put(f'/api/projects/{pid}/stages', headers=users['viewer'], json=body)
    assert r.status_code == 403
    r = client.put(f'/api/projects/{pid}/stages', headers=users['engineer'], json=body)
    assert r.status_code == 403


def test_put_stages_validation(client, admin, pid):
    r = client.put(f'/api/projects/{pid}/stages', headers=admin, json={'stages': []})
    assert r.status_code == 422, r.text[:160]
    dup = _default_stages_payload()
    dup[1] = dict(dup[1], id='s0')
    r = client.put(f'/api/projects/{pid}/stages', headers=admin, json={'stages': dup})
    assert r.status_code == 400 and 'unique' in r.text.lower(), r.text[:160]
    bad = _default_stages_payload()
    bad[2] = dict(bad[2], name='  ')
    r = client.put(f'/api/projects/{pid}/stages', headers=admin, json={'stages': bad})
    assert r.status_code == 422, r.text[:160]


def test_put_stages_delete_guard(client, admin, pid):
    # Drop the RTO stage (index 5): seeded units sit at/past it.
    dropped = [s for s in _default_stages_payload() if s['id'] != 's5']
    r = client.put(f'/api/projects/{pid}/stages', headers=admin, json={'stages': dropped})
    assert r.status_code == 400 and 'RTO approval' in r.text, r.text[:160]
    # Drop index 0: every unit has stage >= 0.
    dropped0 = [s for s in _default_stages_payload() if s['id'] != 's0']
    r = client.put(f'/api/projects/{pid}/stages', headers=admin, json={'stages': dropped0})
    assert r.status_code == 400, r.text[:160]
    # List unchanged after rejected writes.
    assert len(client.get(f'/api/projects/{pid}/stages', headers=admin).json()) == 9


def test_put_stages_add_rename_reorder(client, admin, pid):
    try:
        # Rename (same ids): affected 0, names updated.
        renamed = [dict(s, name=s['name'] + ' *') for s in _default_stages_payload()]
        r = client.put(f'/api/projects/{pid}/stages', headers=admin, json={'stages': renamed})
        assert r.status_code == 200 and r.json()['affected_units'] == 0
        assert r.json()['stages'][0]['name'] == 'Slab PVC *'
        _restore(pid, client, admin)
        # Append: units past the old end (stage 9 == complete in seed data) now
        # point at the new stage, so exactly those count as affected.
        n_past_end = DB.units.count_documents({'project_id': pid, 'stage': {'$gte': 9}})
        extended = _default_stages_payload() + [
            {'id': 's9', 'name': 'Snagging', 'name_key': None, 'requires_rto': False}]
        r = client.put(f'/api/projects/{pid}/stages', headers=admin, json={'stages': extended})
        assert r.status_code == 200, r.text[:160]
        assert r.json()['affected_units'] == n_past_end, r.json()
        assert len(r.json()['stages']) == 10
        # Reorder: put two known units at stages 0/1, then swap them.
        u0 = DB.units.find_one({'project_id': pid})
        u1 = DB.units.find_one({'project_id': pid, 'id': {'$ne': u0['id']}})
        DB.units.update_one({'id': u0['id']}, {'$set': {'stage': 0}})
        DB.units.update_one({'id': u1['id']}, {'$set': {'stage': 1}})
        swapped = extended
        swapped[0], swapped[1] = swapped[1], swapped[0]
        r = client.put(f'/api/projects/{pid}/stages', headers=admin, json={'stages': swapped})
        assert r.status_code == 200, r.text[:160]
        assert r.json()['affected_units'] >= 2, r.json()
        assert r.json()['stages'][0]['id'] == 's1'
    finally:
        _restore(pid, client, admin)


# ---------- stage-groups ----------

def test_stage_groups(client, users, pid):
    r = client.get(f'/api/projects/{pid}/stage-groups', headers=users['supervisor'])
    assert r.status_code == 200, r.text[:160]
    groups = r.json()
    assert groups, 'expected at least one stage group'
    keys = {'block_id', 'block', 'level', 'stage_index', 'stage_id',
            'stage_name', 'stage_name_key', 'total_units', 'remaining_units', 'unit_ids'}
    for g in groups:
        assert keys <= set(g), g
        assert g['remaining_units'] == len(g['unit_ids']) > 0
        assert g['stage_index'] < g['total_units'] + 9  # sanity
    # sorted by block, level, stage_index
    order = [(g['block'], g['level'], g['stage_index']) for g in groups]
    assert order == sorted(order), order[:5]
    # remaining sums to the block/level total; stage names resolve from defaults
    by_bl = {}
    for g in groups:
        by_bl.setdefault((g['block'], g['level']), []).append(g)
    for (block, level), gs in by_bl.items():
        assert sum(g['remaining_units'] for g in gs) == gs[0]['total_units'] > 0
    sample = groups[0]
    assert sample['stage_name'] == DEFAULT_NAMES[sample['stage_index']]
    assert sample['stage_name_key'] == f"stage{sample['stage_index']}"
    # cross-check one group against the DB
    g = groups[0]
    n = DB.units.count_documents({'project_id': pid, 'block': g['block'],
                                  'level': g['level'], 'stage': g['stage_index']})
    assert n == g['remaining_units']


def test_stage_groups_roles(client, users, pid):
    r = client.get(f'/api/projects/{pid}/stage-groups', headers=users['worker'])
    assert r.status_code == 403
    r = client.get(f'/api/projects/{pid}/stage-groups', headers=users['viewer'])
    assert r.status_code == 403
    r = client.get(f'/api/projects/{pid}/stage-groups', headers=users['engineer'])
    assert r.status_code == 200


# ---------- bulk advance ----------

_used_units = set()

def _unit_at(pid, stage):
    u = DB.units.find_one({'project_id': pid, 'id': {'$nin': list(_used_units)}})
    _used_units.add(u['id'])
    DB.units.update_one({'id': u['id']}, {'$set': {'stage': stage, 'rto': 'none'}})
    return u['id']


def test_bulk_advance_rto_gate(client, users, pid):
    uid = _unit_at(pid, 4)
    # 4 -> 5 passes no requires_rto stage: ok
    r = client.post(f'/api/projects/{pid}/units/bulk-advance', headers=users['supervisor'],
                    json={'unit_ids': [uid], 'to_stage': 5})
    assert r.status_code == 200, r.text[:160]
    assert r.json()['results'] == [{'unit_id': uid, 'ok': True}]
    assert DB.units.find_one({'id': uid})['stage'] == 5
    # 5 -> 6 leaves the RTO stage without approval: rejected per unit
    r = client.post(f'/api/projects/{pid}/units/bulk-advance', headers=users['supervisor'],
                    json={'unit_ids': [uid], 'to_stage': 6})
    res = r.json()['results'][0]
    assert res['ok'] is False and 'RTO' in res['error'], res
    assert DB.units.find_one({'id': uid})['stage'] == 5
    # approve RTO, then it goes through
    DB.units.update_one({'id': uid}, {'$set': {'rto': 'approved'}})
    r = client.post(f'/api/projects/{pid}/units/bulk-advance', headers=users['supervisor'],
                    json={'unit_ids': [uid], 'to_stage': 6})
    assert r.json()['results'][0]['ok'] is True
    assert DB.units.find_one({'id': uid})['stage'] == 6


def test_bulk_advance_partial_and_validation(client, users, pid):
    good = _unit_at(pid, 5)
    DB.units.update_one({'id': good}, {'$set': {'rto': 'approved'}})
    gated = _unit_at(pid, 5)  # rto 'none' -> blocked leaving stage 5
    r = client.post(f'/api/projects/{pid}/units/bulk-advance', headers=users['supervisor'],
                    json={'unit_ids': [good, gated, 'missing-id'], 'to_stage': 6})
    assert r.status_code == 200, r.text[:160]
    by_id = {x['unit_id']: x for x in r.json()['results']}
    assert by_id[good]['ok'] is True
    assert by_id[gated]['ok'] is False and 'RTO' in by_id[gated]['error']
    assert by_id['missing-id']['ok'] is False
    # to_stage out of range
    r = client.post(f'/api/projects/{pid}/units/bulk-advance', headers=users['supervisor'],
                    json={'unit_ids': [good], 'to_stage': 9})
    assert r.status_code == 400, r.text[:160]
    # target at/below current stage
    r = client.post(f'/api/projects/{pid}/units/bulk-advance', headers=users['supervisor'],
                    json={'unit_ids': [good], 'to_stage': 4})
    assert r.json()['results'][0]['ok'] is False
    # roles
    r = client.post(f'/api/projects/{pid}/units/bulk-advance', headers=users['worker'],
                    json={'unit_ids': [good], 'to_stage': 5})
    assert r.status_code == 403
    r = client.post(f'/api/projects/{pid}/units/bulk-advance', headers=users['viewer'],
                    json={'unit_ids': [good], 'to_stage': 5})
    assert r.status_code == 403


def test_single_advance_uses_dynamic_rto_gate(client, users, pid):
    # /advance can never step past a requires_rto stage directly; approval
    # flows through the inspection decision (engineer+), which moves the unit.
    uid = _unit_at(pid, 5)
    r = client.post(f'/api/units/{uid}/advance', headers=users['supervisor'],
                    json={'expected_stage': 5, 'note': 'x'})
    assert r.status_code == 400 and 'RTO approval' in r.text, r.text[:160]
    tpl = client.get(f'/api/projects/{pid}/settings/rto-checklist',
                     headers=users['supervisor']).json()['template']
    good = {'inspector': 'RTO Officer', 'date': '2026-10-05', 'note': '',
            'checklist': [{'item': i, 'checked': True} for i in tpl]}
    r = client.post(f'/api/units/{uid}/inspections', headers=users['supervisor'], json=good)
    assert r.status_code == 200, r.text[:160]
    r = client.post(f"/api/inspections/{r.json()['id']}/decision", headers=users['engineer'],
                    json={'result': 'approved', 'inspector': 'RTO Officer', 'note': 'ok'})
    assert r.status_code == 200, r.text[:160]
    assert DB.units.find_one({'id': uid})['stage'] == 6
