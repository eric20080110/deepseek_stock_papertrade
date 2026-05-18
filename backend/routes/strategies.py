import json
import time
import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Any, Optional

from database import get_db, get_turso, sync_strategies_to_local

router = APIRouter(prefix="/strategies", tags=["strategies"])


class StrategyCreateBody(BaseModel):
    template_id: str
    name: str = Field(..., min_length=1, max_length=50)
    description: str = Field(default="", max_length=200)
    parameters: list[dict[str, Any]] = []
    constraints: list[dict[str, Any]] = []


class StrategyUpdateBody(BaseModel):
    name: str = Field(..., min_length=1, max_length=50)
    description: str = Field(default="", max_length=200)
    parameters: list[dict[str, Any]] = []
    constraints: list[dict[str, Any]] = []


def _row_to_dict(row) -> dict:
    params = json.loads(row["parameters_json"])
    for p in params:
        if p.get("type") == "boolean" and "controls" not in p:
            p["controls"] = []
    return {
        "config_id": row["config_id"],
        "name": row["name"],
        "description": row["description"],
        "template_id": row["template_id"],
        "is_template": bool(row["is_template"]),
        "is_locked": bool(row["is_locked"]),
        "locked_by_task_id": row["locked_by_task_id"],
        "parameters": params,
        "constraints": json.loads(row["constraints_json"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


@router.get("")
def list_strategies():
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM strategy_configs ORDER BY is_template DESC, created_at DESC"
    ).fetchall()
    conn.close()
    return [_row_to_dict(r) for r in rows]


@router.get("/templates")
def list_templates():
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM strategy_configs WHERE is_template = 1 ORDER BY created_at ASC"
    ).fetchall()
    conn.close()
    return [_row_to_dict(r) for r in rows]


@router.get("/{config_id}")
def get_strategy(config_id: str):
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM strategy_configs WHERE config_id = ?", (config_id,)
    ).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Strategy not found")
    return _row_to_dict(row)


@router.post("")
def create_strategy(body: StrategyCreateBody):
    now = int(time.time())
    config_id = str(uuid.uuid4())

    t = get_turso()
    template = t.execute(
        "SELECT parameters_json, constraints_json FROM strategy_configs WHERE template_id = ? AND is_template = 1",
        (body.template_id,),
    ).fetchone()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    merged_params = body.parameters if body.parameters else json.loads(template["parameters_json"])
    merged_constraints = body.constraints if body.constraints else json.loads(template["constraints_json"])

    t.execute(
        """INSERT INTO strategy_configs
           (config_id, name, description, template_id, is_template, is_locked,
            parameters_json, constraints_json, created_at, updated_at)
           VALUES (?, ?, ?, ?, 0, 0, ?, ?, ?, ?)""",
        (
            config_id,
            body.name,
            body.description,
            body.template_id,
            json.dumps(merged_params),
            json.dumps(merged_constraints),
            now,
            now,
        ),
    )
    sync_strategies_to_local()
    conn = get_db()
    row = conn.execute("SELECT * FROM strategy_configs WHERE config_id = ?", (config_id,)).fetchone()
    conn.close()
    return _row_to_dict(row)


@router.put("/{config_id}")
def update_strategy(config_id: str, body: StrategyUpdateBody):
    t = get_turso()
    row = t.execute(
        "SELECT * FROM strategy_configs WHERE config_id = ?", (config_id,)
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Strategy not found")
    if row["is_template"]:
        raise HTTPException(status_code=403, detail="Cannot edit a system template")
    if row["is_locked"]:
        raise HTTPException(status_code=423, detail="Strategy is locked by a running task")

    now = int(time.time())
    t.execute(
        """UPDATE strategy_configs
           SET name = ?, description = ?, parameters_json = ?, constraints_json = ?, updated_at = ?
           WHERE config_id = ?""",
        (
            body.name,
            body.description,
            json.dumps(body.parameters),
            json.dumps(body.constraints),
            now,
            config_id,
        ),
    )
    sync_strategies_to_local()
    conn = get_db()
    row = conn.execute("SELECT * FROM strategy_configs WHERE config_id = ?", (config_id,)).fetchone()
    conn.close()
    return _row_to_dict(row)


@router.delete("/{config_id}")
def delete_strategy(config_id: str):
    t = get_turso()
    row = t.execute(
        "SELECT * FROM strategy_configs WHERE config_id = ?", (config_id,)
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Strategy not found")
    if row["is_template"]:
        raise HTTPException(status_code=403, detail="Cannot delete a system template")
    if row["is_locked"]:
        raise HTTPException(status_code=423, detail="Strategy is locked by a running task")

    t.execute("DELETE FROM strategy_configs WHERE config_id = ?", (config_id,))
    sync_strategies_to_local()
    return {"detail": "Strategy deleted"}


@router.post("/{config_id}/duplicate")
def duplicate_strategy(config_id: str):
    t = get_turso()
    row = t.execute(
        "SELECT * FROM strategy_configs WHERE config_id = ?", (config_id,)
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Strategy not found")

    now = int(time.time())
    new_id = str(uuid.uuid4())
    new_name = row["name"] + "（複製）"

    t.execute(
        """INSERT INTO strategy_configs
           (config_id, name, description, template_id, is_template, is_locked,
            parameters_json, constraints_json, created_at, updated_at)
           VALUES (?, ?, ?, ?, 0, 0, ?, ?, ?, ?)""",
        (
            new_id,
            new_name,
            row["description"],
            row["template_id"],
            row["parameters_json"],
            row["constraints_json"],
            now,
            now,
        ),
    )
    sync_strategies_to_local()
    conn = get_db()
    new_row = conn.execute("SELECT * FROM strategy_configs WHERE config_id = ?", (new_id,)).fetchone()
    conn.close()
    return _row_to_dict(new_row)
