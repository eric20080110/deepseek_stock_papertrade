from pydantic import BaseModel, Field
from typing import Optional, Literal
from enum import Enum


class ScaleType(str, Enum):
    linear = "linear"
    logarithmic = "logarithmic"


class ParamType(str, Enum):
    continuous = "continuous"
    integer = "integer"
    categorical = "categorical"
    boolean = "boolean"


class RelationType(str, Enum):
    less_than = "less_than"
    less_equal = "less_equal"


class RepairStrategy(str, Enum):
    clamp_upper = "clamp_upper"
    clamp_lower = "clamp_lower"
    swap = "swap"


class ConstraintType(str, Enum):
    ordering = "ordering"
    conditional = "conditional"
    categorical_group = "categorical_group"


class ContinuousParam(BaseModel):
    name: str
    type: Literal["continuous"] = "continuous"
    min: float
    max: float
    default: float
    scale: ScaleType = ScaleType.linear


class IntegerParam(BaseModel):
    name: str
    type: Literal["integer"] = "integer"
    min: int
    max: int
    step: int = 1
    default: int


class CategoricalParam(BaseModel):
    name: str
    type: Literal["categorical"] = "categorical"
    options: list[str]
    default: str


class BooleanParam(BaseModel):
    name: str
    type: Literal["boolean"] = "boolean"
    default: bool
    controls: list[str] = []


ParamDef = ContinuousParam | IntegerParam | CategoricalParam | BooleanParam


class OrderingConstraint(BaseModel):
    type: Literal["ordering"] = "ordering"
    params: list[str]
    relation: RelationType
    repair: RepairStrategy


class ConditionalConstraint(BaseModel):
    type: Literal["conditional"] = "conditional"
    controller: str
    active_when: bool
    controlled_params: list[str]


class CategoricalGroupConstraint(BaseModel):
    type: Literal["categorical_group"] = "categorical_group"
    controller: str
    groups: dict[str, list[str]]
    common_params: list[str] = []


ConstraintDef = OrderingConstraint | ConditionalConstraint | CategoricalGroupConstraint


class StrategyConfigCreate(BaseModel):
    template_id: str
    name: str
    description: str = ""
    parameters: list[ParamDef] = []
    constraints: list[ConstraintDef] = []


class StrategyConfigUpdate(BaseModel):
    name: str
    description: str = ""
    parameters: list[ParamDef] = []
    constraints: list[ConstraintDef] = []


class StrategyConfigOut(BaseModel):
    config_id: str
    name: str
    description: str
    template_id: Optional[str]
    is_template: bool
    is_locked: bool
    locked_by_task_id: Optional[str]
    parameters: list[ParamDef]
    constraints: list[ConstraintDef]
    created_at: int
    updated_at: int
