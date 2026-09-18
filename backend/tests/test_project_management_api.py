import os
import time
import requests
import pytest


BASE_ROOT = os.environ.get("REACT_APP_BACKEND_URL")
if not BASE_ROOT:
    pytest.skip("REACT_APP_BACKEND_URL is required for public endpoint testing", allow_module_level=True)

BASE_URL = BASE_ROOT.rstrip("/") + "/api"
RUN_ID = str(int(time.time()))


@pytest.fixture(scope="session")
def api_client():
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session


@pytest.fixture(scope="session")
def qa_context(api_client):
    project_payload = {
        "name": f"TEST_QA_{RUN_ID}",
        "location": "Singapore QA",
        "company": "VoltCraft QA",
        "budget": 120000,
        "target_date": "2026-12-31",
    }
    p_res = api_client.post(f"{BASE_URL}/projects", json=project_payload)
    assert p_res.status_code == 200
    project = p_res.json()

    block_payload = {
        "name": f"QAB{RUN_ID[-4:]}",
        "levels": 1,
        "units_per_level": 2,
        "first_unit": 901,
    }
    b_res = api_client.post(f"{BASE_URL}/projects/{project['id']}/blocks", json=block_payload)
    assert b_res.status_code == 200
    block = b_res.json()

    ws = api_client.get(f"{BASE_URL}/projects/{project['id']}/workspace")
    assert ws.status_code == 200
    workspace = ws.json()
    units = [u for u in workspace["units"] if u["block_id"] == block["id"]]
    assert len(units) == 2

    return {
        "project": project,
        "block": block,
        "units": units,
    }


# Module: health and seed workspace validation
def test_health_and_seed_workspace_counts(api_client):
    health = api_client.get(f"{BASE_URL}/")
    assert health.status_code == 200
    assert health.json().get("status") == "ok"

    projects = api_client.get(f"{BASE_URL}/projects")
    assert projects.status_code == 200
    assert isinstance(projects.json(), list)

    seeded = api_client.get(f"{BASE_URL}/projects/rail-garden/workspace")
    assert seeded.status_code == 200
    seeded_data = seeded.json()
    assert len(seeded_data["blocks"]) == 6
    assert len(seeded_data["units"]) == 465


# Module: project/block/unit creation and isolation
def test_create_project_block_and_edit_unit_metadata(api_client, qa_context):
    pid = qa_context["project"]["id"]
    target_unit = qa_context["units"][0]

    unit_edit = {
        "level": 1,
        "number": target_unit["number"],
        "unit_type": "5-room",
        "assigned_to": "TEST Team",
        "note": "TEST updated metadata",
    }
    update = api_client.patch(f"{BASE_URL}/units/{target_unit['id']}", json=unit_edit)
    assert update.status_code == 200
    updated = update.json()
    assert updated["unit_type"] == "5-room"
    assert updated["assigned_to"] == "TEST Team"

    qa_ws = api_client.get(f"{BASE_URL}/projects/{pid}/workspace")
    rail_ws = api_client.get(f"{BASE_URL}/projects/rail-garden/workspace")
    assert qa_ws.status_code == 200
    assert rail_ws.status_code == 200
    assert qa_ws.json()["project"]["id"] == pid
    assert rail_ws.json()["project"]["id"] == "rail-garden"


# Module: unit stage workflow, expected_stage guard, and RTO lifecycle
def test_unit_stage_flow_with_rto_rework_and_approval(api_client, qa_context):
    unit_id = qa_context["units"][0]["id"]

    conflict = api_client.post(
        f"{BASE_URL}/units/{unit_id}/advance",
        json={"expected_stage": 1, "note": "wrong expected stage"},
    )
    assert conflict.status_code == 409

    for stage in range(5):
        adv = api_client.post(
            f"{BASE_URL}/units/{unit_id}/advance",
            json={"expected_stage": stage, "note": f"advance {stage}"},
        )
        assert adv.status_code == 200
        assert adv.json()["stage"] == stage + 1

    locked = api_client.post(
        f"{BASE_URL}/units/{unit_id}/advance",
        json={"expected_stage": 5, "note": "try stage5 advance"},
    )
    assert locked.status_code == 400

    req = api_client.post(
        f"{BASE_URL}/units/{unit_id}/inspections",
        json={"inspector": "TEST Inspector", "date": "2026-02-01", "note": "initial request"},
    )
    assert req.status_code == 200
    inspection_id = req.json()["id"]

    rework = api_client.post(
        f"{BASE_URL}/inspections/{inspection_id}/decision",
        json={"result": "rework", "inspector": "TEST Inspector", "note": "fix routing"},
    )
    assert rework.status_code == 200
    assert rework.json()["status"] == "rework"

    req_again = api_client.post(
        f"{BASE_URL}/units/{unit_id}/inspections",
        json={"inspector": "TEST Inspector", "date": "2026-02-02", "note": "resubmitted"},
    )
    assert req_again.status_code == 200

    approve = api_client.post(
        f"{BASE_URL}/inspections/{req_again.json()['id']}/decision",
        json={"result": "approved", "inspector": "TEST Inspector", "note": "approved now"},
    )
    assert approve.status_code == 200
    assert approve.json()["status"] == "approved"

    ws = api_client.get(f"{BASE_URL}/projects/{qa_context['project']['id']}/workspace")
    unit = next(u for u in ws.json()["units"] if u["id"] == unit_id)
    assert unit["stage"] == 6
    assert unit["rto"] == "approved"


# Module: testing-stage constraints and latest pass result behavior
def test_point_tests_gate_completion_and_latest_result_wins(api_client, qa_context):
    unit = qa_context["units"][0]
    unit_id = unit["id"]

    # Move from stage 6 -> 8 (plastering then accessories)
    for stage in [6, 7]:
        adv = api_client.post(
            f"{BASE_URL}/units/{unit_id}/advance",
            json={"expected_stage": stage, "note": f"advance {stage}"},
        )
        assert adv.status_code == 200

    ws = api_client.get(f"{BASE_URL}/projects/{qa_context['project']['id']}/workspace").json()
    current = next(u for u in ws["units"] if u["id"] == unit_id)
    assert current["stage"] == 8
    assert len(current["points"]) == 4

    blocked = api_client.post(
        f"{BASE_URL}/units/{unit_id}/advance",
        json={"expected_stage": 8, "note": "attempt complete before tests"},
    )
    assert blocked.status_code == 400

    first_point = current["points"][0]
    fail = api_client.post(
        f"{BASE_URL}/units/{unit_id}/tests",
        json={
            "point_id": first_point["id"],
            "voltage": 500,
            "l_n": 0,
            "l_e": 0,
            "n_e": 0,
            "result": "fail",
            "tested_by": "TEST Tech",
            "note": "failed once",
        },
    )
    assert fail.status_code == 200
    assert fail.json()["result"] == "fail"

    for p in current["points"][1:]:
        ok = api_client.post(
            f"{BASE_URL}/units/{unit_id}/tests",
            json={
                "point_id": p["id"],
                "voltage": 500,
                "l_n": 200,
                "l_e": 200,
                "n_e": 200,
                "result": "pass",
                "tested_by": "TEST Tech",
                "note": "pass",
            },
        )
        assert ok.status_code == 200

    still_blocked = api_client.post(
        f"{BASE_URL}/units/{unit_id}/advance",
        json={"expected_stage": 8, "note": "should still fail"},
    )
    assert still_blocked.status_code == 400

    retest = api_client.post(
        f"{BASE_URL}/units/{unit_id}/tests",
        json={
            "point_id": first_point["id"],
            "voltage": 500,
            "l_n": 210,
            "l_e": 210,
            "n_e": 210,
            "result": "pass",
            "tested_by": "TEST Tech",
            "note": "retest pass",
        },
    )
    assert retest.status_code == 200

    done = api_client.post(
        f"{BASE_URL}/units/{unit_id}/advance",
        json={"expected_stage": 8, "note": "all pass now"},
    )
    assert done.status_code == 200
    assert done.json()["stage"] == 9


# Module: test recording only at stage8
def test_record_test_rejected_outside_stage8(api_client, qa_context):
    unit_id = qa_context["units"][1]["id"]
    ws = api_client.get(f"{BASE_URL}/projects/{qa_context['project']['id']}/workspace").json()
    unit = next(u for u in ws["units"] if u["id"] == unit_id)

    attempt = api_client.post(
        f"{BASE_URL}/units/{unit_id}/tests",
        json={
            "point_id": unit["points"][0]["id"],
            "voltage": 500,
            "l_n": 100,
            "l_e": 100,
            "n_e": 100,
            "result": "pass",
            "tested_by": "TEST Tech",
            "note": "should fail",
        },
    )
    assert attempt.status_code == 400


# Module: workforce CRUD and attendance rule validation
def test_workforce_create_edit_attendance_archive(api_client, qa_context):
    pid = qa_context["project"]["id"]
    worker_payload = {
        "name": f"TEST Worker {RUN_ID}",
        "trade": "Electrician",
        "block": qa_context["block"]["name"],
        "daily_rate": 120,
        "phone": "12345678",
    }
    created = api_client.post(f"{BASE_URL}/projects/{pid}/workers", json=worker_payload)
    assert created.status_code == 200
    worker = created.json()

    edited = api_client.patch(
        f"{BASE_URL}/workers/{worker['id']}",
        json={**worker_payload, "trade": "Supervisor", "daily_rate": 140},
    )
    assert edited.status_code == 200
    assert edited.json()["trade"] == "Supervisor"

    attendance_absent = api_client.put(
        f"{BASE_URL}/workers/{worker['id']}/attendance",
        json={"date": "2026-02-03", "status": "absent", "hours": 8},
    )
    assert attendance_absent.status_code == 200
    assert attendance_absent.json()["hours"] == 0

    attendance_present = api_client.put(
        f"{BASE_URL}/workers/{worker['id']}/attendance",
        json={"date": "2026-02-04", "status": "present", "hours": 16},
    )
    assert attendance_present.status_code == 200
    assert attendance_present.json()["hours"] == 16
    assert attendance_present.json()["daily_rate"] == 140

    archived = api_client.delete(f"{BASE_URL}/workers/{worker['id']}")
    assert archived.status_code == 200
    assert archived.json().get("ok") is True


# Module: materials metadata and stock movement including overdraw protection
def test_materials_create_edit_and_prevent_overdraw(api_client, qa_context):
    pid = qa_context["project"]["id"]
    material_payload = {
        "name": f"TEST Material {RUN_ID}",
        "unit": "pcs",
        "stock": 5,
        "minimum": 2,
        "unit_cost": 3,
    }
    created = api_client.post(f"{BASE_URL}/projects/{pid}/materials", json=material_payload)
    assert created.status_code == 200
    material = created.json()

    patched = api_client.patch(
        f"{BASE_URL}/materials/{material['id']}",
        json={**material_payload, "name": f"TEST Material {RUN_ID} Updated", "stock": 999},
    )
    assert patched.status_code == 200
    assert patched.json()["name"].endswith("Updated")
    assert patched.json()["stock"] == 5

    overdraw = api_client.post(
        f"{BASE_URL}/materials/{material['id']}/movements",
        json={"kind": "issue", "quantity": 6, "block": qa_context['block']['name'], "note": "too much"},
    )
    assert overdraw.status_code == 400

    receive = api_client.post(
        f"{BASE_URL}/materials/{material['id']}/movements",
        json={"kind": "receive", "quantity": 10, "block": qa_context['block']['name'], "note": "top up"},
    )
    assert receive.status_code == 200

    issue = api_client.post(
        f"{BASE_URL}/materials/{material['id']}/movements",
        json={"kind": "issue", "quantity": 8, "block": qa_context['block']['name'], "note": "consume"},
    )
    assert issue.status_code == 200


# Module: expense CRUD and export safety (UTF-8 BOM + formula escape)
def test_expense_crud_and_csv_export_safety(api_client, qa_context):
    pid = qa_context["project"]["id"]
    create_payload = {
        "description": "=TEST Formula Injection",
        "category": "materials",
        "amount": 101.25,
        "date": "2026-02-05",
        "block": qa_context["block"]["name"],
        "reference": "+REFTEST",
    }
    created = api_client.post(f"{BASE_URL}/projects/{pid}/expenses", json=create_payload)
    assert created.status_code == 200
    exp = created.json()

    edited = api_client.patch(
        f"{BASE_URL}/expenses/{exp['id']}",
        json={**create_payload, "amount": 155.5, "description": "@TEST Updated"},
    )
    assert edited.status_code == 200
    assert edited.json()["amount"] == 155.5

    exported = api_client.get(f"{BASE_URL}/projects/{pid}/export/expenses")
    assert exported.status_code == 200
    assert exported.content.startswith(b"\xef\xbb\xbf")
    csv_text = exported.content.decode("utf-8")
    assert "'@TEST Updated" in csv_text
    assert "'+REFTEST" in csv_text

    deleted = api_client.delete(f"{BASE_URL}/expenses/{exp['id']}")
    assert deleted.status_code == 200
    assert deleted.json().get("ok") is True


# Regression: rejected sample resets must leave all sample records untouched.
def test_sample_reset_preserves_records_when_real_records_exist(api_client):
    ws = api_client.get(f"{BASE_URL}/projects/rail-garden/workspace")
    assert ws.status_code == 200
    data = ws.json()

    candidate = None
    for u in data["units"]:
        if u.get("sample") and u.get("stage") == 5 and u.get("rto") in {"rework", "none"}:
            candidate = u
            break

    if not candidate:
        pytest.skip("No suitable sample unit at stage 5 for reset-sample safety check")

    before_sample_inspections = [
        i for i in data["inspections"] if i["unit_id"] == candidate["id"] and i.get("sample") is True
    ]
    if not before_sample_inspections:
        pytest.skip("Candidate sample unit has no sample inspections to validate unsafe deletion")

    create_real = api_client.post(
        f"{BASE_URL}/units/{candidate['id']}/inspections",
        json={"inspector": "TEST Safety", "date": "2026-02-06", "note": "create real record"},
    )
    if create_real.status_code != 200:
        pytest.skip("Could not create real inspection for reset safety scenario")

    reset = api_client.post(f"{BASE_URL}/units/{candidate['id']}/reset-sample", json={})
    assert reset.status_code == 400

    after = api_client.get(f"{BASE_URL}/projects/rail-garden/workspace")
    assert after.status_code == 200
    after_data = after.json()
    after_sample_inspections = [
        i for i in after_data["inspections"] if i["unit_id"] == candidate["id"] and i.get("sample") is True
    ]

    assert len(after_sample_inspections) == len(before_sample_inspections)
