import json
import time
import uuid
from fastapi import APIRouter, HTTPException, Query
from typing import Optional

from database import get_db
from live_trading.models import CreateLiveInstanceRequest, LiveInstance, LiveOrder, LivePosition, LiveStatus, OrderStatus

router = APIRouter(prefix="/live-trading", tags=["live_trading"])


def _row_to_instance(row) -> LiveInstance:
    return LiveInstance(
        instance_id=row["instance_id"],
        name=row["name"],
        strategy_config_id=row["strategy_config_id"],
        params_json=row["params_json"],
        symbols=row["symbols"],
        initial_capital=row["initial_capital"],
        status=LiveStatus(row["status"]),
        started_at=row["started_at"],
        stopped_at=row["stopped_at"],
        timeframe=row["timeframe"],
        total_equity=row["total_equity"],
        total_return=row["total_return"],
        unrealized_pnl=row["unrealized_pnl"],
        realized_pnl=row["realized_pnl"],
        trade_count=row["trade_count"],
        win_rate=row["win_rate"],
        max_drawdown=row["max_drawdown"],
        schedule_time=row["schedule_time"],
        max_daily_loss_pct=row["max_daily_loss_pct"],
        max_position_size_pct=row["max_position_size_pct"],
    )


@router.get("/render-status")
def render_status():
    import os, urllib.request, urllib.error
    url = os.environ.get("RENDER_PAPER_URL", "").rstrip("/")
    if not url:
        return {"connected": False, "reason": "not_configured"}
    try:
        with urllib.request.urlopen(f"{url}/health", timeout=8) as r:
            import json as _json
            data = _json.loads(r.read())
            return {"connected": True, "url": url, "instances": data.get("instances", 0)}
    except urllib.error.HTTPError as e:
        reason = "not_deployed" if e.code == 404 else f"http_{e.code}"
        return {"connected": False, "url": url, "reason": reason}
    except Exception as e:
        return {"connected": False, "url": url, "reason": "unreachable"}


@router.get("")
def list_instances():
    db = get_db()
    rows = db.execute(
        "SELECT * FROM live_instances ORDER BY started_at DESC"
    ).fetchall()
    db.close()
    return [_row_to_instance(r).model_dump() for r in rows]


@router.post("")
def create_instance(req: CreateLiveInstanceRequest):
    instance_id = str(uuid.uuid4())
    now = int(time.time())
    db = get_db()
    db.execute(
        """INSERT INTO live_instances
           (instance_id, name, strategy_config_id, params_json, symbols,
            initial_capital, status, started_at, timeframe, schedule_time,
            max_daily_loss_pct, max_position_size_pct)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            instance_id, req.name, req.strategy_config_id,
            json.dumps(req.params), json.dumps(req.symbols),
            req.initial_capital, LiveStatus.INITIALIZING.value, now,
            req.timeframe, req.schedule_time,
            req.max_daily_loss_pct, req.max_position_size_pct,
        ),
    )
    db.commit()
    row = db.execute(
        "SELECT * FROM live_instances WHERE instance_id = ?", (instance_id,)
    ).fetchone()
    db.close()
    return _row_to_instance(row).model_dump()


@router.get("/{instance_id}")
def get_instance(instance_id: str):
    db = get_db()
    row = db.execute(
        "SELECT * FROM live_instances WHERE instance_id = ?", (instance_id,)
    ).fetchone()
    db.close()
    if not row:
        raise HTTPException(404, "Instance not found")
    return _row_to_instance(row).model_dump()


@router.delete("/{instance_id}")
def stop_instance(instance_id: str, purge: bool = Query(False)):
    db = get_db()
    row = db.execute(
        "SELECT * FROM live_instances WHERE instance_id = ?", (instance_id,)
    ).fetchone()
    if not row:
        db.close()
        raise HTTPException(404, "Instance not found")

    if purge:
        db.execute("DELETE FROM live_orders WHERE instance_id = ?", (instance_id,))
        db.execute("DELETE FROM live_instances WHERE instance_id = ?", (instance_id,))
    else:
        now = int(time.time())
        db.execute(
            "UPDATE live_instances SET status = ?, stopped_at = ? WHERE instance_id = ?",
            (LiveStatus.STOPPED.value, now, instance_id),
        )
    db.commit()
    db.close()
    return {"detail": "ok"}


@router.put("/{instance_id}/pause")
def pause_instance(instance_id: str):
    db = get_db()
    db.execute(
        "UPDATE live_instances SET status = ? WHERE instance_id = ? AND status = ?",
        (LiveStatus.PAUSED.value, instance_id, LiveStatus.RUNNING.value),
    )
    db.commit()
    db.close()
    return {"detail": "ok"}


@router.put("/{instance_id}/resume")
def resume_instance(instance_id: str):
    db = get_db()
    db.execute(
        "UPDATE live_instances SET status = ? WHERE instance_id = ? AND status = ?",
        (LiveStatus.RUNNING.value, instance_id, LiveStatus.PAUSED.value),
    )
    db.commit()
    db.close()
    return {"detail": "ok"}


@router.get("/{instance_id}/positions")
def get_positions(instance_id: str):
    return []


@router.get("/{instance_id}/orders")
def get_orders(instance_id: str):
    db = get_db()
    rows = db.execute(
        "SELECT * FROM live_orders WHERE instance_id = ? ORDER BY created_at DESC",
        (instance_id,),
    ).fetchall()
    db.close()
    return [dict(r) for r in rows]
