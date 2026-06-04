import json
import threading
import time
import uuid
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
from database import get_db, get_turso, sync_strategies_to_local
from routes.strategies import _row_to_dict

router = APIRouter(prefix="/gene-pool", tags=["gene_pool"])


def _remote_conn():
    """Return (conn, is_remote). Falls back to local SQLite when Turso unavailable."""
    try:
        return get_turso(), True
    except Exception:
        return get_db(), False


class AnnotationPayload(BaseModel):
    is_favorite: Optional[bool] = None
    custom_name: Optional[str] = None


def _get_annotations(conn) -> dict[str, dict]:
    rows = conn.execute("SELECT * FROM gene_favorites").fetchall()
    return {r["strategy_id"]: dict(r) for r in rows}


@router.get("")
def gene_pool(favorites_only: bool = Query(False)):
    remote, is_remote = _remote_conn()
    annotations = _get_annotations(remote)

    strategies = remote.execute(
        "SELECT * FROM strategy_configs ORDER BY is_template DESC, name ASC"
    ).fetchall()

    local = get_db()
    tasks = local.execute(
        "SELECT * FROM evolution_tasks WHERE status = 'COMPLETED' ORDER BY completed_at DESC"
    ).fetchall()

    result = []
    for s in strategies:
        sdict = dict(s)
        task_list = []
        for tk in tasks:
            config = json.loads(tk["config_json"])
            if config.get("strategy_config_id") != s["config_id"]:
                continue
            individuals = local.execute(
                """SELECT strategy_id, strategy_id AS sid, generation, cagr, max_drawdown, sharpe_ratio,
                          profit_factor, win_rate, trade_count,
                          oos_consistency_score, params_json, pareto_rank
                   FROM individuals
                   WHERE task_id = ? AND pareto_rank = 1
                   ORDER BY cagr DESC LIMIT 10""",
                (tk["task_id"],),
            ).fetchall()
            champions = []
            for i, ind in enumerate(individuals):
                d = dict(ind)
                ann = annotations.get(ind["strategy_id"], {})
                d["idx"] = i + 1
                d["is_favorite"] = bool(ann.get("is_favorite", False))
                d["custom_name"] = ann.get("custom_name", "")
                if favorites_only and not d["is_favorite"]:
                    continue
                champions.append(d)
            champions.sort(key=lambda c: (not c["is_favorite"], -(c.get("cagr") or 0)))
            if not champions and favorites_only:
                continue
            task_list.append({
                "task_id": tk["task_id"],
                "task_name": tk["name"] or tk["task_id"][:8],
                "current_generation": tk["current_generation"],
                "total_generations": tk["total_generations"],
                "completed_at": tk["completed_at"],
                "symbols": config.get("symbols", []),
                "timeframe": config.get("timeframe", "1d"),
                "champions": champions,
            })
        if task_list:
            result.append({
                "config_id": sdict["config_id"],
                "name": sdict["name"],
                "template_id": sdict["template_id"],
                "is_template": bool(sdict["is_template"]),
                "tasks": task_list,
            })

    local.close()
    return result


@router.get("/ranking")
def champion_ranking():
    local = get_db()
    rows = local.execute(
        """SELECT i.strategy_id, i.task_id, t.name AS task_name, i.generation,
                  i.cagr, i.max_drawdown, i.sharpe_ratio, i.profit_factor, i.win_rate,
                  i.oos_consistency_score, i.trade_count, t.config_json
           FROM individuals i
           JOIN evolution_tasks t ON i.task_id = t.task_id
           WHERE i.pareto_rank = 1
           ORDER BY i.cagr DESC
           LIMIT 100"""
    ).fetchall()
    local.close()
    result = []
    for r in rows:
        config = json.loads(r["config_json"])
        result.append({
            "strategy_id": r["strategy_id"],
            "task_id": r["task_id"],
            "task_name": r["task_name"],
            "generation": r["generation"],
            "cagr": r["cagr"],
            "max_drawdown": r["max_drawdown"],
            "sharpe_ratio": r["sharpe_ratio"],
            "profit_factor": r["profit_factor"],
            "win_rate": r["win_rate"],
            "oos_consistency_score": r["oos_consistency_score"],
            "trade_count": r["trade_count"],
            "symbols": config.get("symbols", []),
            "timeframe": config.get("timeframe", "1d"),
        })
    return result


@router.put("/annotations/{strategy_id}")
def update_annotation(strategy_id: str, payload: AnnotationPayload):
    conn, is_remote = _remote_conn()
    existing = conn.execute(
        "SELECT * FROM gene_favorites WHERE strategy_id = ?", (strategy_id,)
    ).fetchone()
    now = int(time.time())
    if existing:
        d = dict(existing)
        if payload.is_favorite is not None:
            d["is_favorite"] = 1 if payload.is_favorite else 0
        if payload.custom_name is not None:
            d["custom_name"] = payload.custom_name
        conn.execute(
            "UPDATE gene_favorites SET is_favorite=?, custom_name=?, updated_at=? WHERE strategy_id=?",
            (d["is_favorite"], d["custom_name"], now, strategy_id),
        )
    else:
        conn.execute(
            "INSERT INTO gene_favorites (strategy_id, task_id, custom_name, is_favorite, updated_at) VALUES (?, '', ?, ?, ?)",
            (strategy_id, payload.custom_name or "", 1 if payload.is_favorite else 0, now),
        )
    if not is_remote:
        conn.commit()
        conn.close()
    return {"ok": True}


@router.delete("/individuals/{strategy_id}")
def delete_individual(strategy_id: str):
    local = get_db()
    local.execute("DELETE FROM individuals WHERE strategy_id = ?", (strategy_id,))
    local.commit()
    local.close()
    conn, is_remote = _remote_conn()
    conn.execute("DELETE FROM gene_favorites WHERE strategy_id = ?", (strategy_id,))
    if not is_remote:
        conn.commit()
        conn.close()
    return {"detail": "Individual deleted"}


@router.delete("/tasks/{task_id}")
def delete_task_champions(task_id: str):
    local = get_db()
    sids = local.execute(
        "SELECT strategy_id FROM individuals WHERE task_id = ?", (task_id,)
    ).fetchall()
    local.execute("DELETE FROM individuals WHERE task_id = ?", (task_id,))
    local.commit()
    local.close()
    if sids:
        conn, is_remote = _remote_conn()
        for row in sids:
            conn.execute("DELETE FROM gene_favorites WHERE strategy_id = ?", (row["strategy_id"],))
        if not is_remote:
            conn.commit()
            conn.close()
    return {"detail": f"Deleted {len(sids)} champions from task {task_id}"}


class RenameTaskPayload(BaseModel):
    name: str


@router.put("/tasks/{task_id}/rename")
def rename_task(task_id: str, payload: RenameTaskPayload):
    local = get_db()
    local.execute(
        "UPDATE evolution_tasks SET name = ? WHERE task_id = ?",
        (payload.name, task_id),
    )
    local.commit()
    local.close()
    return {"ok": True}


@router.put("/{strategy_id}/favorite")
def set_favorite(strategy_id: str, payload: AnnotationPayload):
    conn, is_remote = _remote_conn()
    existing = conn.execute(
        "SELECT * FROM gene_favorites WHERE strategy_id = ?", (strategy_id,)
    ).fetchone()
    now = int(time.time())
    val = 1 if (payload.is_favorite or False) else 0
    if existing:
        conn.execute(
            "UPDATE gene_favorites SET is_favorite=?, updated_at=? WHERE strategy_id=?",
            (val, now, strategy_id),
        )
    else:
        conn.execute(
            "INSERT INTO gene_favorites (strategy_id, task_id, custom_name, is_favorite, updated_at) VALUES (?, '', '', ?, ?)",
            (strategy_id, val, now),
        )
    if not is_remote:
        conn.commit()
        conn.close()
    return {"ok": True}


@router.put("/{strategy_id}/rename")
def rename_individual(strategy_id: str, payload: AnnotationPayload):
    conn, is_remote = _remote_conn()
    name = payload.custom_name or ""
    existing = conn.execute(
        "SELECT * FROM gene_favorites WHERE strategy_id = ?", (strategy_id,)
    ).fetchone()
    now = int(time.time())
    if existing:
        conn.execute(
            "UPDATE gene_favorites SET custom_name=?, updated_at=? WHERE strategy_id=?",
            (name, now, strategy_id),
        )
    else:
        conn.execute(
            "INSERT INTO gene_favorites (strategy_id, task_id, custom_name, is_favorite, updated_at) VALUES (?, '', ?, 0, ?)",
            (strategy_id, name, now),
        )
    if not is_remote:
        conn.commit()
        conn.close()
    return {"ok": True}


class CreateStrategyFromChampionBody(BaseModel):
    name: str
    description: str = ""


@router.post("/{sid}/create-strategy")
def create_strategy_from_champion(sid: str, body: CreateStrategyFromChampionBody):
    local = get_db()
    ind = local.execute(
        "SELECT * FROM individuals WHERE strategy_id = ?", (sid,)
    ).fetchone()
    if not ind:
        local.close()
        raise HTTPException(status_code=404, detail="Individual not found")

    params_json = ind["params_json"]
    task_id = ind["task_id"]

    task = local.execute(
        "SELECT * FROM evolution_tasks WHERE task_id = ?", (task_id,)
    ).fetchone()
    local.close()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    task_config = json.loads(task["config_json"])
    strategy_config_id = task_config.get("strategy_config_id")
    if not strategy_config_id:
        raise HTTPException(status_code=400, detail="Task has no strategy_config_id")

    t, is_remote = _remote_conn()
    original = t.execute(
        "SELECT * FROM strategy_configs WHERE config_id = ?", (strategy_config_id,)
    ).fetchone()
    if not original:
        raise HTTPException(status_code=404, detail="Original strategy config not found")

    template_params = json.loads(original["parameters_json"])
    champion_params = json.loads(params_json)
    merged_params = []
    for p in template_params:
        p = dict(p)
        if p["name"] in champion_params:
            p["default"] = champion_params[p["name"]]
        merged_params.append(p)

    now = int(time.time())
    config_id = str(uuid.uuid4())

    t.execute(
        """INSERT INTO strategy_configs
           (config_id, name, description, template_id, is_template, is_locked,
            parameters_json, constraints_json, created_at, updated_at)
           VALUES (?, ?, ?, ?, 0, 0, ?, ?, ?, ?)""",
        (config_id, body.name, body.description, strategy_config_id,
         json.dumps(merged_params), original["constraints_json"], now, now),
    )
    row = t.execute("SELECT * FROM strategy_configs WHERE config_id = ?", (config_id,)).fetchone()
    if not is_remote:
        t.commit()
        t.close()

    threading.Thread(target=sync_strategies_to_local, daemon=True).start()

    return _row_to_dict(row)


@router.delete("/{strategy_id}")
def delete_champion(strategy_id: str):
    local = get_db()
    local.execute("DELETE FROM individuals WHERE strategy_id = ?", (strategy_id,))
    local.commit()
    local.close()
    conn, is_remote = _remote_conn()
    conn.execute("DELETE FROM gene_favorites WHERE strategy_id = ?", (strategy_id,))
    if not is_remote:
        conn.commit()
        conn.close()
    return {"detail": "Champion deleted"}
