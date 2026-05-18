import json
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Any

from database import get_db
from param_space.space import ParameterSpace
from models import (
    ParamDef, ConstraintDef,
    ContinuousParam, IntegerParam, CategoricalParam, BooleanParam,
    OrderingConstraint, ConditionalConstraint, CategoricalGroupConstraint,
)

router = APIRouter(prefix="/param-space", tags=["param_space"])


class ValidateRequest(BaseModel):
    parameters: list[dict[str, Any]]
    constraints: list[dict[str, Any]]
    params: dict[str, Any]


class SampleRequest(BaseModel):
    parameters: list[dict[str, Any]]
    constraints: list[dict[str, Any]]


class RepairRequest(BaseModel):
    parameters: list[dict[str, Any]]
    constraints: list[dict[str, Any]]
    params: dict[str, Any]


class EncodeRequest(BaseModel):
    parameters: list[dict[str, Any]]
    constraints: list[dict[str, Any]]
    params: dict[str, Any]


class DecodeRequest(BaseModel):
    parameters: list[dict[str, Any]]
    constraints: list[dict[str, Any]]
    vector: list[float]


def _build_space(parameters: list[dict], constraints: list[dict]) -> ParameterSpace:
    parsed_params: list[ParamDef] = []
    for p in parameters:
        t = p.get("type", "continuous")
        if t == "continuous":
            parsed_params.append(ContinuousParam(**p))
        elif t == "integer":
            parsed_params.append(IntegerParam(**p))
        elif t == "categorical":
            parsed_params.append(CategoricalParam(**p))
        elif t == "boolean":
            parsed_params.append(BooleanParam(**p))

    parsed_constraints: list[ConstraintDef] = []
    for c in constraints:
        ct = c.get("type", "ordering")
        if ct == "ordering":
            parsed_constraints.append(OrderingConstraint(**c))
        elif ct == "conditional":
            parsed_constraints.append(ConditionalConstraint(**c))
        elif ct == "categorical_group":
            parsed_constraints.append(CategoricalGroupConstraint(**c))

    return ParameterSpace(parsed_params, parsed_constraints)


@router.post("/sample")
def sample_endpoint(req: SampleRequest):
    space = _build_space(req.parameters, req.constraints)
    ind = space.sample()
    return {"params": ind.params, "summary": space.summary()}


@router.post("/validate")
def validate_endpoint(req: ValidateRequest):
    space = _build_space(req.parameters, req.constraints)
    result = space.validate(req.params)
    return result


@router.post("/repair")
def repair_endpoint(req: RepairRequest):
    space = _build_space(req.parameters, req.constraints)
    result = space.repair(req.params)
    return result


@router.post("/encode")
def encode_endpoint(req: EncodeRequest):
    space = _build_space(req.parameters, req.constraints)
    vec = space.encode(req.params)
    return {"vector": vec.tolist(), "length": len(vec)}


@router.post("/decode")
def decode_endpoint(req: DecodeRequest):
    space = _build_space(req.parameters, req.constraints)
    import numpy as np
    params = space.decode(np.array(req.vector, dtype=np.float64))
    return {"params": params}


@router.get("/strategies/{config_id}/summary")
def strategy_summary(config_id: str):
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM strategy_configs WHERE config_id = ?", (config_id,)
    ).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Strategy not found")

    parameters = json.loads(row["parameters_json"])
    constraints = json.loads(row["constraints_json"])
    space = _build_space(parameters, constraints)
    return space.summary()


@router.post("/strategies/{config_id}/sample")
def strategy_sample(config_id: str):
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM strategy_configs WHERE config_id = ?", (config_id,)
    ).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Strategy not found")

    parameters = json.loads(row["parameters_json"])
    constraints = json.loads(row["constraints_json"])
    space = _build_space(parameters, constraints)
    ind = space.sample()
    return {"params": ind.params}
