"""VoltCraft v2 blueprint — Milestone 1: multi-tenant SaaS core + 4-zone
spatial engine (PRD v2.0 Sections 1-2).

Keeps the v1 stack (FastAPI + MongoDB). Every v2 collection carries a
mandatory company_id and all reads go through tenant resolution
(auth.get_current_tenant / the effective-company helpers below), so one
tenant can never see or mutate another tenant's data.

Error convention (all v2 endpoints): HTTPException(status, {"error_code":
"...", "message": "...", ...extra}) — FastAPI serializes the dict under
"detail".
"""
import re
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pymongo.errors import DuplicateKeyError

from auth import get_current_tenant, get_current_user, hash_password, require_roles
from models import (ApkReleaseIn, BatchAdvanceIn, CompanyIn, CompanyPatchIn,
                    DefectV2In, DefectV2StatusIn, ProjectV2In)
from routes import database, now, uid

router = APIRouter(prefix="/v2")

# ---------------------------------------------------------------- constants

_STARTER = ["CORE_4ZONE_MATRIX", "DAILY_PLAN", "BATCH_CHECKOFF",
            "DEFECTS_3TAP", "GANG_ATTENDANCE"]
_PRO = _STARTER + ["DRAWING_VAULT", "VO_CLAIMS", "LIVE_POWER_LOTO",
                   "TOOLBOX_SAFETY", "DIGITAL_TC_SHEETS"]
_ENTERPRISE = _PRO + ["SMART_STORE_WASTAGE", "QR_TOOL_TRACKER",
                      "AUTO_PAYROLL_MOM", "QS_PROGRESS_PROFIT"]

MODULES_BY_TIER = {
    "STARTER": _STARTER,
    "PRO": _PRO,
    "ENTERPRISE": _ENTERPRISE,
}


def _pipeline(pairs):
    return [{"code": code, "name": name} for code, name in pairs]


STAGE_PIPELINES = {
    "ZONE_1_RESIDENTIAL": _pipeline([
        ("S1", "Slab/Precast Conduit"),
        ("S2", "Wall Chasing & Backbox"),
        ("S3", "Cable Pulling/Wiring"),
        ("S4", "DB Box & Final Fix"),
        ("S5", "Testing & Commissioning"),
        ("S6", "RTO Passed & Handover"),
    ]),
    "ZONE_2_CORRIDOR": _pipeline([
        ("C1", "Bracket & Marking"),
        ("C2", "Trunking & GI Conduit"),
        ("C3", "Sub-Main & Circuit Pulling"),
        ("C4", "Fittings & Accessories"),
        ("C5", "Testing & RTO Sign-off"),
    ]),
    "ZONE_3_RISER": _pipeline([
        ("R1", "Ladder, Tray & Trunking"),
        ("R2", "Enclosure & Meter Board"),
        ("R3", "Main & Sub-Main Termination"),
        ("R4", "Earthing, Bonding & Labeling"),
        ("R5", "Fire-Stop & RTO Handover"),
    ]),
    "ZONE_4_EXTERNAL": _pipeline([
        ("M1", "Trunking & Tray Run"),
        ("M2", "Surface GI Conduit"),
        ("M3", "Cable Pulling"),
        ("M4", "Weatherproof Lights & Isolators"),
        ("M5", "Testing & RTO"),
    ]),
}

DEFAULT_EXTERNAL_ZONES = [
    {"zone_code": "L01-SWITCHROOM", "floor": "L01",
     "subtype": "Void Deck & Consumer Switchroom"},
    {"zone_code": "ROOF-PUMP-SOLAR", "floor": "ROOF",
     "subtype": "Roof - Booster Pump, LMR & Solar"},
    {"zone_code": "MSCP-L1-L7", "floor": "MSCP", "subtype": "MSCP Car Park"},
    {"zone_code": "LINKWAY-PAVILION", "floor": "L01",
     "subtype": "Linkway & Pavilion"},
]

PROJECT_CREATE_ROLES = ("super_admin", "company_admin", "admin", "pm", "manager")
BATCH_ADVANCE_ROLES = ("super_admin", "company_admin", "admin", "pm", "manager",
                       "engineer", "supervisor")


def _err(status, code, message, **extra):
    detail = {"error_code": code, "message": message}
    detail.update(extra)
    return HTTPException(status, detail)


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-")


def _zone_id(project_id: str, block: str, zone_code: str) -> str:
    return _slug(f"wz-{project_id}-{block}-{zone_code}")


def _effective_company_id(user: dict):
    """Tenant id for a user; None for the platform super_admin."""
    if user.get("role") == "super_admin":
        return None
    return user.get("company_id") or "company-default"


# ------------------------------------------------------- spatial generator

def _stage_status_map(category: str) -> dict:
    return {s["code"]: {"checked": False, "locked": False}
            for s in STAGE_PIPELINES[category]}


def _zone_doc(company_id, project_id, category, block, floor, zone_code,
              unit_type_or_subtype, parent_ids=None):
    zid = _zone_id(project_id, block, zone_code)
    return {
        "id": zid,
        "company_id": company_id,
        "project_id": project_id,
        "zone_category": category,
        "block": block,
        "floor": floor,
        "zone_code": zone_code,
        "unit_type_or_subtype": unit_type_or_subtype,
        "current_stage_code": STAGE_PIPELINES[category][0]["code"],
        "stage_status_map": _stage_status_map(category),
        "parent_dependency_zone_ids": list(parent_ids or []),
        "submain_ready": False,
        "power_state": "DE_ENERGIZED",
        "loto_padlock_tag": None,
        "open_defects_count": 0,
        "updated_at": now(),
    }


def _tasks_for_zone(zone: dict):
    tasks = []
    for stage in STAGE_PIPELINES[zone["zone_category"]]:
        tasks.append({
            "id": f"ztask-{zone['id']}-{stage['code']}",
            "company_id": zone["company_id"],
            "project_id": zone["project_id"],
            "work_zone_id": zone["id"],
            "block": zone["block"],
            "floor": zone["floor"],
            "zone_category": zone["zone_category"],
            "stage_code": stage["code"],
            "title": stage["name"],
            "title_i18n_json": {"EN": stage["name"]},
            "assigned_worker_ids": [],
            "supervisor_id": None,
            "target_date": None,
            "unit_check_map_json": {},
            "status": "todo",
        })
    return tasks


def _summary_from_zones(zones):
    by_category = {}
    for z in zones:
        by_category[z["zone_category"]] = by_category.get(z["zone_category"], 0) + 1
    return {"total_zones": len(zones), "total": len(zones),
            "by_category": by_category, "counts": dict(by_category),
            **by_category}


async def generate_project_zones(db, company_id, project) -> dict:
    """Generate all work_zones + zone_tasks for a v2 project from its
    blocks_config. Idempotent: a project that already has zones is left
    untouched and its existing counts are returned."""
    project_id = project["id"]
    existing = await db.work_zones.find(
        {"project_id": project_id}, {"_id": 0}).to_list(100000)
    if existing:
        return _summary_from_zones(existing)

    zones = []
    for block_cfg in project.get("blocks_config") or []:
        block = str(block_cfg["block"]).strip()
        floor_from = int(block_cfg["floor_from"])
        floor_to = int(block_cfg["floor_to"])
        for n in range(floor_from, floor_to + 1):
            floor = f"L{n:02d}"
            corridor = _zone_doc(company_id, project_id, "ZONE_2_CORRIDOR",
                                 block, floor, f"{floor}-CORRIDOR", "Corridor")
            lv_riser = _zone_doc(company_id, project_id, "ZONE_3_RISER",
                                 block, floor, f"{floor}-LV-RISER",
                                 "LV Electrical Riser")
            elv_riser = _zone_doc(company_id, project_id, "ZONE_3_RISER",
                                  block, floor, f"{floor}-ELV-RISER",
                                  "ELV/Telecom Riser")
            zones.extend([corridor, lv_riser, elv_riser])
            for stack in block_cfg.get("stacks") or []:
                zones.append(_zone_doc(
                    company_id, project_id, "ZONE_1_RESIDENTIAL", block, floor,
                    f"#{n:02d}-{stack['stack']}", stack["unit_type"],
                    parent_ids=[corridor["id"], lv_riser["id"]]))
        externals = block_cfg.get("external_zones") or DEFAULT_EXTERNAL_ZONES
        for ext in externals:
            zones.append(_zone_doc(company_id, project_id, "ZONE_4_EXTERNAL",
                                   block, ext["floor"], ext["zone_code"],
                                   ext["subtype"]))

    tasks = [t for z in zones for t in _tasks_for_zone(z)]
    if zones:
        await db.work_zones.insert_many(zones)
    if tasks:
        await db.zone_tasks.insert_many(tasks)
    summary = _summary_from_zones(zones)
    summary["total_tasks"] = len(tasks)
    return summary


# ------------------------------------------------------------- super admin

@router.post("/super-admin/tenants", status_code=201)
async def create_tenant(data: CompanyIn,
                        user: dict = Depends(require_roles("super_admin"))):
    db = database()
    if await db.companies.find_one({"uen_number": data.uen_number}):
        raise _err(409, "UEN_EXISTS",
                   f"A company with UEN {data.uen_number} already exists.")
    company_id = "company-" + uuid.uuid4().hex[:12]
    company = {
        "id": company_id,
        "company_name": data.company_name,
        "uen_number": data.uen_number,
        "bca_grade": data.bca_grade,
        "subscription_tier": data.subscription_tier,
        "enabled_modules": list(MODULES_BY_TIER[data.subscription_tier]),
        "max_projects": data.max_projects,
        "max_users": data.max_users,
        "office_address": data.office_address,
        "contact_phone": data.contact_phone,
        "status": "ACTIVE",
        "created_at": now(),
        "created_by": user["id"],
    }
    admin = {
        "id": uid(),
        "name": data.admin_full_name,
        "phone": data.admin_phone,
        "password_hash": hash_password(data.admin_temp_password),
        "role": "company_admin",
        "company_id": company_id,
        "worker_id": None,
        "active": True,
        "must_change_password": False,
        "created_at": now(),
        "last_login_at": None,
    }
    try:
        await db.companies.insert_one(dict(company))
        await db.users.insert_one(admin)
    except DuplicateKeyError:
        await db.companies.delete_one({"id": company_id})
        raise _err(409, "UEN_EXISTS",
                   "A company or admin with these details already exists.")
    return {"company_id": company_id, "admin_user_id": admin["id"],
            "status": "ACTIVE", "company": company}


@router.get("/super-admin/tenants")
async def list_tenants(user: dict = Depends(require_roles("super_admin"))):
    db = database()
    companies = await db.companies.find({}, {"_id": 0}).sort("created_at", 1).to_list(1000)
    for c in companies:
        c["project_count"] = await db.projects.count_documents({"company_id": c["id"]})
        c["user_count"] = await db.users.count_documents({"company_id": c["id"]})
    return companies


@router.patch("/super-admin/tenants/{company_id}")
async def patch_tenant(company_id: str, data: CompanyPatchIn,
                       user: dict = Depends(require_roles("super_admin"))):
    db = database()
    company = await db.companies.find_one({"id": company_id}, {"_id": 0})
    if not company:
        raise _err(404, "COMPANY_NOT_FOUND", f"Company {company_id} not found.")
    patch = data.model_dump(exclude_unset=True)
    if patch.get("subscription_tier") and "enabled_modules" not in patch:
        patch["enabled_modules"] = list(MODULES_BY_TIER[patch["subscription_tier"]])
    if patch:
        patch["updated_at"] = now()
        await db.companies.update_one({"id": company_id}, {"$set": patch})
    return await db.companies.find_one({"id": company_id}, {"_id": 0})


@router.post("/super-admin/apk-releases", status_code=201)
async def publish_apk_release(data: ApkReleaseIn,
                              user: dict = Depends(require_roles("super_admin"))):
    db = database()
    doc = {**data.model_dump(), "published_by": user["id"], "updated_at": now()}
    await db.platform_apk_releases.update_one(
        {"version_code": data.version_code},
        {"$set": doc, "$setOnInsert": {"created_at": now()}},
        upsert=True)
    return await db.platform_apk_releases.find_one(
        {"version_code": data.version_code}, {"_id": 0})


@router.get("/app-release")
async def app_release(user: dict = Depends(get_current_user)):
    db = database()
    latest = await db.platform_apk_releases.find_one(
        {}, {"_id": 0}, sort=[("version_code", -1)])
    if latest:
        return latest
    return {"version_code": 2, "version_name": "2.0.0",
            "min_required_version_code": 1, "apk_download_url": "",
            "release_notes_en": ""}


# ---------------------------------------------------------------- projects

@router.post("/projects", status_code=201)
async def create_project_v2(data: ProjectV2In, tenant: dict = Depends(get_current_tenant)):
    db = database()
    user = tenant["user"]
    if user.get("role") not in PROJECT_CREATE_ROLES:
        raise _err(403, "FORBIDDEN", "You do not have permission to create projects.")
    if user.get("role") == "super_admin":
        if not data.company_id:
            raise _err(400, "COMPANY_ID_REQUIRED",
                       "Super admin must specify company_id for the new project.")
        company_id = data.company_id
    else:
        company_id = _effective_company_id(user)
    company = await db.companies.find_one({"id": company_id}, {"_id": 0})
    if company is None:
        if company_id == "company-default":
            company = {"id": company_id, "company_name": "VoltCraft Electrical",
                       "max_projects": None}
        else:
            raise _err(404, "COMPANY_NOT_FOUND", f"Company {company_id} not found.")
    if company.get("status") == "SUSPENDED":
        raise _err(403, "TENANT_SUSPENDED", "This company account is suspended.")
    max_projects = company.get("max_projects")
    if max_projects:
        count = await db.projects.count_documents({"company_id": company_id})
        if count >= max_projects:
            raise _err(409, "PROJECT_QUOTA_EXCEEDED",
                       f"Company has reached its project quota ({max_projects}).")
    if await db.projects.find_one({"company_id": company_id,
                                   "project_code": data.project_code}):
        raise _err(409, "PROJECT_CODE_EXISTS",
                   f"Project code {data.project_code} already exists for this company.")
    project = {
        "id": uid(),
        "company_id": company_id,
        "project_code": data.project_code,
        "project_name": data.project_name,
        "project_type": data.project_type,
        "main_contractor_name": data.main_contractor_name,
        "blocks_config": data.model_dump()["blocks_config"],
        # v1-compat fields so existing tooling keeps working.
        "name": data.project_name,
        "location": "",
        "company": company.get("company_name", ""),
        "status": "ACTIVE",
        "schema": "v2",
        "created_at": now(),
        "created_by": user["id"],
    }
    await db.projects.insert_one(dict(project))
    generation = await generate_project_zones(db, company_id, project)
    return {"project": project, "generation": generation}


@router.get("/projects")
async def list_projects_v2(tenant: dict = Depends(get_current_tenant)):
    db = database()
    user = tenant["user"]
    filt = {"schema": "v2"}
    company_id = _effective_company_id(user)
    if company_id is not None:
        filt["company_id"] = company_id
    return await db.projects.find(filt, {"_id": 0}).sort("created_at", 1).to_list(1000)


async def _get_tenant_project(db, user, project_id):
    project = await db.projects.find_one({"id": project_id}, {"_id": 0})
    if not project:
        raise _err(404, "PROJECT_NOT_FOUND", f"Project {project_id} not found.")
    company_id = _effective_company_id(user)
    if company_id is not None and project.get("company_id") != company_id:
        # Isolation: another tenant's project is indistinguishable from missing.
        raise _err(404, "PROJECT_NOT_FOUND", f"Project {project_id} not found.")
    return project


@router.get("/projects/{project_id}/matrix")
async def project_matrix(project_id: str,
                         block: str | None = Query(None),
                         floor: str | None = Query(None),
                         tenant: dict = Depends(get_current_tenant)):
    db = database()
    project = await _get_tenant_project(db, tenant["user"], project_id)
    all_zones = await db.work_zones.find(
        {"project_id": project_id}, {"_id": 0}).to_list(100000)
    by_category = {}
    for cat, pipeline in STAGE_PIPELINES.items():
        cat_zones = [z for z in all_zones if z["zone_category"] == cat]
        total_stages = sum(len(z.get("stage_status_map") or {}) for z in cat_zones)
        completed = sum(
            1 for z in cat_zones
            for entry in (z.get("stage_status_map") or {}).values()
            if entry.get("checked"))
        by_category[cat] = {
            "total": len(cat_zones),
            "completed_stages": completed,
            "total_stages": total_stages,
            "pct": round(100.0 * completed / total_stages, 2) if total_stages else 0.0,
        }
    kpis = {
        "total_zones": len(all_zones),
        "by_category": by_category,
        "open_defects": sum(z.get("open_defects_count", 0) for z in all_zones),
        "live_zones": sum(1 for z in all_zones
                          if z.get("power_state") in ("LIVE_230V", "LIVE_400V")),
        "submain_pending": sum(1 for z in all_zones
                               if z["zone_category"] == "ZONE_1_RESIDENTIAL"
                               and not z.get("submain_ready")),
    }
    zones = all_zones
    if block:
        zones = [z for z in zones if z["block"] == block]
    if floor:
        zones = [z for z in zones if z["floor"] == floor]
    return {"project": project, "kpis": kpis, "zones": zones}


@router.get("/zones/{zone_id}")
async def get_zone(zone_id: str, tenant: dict = Depends(get_current_tenant)):
    db = database()
    user = tenant["user"]
    zone = await db.work_zones.find_one({"id": zone_id}, {"_id": 0})
    company_id = _effective_company_id(user)
    if not zone or (company_id is not None and zone.get("company_id") != company_id):
        raise _err(404, "ZONE_NOT_FOUND", f"Work zone {zone_id} not found.")
    dependencies = []
    for dep_id in zone.get("parent_dependency_zone_ids") or []:
        dep = await db.work_zones.find_one({"id": dep_id}, {"_id": 0})
        if not dep:
            continue
        code = _DEP_STAGE.get(dep["zone_category"])
        dependencies.append({
            "id": dep["id"], "zone_code": dep["zone_code"],
            "zone_category": dep["zone_category"], "block": dep["block"],
            "floor": dep["floor"], "current_stage_code": dep["current_stage_code"],
            "dependency_stage_code": code,
            "dependency_completed": _stage_completed(dep, code) if code else False,
        })
    dependents_count = await db.work_zones.count_documents(
        {"parent_dependency_zone_ids": zone_id})
    return {**zone, "dependencies": dependencies,
            "dependents_count": dependents_count}


# ------------------------------------------------------------ batch advance

_DEP_STAGE = {"ZONE_2_CORRIDOR": "C3", "ZONE_3_RISER": "R3"}


def _stage_completed(zone: dict, code: str) -> bool:
    """A dependency stage (Corridor C3 / Riser R3) counts as completed when
    its stage entry is locked, or the zone has advanced to/past it — the
    batch-advance that lands a corridor on C3 is the sub-main pulling step
    itself, so reaching C3 satisfies the interlock (Milestone 1 flow d)."""
    entry = (zone.get("stage_status_map") or {}).get(code, {})
    if entry.get("locked"):
        return True
    pipeline = [s["code"] for s in STAGE_PIPELINES[zone["zone_category"]]]
    try:
        return pipeline.index(zone["current_stage_code"]) >= pipeline.index(code)
    except ValueError:
        return False


async def _dependency_completed(db, dep_id) -> bool:
    dep = await db.work_zones.find_one({"id": dep_id}, {"_id": 0})
    if not dep:
        return False
    code = _DEP_STAGE.get(dep["zone_category"])
    if not code:
        return False
    return _stage_completed(dep, code)


async def _submain_ready(db, residential_zone) -> bool:
    deps = residential_zone.get("parent_dependency_zone_ids") or []
    if len(deps) < 2:
        return False
    results = [await _dependency_completed(db, d) for d in deps]
    return all(results)


async def _recompute_submain(db, project_id, combos):
    """After corridor/riser advances, refresh submain_ready on the
    residential zones of every affected (block, floor)."""
    for block, floor in combos:
        residents = await db.work_zones.find(
            {"project_id": project_id, "zone_category": "ZONE_1_RESIDENTIAL",
             "block": block, "floor": floor}, {"_id": 0}).to_list(10000)
        for rz in residents:
            ready = await _submain_ready(db, rz)
            if ready != bool(rz.get("submain_ready")):
                await db.work_zones.update_one(
                    {"id": rz["id"]},
                    {"$set": {"submain_ready": ready, "updated_at": now()}})


@router.post("/projects/{project_id}/zones/batch-advance")
async def batch_advance(project_id: str, data: BatchAdvanceIn,
                        tenant: dict = Depends(get_current_tenant)):
    db = database()
    user = tenant["user"]
    if user.get("role") not in BATCH_ADVANCE_ROLES:
        raise _err(403, "FORBIDDEN", "You do not have permission to advance stages.")
    project = await _get_tenant_project(db, user, project_id)
    company_id = project["company_id"]

    # Idempotency first: a replayed key returns the stored response verbatim.
    prior = await db.processed_idempotency_keys.find_one(
        {"idempotency_key": data.idempotency_key, "company_id": company_id},
        {"_id": 0})
    if prior:
        return prior["response_body_json"]

    readiness = data.pre_rto_readiness or {}
    if len(readiness) < 3 or not all(v is True for v in readiness.values()):
        raise _err(422, "PRE_RTO_CHECKLIST_INCOMPLETE",
                   "All 3 Pre-RTO readiness confirmations are required before advancing.")

    # Validate every zone before mutating any (no partial advances).
    zones = []
    for zone_id in data.work_zone_ids:
        zone = await db.work_zones.find_one(
            {"id": zone_id, "project_id": project_id, "company_id": company_id},
            {"_id": 0})
        if not zone:
            raise _err(404, "ZONE_NOT_FOUND",
                       f"Work zone {zone_id} not found in this project.",
                       work_zone_id=zone_id)
        if zone["current_stage_code"] != data.from_stage_code:
            raise _err(409, "409_STAGE_LOCKED",
                       f"{zone['zone_code']} is at {zone['current_stage_code']}, "
                       f"not {data.from_stage_code}. Refresh and retry.",
                       work_zone_id=zone_id,
                       server_state={"current_stage_code": zone["current_stage_code"]})
        pipeline = [s["code"] for s in STAGE_PIPELINES[zone["zone_category"]]]
        idx = pipeline.index(data.from_stage_code)
        if idx + 1 >= len(pipeline) or pipeline[idx + 1] != data.to_stage_code:
            raise _err(422, "INVALID_STAGE_TRANSITION",
                       f"Cannot advance {zone['zone_code']} from "
                       f"{data.from_stage_code} to {data.to_stage_code}; stages "
                       "must advance one step at a time.",
                       work_zone_id=zone_id)
        if zone["zone_category"] == "ZONE_1_RESIDENTIAL" and data.to_stage_code == "S6":
            if not await _submain_ready(db, zone):
                floor_label = str(zone["floor"]).lstrip("L")
                raise _err(
                    409, "409_SUBMAIN_DEPENDENCY_UNMET",
                    f"Cannot advance {zone['zone_code']} to S6 Handover: "
                    f"L{floor_label} Corridor C3 or LV Riser R3 sub-main cable "
                    "is still pending.",
                    work_zone_id=zone_id)
        zones.append(zone)

    combos = set()
    stamp = now()
    for zone in zones:
        stage_map = dict(zone.get("stage_status_map") or {})
        stage_map[data.from_stage_code] = {
            "checked": True, "locked": data.lock_completed_stage,
            "updated_by": user["id"], "updated_at": stamp,
        }
        await db.work_zones.update_one(
            {"id": zone["id"]},
            {"$set": {"stage_status_map": stage_map,
                      "current_stage_code": data.to_stage_code,
                      "updated_at": stamp}})
        if zone["zone_category"] in ("ZONE_2_CORRIDOR", "ZONE_3_RISER"):
            combos.add((zone["block"], zone["floor"]))
    if combos:
        await _recompute_submain(db, project_id, combos)

    response = {
        "advanced": [z["id"] for z in zones],
        "results": [{"work_zone_id": z["id"], "from": data.from_stage_code,
                     "to": data.to_stage_code} for z in zones],
        "idempotency_key": data.idempotency_key,
    }
    try:
        await db.processed_idempotency_keys.insert_one({
            "id": uid(),
            "idempotency_key": data.idempotency_key,
            "company_id": company_id,
            "user_id": user["id"],
            "endpoint_path": f"/api/v2/projects/{project_id}/zones/batch-advance",
            "response_status": 200,
            "response_body_json": response,
            "processed_at": stamp,
        })
    except DuplicateKeyError:
        pass  # A concurrent twin request already recorded it; response stands.
    return response


# ------------------------------------------------- zone defects (Milestone 3)
# PRD §3.5 / §7.6: 3-tap zero-typing defects linked to work zones, with the
# simplified 3-state lifecycle OPEN -> FIXED -> CLOSED. These live in the
# same `defects` collection as v1 unit defects (which carry unit_id and no
# work_zone_id, so the two flows never collide), extended with company_id,
# client_defect_id and the PRD room/issue codes. Zone open_defects_count is
# recomputed from the collection after every mutation — never incremented
# blind, so retries and replays cannot drift it.

DEFECT_V2_TRANSITIONS = {"OPEN": {"FIXED"}, "FIXED": {"CLOSED"}, "CLOSED": set()}
DEFECT_V2_CLOSE_ROLES = ("supervisor", "engineer", "manager", "admin",
                         "company_admin", "pm", "super_admin")
DEFECT_V2_LIVE = ("OPEN", "FIXED")


async def _recount_zone_defects(db, zone_id):
    count = await db.defects.count_documents(
        {"work_zone_id": zone_id, "status": {"$in": list(DEFECT_V2_LIVE)}})
    await db.work_zones.update_one(
        {"id": zone_id},
        {"$set": {"open_defects_count": count, "updated_at": now()}})
    return count


async def _idempotent_replay(db, key, company_id):
    if not key:
        return None
    prior = await db.processed_idempotency_keys.find_one(
        {"idempotency_key": key, "company_id": company_id}, {"_id": 0})
    return prior["response_body_json"] if prior else None


async def _record_idempotency(db, key, company_id, user_id, path, status, body):
    if not key:
        return
    try:
        await db.processed_idempotency_keys.insert_one({
            "id": uid(), "idempotency_key": key, "company_id": company_id,
            "user_id": user_id, "endpoint_path": path,
            "response_status": status, "response_body_json": body,
            "processed_at": now(),
        })
    except DuplicateKeyError:
        pass  # A concurrent twin already recorded it; the response stands.


def _public_zone_defect(doc):
    return {k: v for k, v in doc.items() if k != "_id"}


@router.post("/projects/{project_id}/defects", status_code=201)
async def create_zone_defect(project_id: str, data: DefectV2In,
                             tenant: dict = Depends(get_current_tenant)):
    db = database()
    user = tenant["user"]
    project = await _get_tenant_project(db, user, project_id)
    company_id = project["company_id"]

    replay = await _idempotent_replay(db, data.idempotency_key, company_id)
    if replay is not None:
        return replay

    # Offline-queue retry dedupe (same rule as v1 client_id): a replayed
    # create returns the defect already stored for this tenant.
    existing = await db.defects.find_one(
        {"company_id": company_id, "client_defect_id": data.client_defect_id},
        {"_id": 0})
    if existing:
        return _public_zone_defect(existing)

    zone = await db.work_zones.find_one(
        {"id": data.work_zone_id, "project_id": project_id,
         "company_id": company_id}, {"_id": 0})
    if not zone:
        raise _err(404, "ZONE_NOT_FOUND",
                   f"Work zone {data.work_zone_id} not found in this project.",
                   work_zone_id=data.work_zone_id)

    stamp = now()
    doc = {
        "id": uid(),
        "client_defect_id": data.client_defect_id,
        "company_id": company_id,
        "project_id": project_id,
        "work_zone_id": zone["id"],
        "block": zone["block"],
        "floor": zone["floor"],
        "unit_or_zone_code": zone["zone_code"],
        "room_code": data.room_code,
        "issue_code": data.issue_code,
        "status": "OPEN",
        "local_photo_filename": data.local_photo_filename
            or f"defect_{data.client_defect_id}.jpg",
        "watermark_text": data.watermark_text or "",
        "reported_by_user_id": user["id"],
        "reported_by_name": user["name"],
        "fixed_by_user_id": None,
        "fixed_by_name": None,
        "closed_by_user_id": None,
        "closed_by_name": None,
        "reported_at": data.reported_at or stamp,
        "fixed_at": None,
        "closed_at": None,
        "created_at": stamp,
        "updated_at": stamp,
    }
    await db.defects.insert_one(dict(doc))
    await _recount_zone_defects(db, zone["id"])
    await _record_idempotency(db, data.idempotency_key, company_id, user["id"],
                              f"/api/v2/projects/{project_id}/defects", 201, doc)
    return doc


@router.get("/projects/{project_id}/defects")
async def list_zone_defects(project_id: str,
                            status: str | None = Query(None),
                            tenant: dict = Depends(get_current_tenant)):
    db = database()
    user = tenant["user"]
    await _get_tenant_project(db, user, project_id)
    filt = {"project_id": project_id, "work_zone_id": {"$exists": True}}
    if status:
        filt["status"] = status
    if user.get("role") == "worker":
        # Workers see the defects they reported (v1 visibility rule).
        filt["reported_by_user_id"] = user["id"]
    docs = await db.defects.find(filt, {"_id": 0}).sort(
        "created_at", -1).to_list(5000)
    return [_public_zone_defect(d) for d in docs]


@router.put("/defects/{client_defect_id}/status")
async def transition_zone_defect(client_defect_id: str, data: DefectV2StatusIn,
                                 tenant: dict = Depends(get_current_tenant)):
    db = database()
    user = tenant["user"]
    company_id = _effective_company_id(user)
    filt = {"client_defect_id": client_defect_id,
            "work_zone_id": {"$exists": True}}
    if company_id is not None:
        filt["company_id"] = company_id
    defect = await db.defects.find_one(filt, {"_id": 0})
    if not defect:
        raise _err(404, "DEFECT_NOT_FOUND",
                   f"Defect {client_defect_id} not found.")
    company_id = defect["company_id"]

    replay = await _idempotent_replay(db, data.idempotency_key, company_id)
    if replay is not None:
        return replay

    target = data.target_status
    if target not in DEFECT_V2_TRANSITIONS.get(defect["status"], set()):
        raise _err(422, "INVALID_DEFECT_TRANSITION",
                   f"Cannot move defect from {defect['status']} to {target}.")
    if target == "CLOSED" and user.get("role") not in DEFECT_V2_CLOSE_ROLES:
        raise _err(403, "FORBIDDEN",
                   "Only a supervisor or above can verify & close a defect.")

    stamp = now()
    patch = {"status": target, "updated_at": stamp}
    if target == "FIXED":
        patch.update({"fixed_by_user_id": user["id"],
                      "fixed_by_name": user["name"], "fixed_at": stamp})
    else:
        patch.update({"closed_by_user_id": user["id"],
                      "closed_by_name": user["name"], "closed_at": stamp})
    await db.defects.update_one({"id": defect["id"]}, {"$set": patch})
    await _recount_zone_defects(db, defect["work_zone_id"])
    updated = await db.defects.find_one({"id": defect["id"]}, {"_id": 0})
    body = _public_zone_defect(updated)
    await _record_idempotency(
        db, data.idempotency_key, company_id, user["id"],
        f"/api/v2/defects/{client_defect_id}/status", 200, body)
    return body
