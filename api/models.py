from pydantic import BaseModel as PydanticBaseModel, Field, ConfigDict
from typing import Literal, Annotated
from datetime import date

class BaseModel(PydanticBaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

class Record(BaseModel):
    model_config = ConfigDict(extra='allow')
    id: str

class Workspace(BaseModel):
    project: Record
    blocks: list[Record]
    units: list[Record]
    workers: list[Record]
    materials: list[Record]
    expenses: list[Record]
    inspections: list[Record]
    tests: list[Record]
    attendance: list[Record]
    movements: list[Record]
    defects: list[Record] = []
    tasks: list[Record] = []
    activity: list[Record]
    pagination: dict = {}

class LoginIn(BaseModel):
    identifier: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=1, max_length=72)

class ChangePasswordIn(BaseModel):
    current_password: str = Field(min_length=1, max_length=72)
    new_password: str = Field(min_length=8, max_length=72)

class UserCreateIn(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    email: str | None = Field(default=None, max_length=120)
    phone: str | None = Field(default=None, max_length=30)
    role: str = Field(default='viewer', max_length=20)
    worker_id: str | None = None
    password: str | None = Field(default=None, min_length=8, max_length=72)

class UserUpdateIn(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=100)
    role: str | None = Field(default=None, max_length=20)
    active: bool | None = None

class AttendanceMeIn(BaseModel):
    status: Literal['present', 'absent', 'leave']
    hours: float = Field(default=8, ge=0, le=16)

class ProjectIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    location: str = Field(min_length=1, max_length=150)
    company: str = Field(default='VoltCraft Electrical', max_length=100)
    budget: float = Field(default=500000, ge=0, allow_inf_nan=False)
    target_date: date
    rto_checklist_template: list[Annotated[str, Field(min_length=1, max_length=200)]] | None = Field(default=None, max_length=30)

class BlockIn(BaseModel):
    name: str = Field(min_length=1, max_length=16, pattern=r'^[A-Za-z0-9 -]+$')
    levels: int = Field(ge=1, le=60)
    units_per_level: int = Field(ge=1, le=30)
    first_unit: int = Field(default=401, ge=1, le=9999)

class UnitIn(BaseModel):
    level: int = Field(ge=1, le=60)
    number: str = Field(min_length=1, max_length=10, pattern=r'^[A-Za-z0-9-]+$')
    unit_type: str = Field(default='4-room', max_length=30)
    assigned_to: str = Field(default='', max_length=100)
    note: str = Field(default='', max_length=2000)

class AdvanceIn(BaseModel):
    note: str = Field(default='', max_length=2000)
    expected_stage: int = Field(ge=0, le=8)

class ChecklistItemIn(BaseModel):
    item: str = Field(min_length=1, max_length=200)
    checked: bool

class InspectionIn(BaseModel):
    inspector: str = Field(min_length=2, max_length=100)
    date: date
    note: str = Field(default='', max_length=2000)
    checklist: list[ChecklistItemIn] | None = None

class DecisionIn(BaseModel):
    result: Literal['approved', 'rework']
    inspector: str = Field(min_length=2, max_length=100)
    note: str = Field(min_length=1, max_length=2000)

class PointIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    kind: Literal['power', 'light', 'socket', 'switch', 'data', 'tv'] = 'power'

class TestIn(BaseModel):
    point_id: str
    voltage: float = Field(gt=0, le=5000, allow_inf_nan=False)
    l_n: float = Field(ge=0, allow_inf_nan=False)
    l_e: float = Field(ge=0, allow_inf_nan=False)
    n_e: float = Field(ge=0, allow_inf_nan=False)
    result: Literal['pass', 'fail']
    tested_by: str = Field(min_length=2, max_length=100)
    note: str = Field(default='', max_length=1000)

class WorkerIn(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    trade: str = Field(min_length=1, max_length=60)
    block: str = Field(default='', max_length=16)
    daily_rate: float = Field(ge=0, allow_inf_nan=False)
    phone: str = Field(default='', max_length=30)

class AttendanceIn(BaseModel):
    date: date
    status: Literal['present', 'absent', 'leave']
    hours: float = Field(default=8, ge=0, le=16)

class MaterialIn(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    unit: str = Field(min_length=1, max_length=20)
    stock: float = Field(default=0, ge=0, allow_inf_nan=False)
    minimum: float = Field(default=10, ge=0, allow_inf_nan=False)
    unit_cost: float = Field(default=0, ge=0, allow_inf_nan=False)

class MovementIn(BaseModel):
    kind: Literal['receive', 'issue']
    quantity: float = Field(gt=0, allow_inf_nan=False)
    block: str = Field(default='', max_length=16)
    note: str = Field(min_length=1, max_length=500)

class ExpenseIn(BaseModel):
    description: str = Field(min_length=2, max_length=200)
    category: Literal['materials', 'labour', 'equipment', 'transport', 'other']
    amount: float = Field(gt=0, allow_inf_nan=False)
    date: date
    block: str = Field(default='', max_length=16)
    reference: str = Field(default='', max_length=100)

# ---------- Phase 2: defects, tasks, photos, RTO checklist ----------

DEFECT_CATEGORIES = ('workmanship', 'material', 'design-drawing', 'safety', 'other')
DEFECT_SEVERITIES = ('critical', 'major', 'minor')
DEFECT_STATUSES = ('open', 'assigned', 'in_progress', 'rectified', 'verified', 'cancelled')
TASK_STATUSES = ('todo', 'in_progress', 'done', 'cancelled')
TASK_PRIORITIES = ('low', 'medium', 'high', 'urgent')
PHOTO_ENTITY_TYPES = ('defect', 'inspection', 'test', 'unit', 'task')

class DefectIn(BaseModel):
    title: str = Field(min_length=2, max_length=150)
    description: str = Field(default='', max_length=2000)
    category: Literal['workmanship', 'material', 'design-drawing', 'safety', 'other'] = 'workmanship'
    severity: Literal['critical', 'major', 'minor'] = 'major'
    unit_id: str | None = None
    due_date: date | None = None

class DefectPatchIn(BaseModel):
    title: str | None = Field(default=None, min_length=2, max_length=150)
    description: str | None = Field(default=None, max_length=2000)
    category: Literal['workmanship', 'material', 'design-drawing', 'safety', 'other'] | None = None
    severity: Literal['critical', 'major', 'minor'] | None = None
    due_date: date | None = None

class DefectAssignIn(BaseModel):
    assignee_id: str = Field(min_length=1)

class DefectTransitionIn(BaseModel):
    status: Literal['open', 'assigned', 'in_progress', 'rectified', 'verified', 'cancelled']
    note: str = Field(default='', max_length=1000)

class TaskIn(BaseModel):
    title: str = Field(min_length=2, max_length=150)
    description: str = Field(default='', max_length=2000)
    unit_id: str | None = None
    defect_id: str | None = None
    assigned_to: str = Field(min_length=1)
    priority: Literal['low', 'medium', 'high', 'urgent'] = 'medium'
    due_date: date | None = None

class TaskPatchIn(BaseModel):
    title: str | None = Field(default=None, min_length=2, max_length=150)
    description: str | None = Field(default=None, max_length=2000)
    priority: Literal['low', 'medium', 'high', 'urgent'] | None = None
    due_date: date | None = None
    assigned_to: str | None = Field(default=None, min_length=1)
    defect_id: str | None = None

class TaskTransitionIn(BaseModel):
    status: Literal['todo', 'in_progress', 'done', 'cancelled']
    note: str = Field(default='', max_length=1000)

class DefectTaskIn(BaseModel):
    title: str = Field(min_length=2, max_length=150)
    description: str = Field(default='', max_length=2000)
    assigned_to: str | None = Field(default=None, min_length=1)
    priority: Literal['low', 'medium', 'high', 'urgent'] = 'medium'
    due_date: date | None = None

class RtoChecklistIn(BaseModel):
    template: list[Annotated[str, Field(min_length=1, max_length=200)]] = Field(min_length=1, max_length=30)