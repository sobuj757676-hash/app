from pydantic import BaseModel as PydanticBaseModel, Field, ConfigDict
from typing import Literal
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
    activity: list[Record]

class ProjectIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    location: str = Field(min_length=1, max_length=150)
    company: str = Field(default='VoltCraft Electrical', max_length=100)
    budget: float = Field(default=500000, ge=0, allow_inf_nan=False)
    target_date: date

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

class InspectionIn(BaseModel):
    inspector: str = Field(min_length=2, max_length=100)
    date: date
    note: str = Field(default='', max_length=2000)

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