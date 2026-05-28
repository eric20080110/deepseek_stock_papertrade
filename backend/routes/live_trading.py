import json
import time
import uuid
from fastapi import APIRouter, HTTPException, Query
from typing import Optional

from database import get_live_db as get_db
from live_trading.models import CreateLiveInstanceRequest, CreateManualOrderRequest, LiveInstance, LivePosition, LiveStatus, OrderType

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


@router.get("/account")
def account_info():
    from live_trading.alpaca import get_account, configured as alpaca_configured, AlpacaError
    if not alpaca_configured():
        return {"connected": False, "reason": "not_configured"}
    try:
        acct = get_account()
        if not acct:
            return {"connected": False, "reason": "alpaca_unreachable"}
        return {
            "connected": True,
            "equity": float(acct.get("equity", 0)),
            "cash": float(acct.get("cash", 0)),
            "buying_power": float(acct.get("buying_power", 0)),
            "status": acct.get("status", ""),
            "currency": acct.get("currency", "USD"),
        }
    except AlpacaError as e:
        return {"connected": False, "reason": e.message, "status_code": e.status_code}


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
    rows = db.execute("SELECT * FROM live_instances ORDER BY started_at DESC").fetchall()
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
        (instance_id, req.name, req.strategy_config_id, json.dumps(req.params),
         json.dumps(req.symbols), req.initial_capital, LiveStatus.INITIALIZING.value,
         now, req.timeframe, req.schedule_time, req.max_daily_loss_pct, req.max_position_size_pct),
    )
    db.commit()
    row = db.execute("SELECT * FROM live_instances WHERE instance_id = ?", (instance_id,)).fetchone()
    db.close()
    return _row_to_instance(row).model_dump()


@router.post("/from-paper/{paper_instance_id}")
def promote_from_paper(paper_instance_id: str):
    db = get_db()
    paper = db.execute("SELECT * FROM paper_instances WHERE instance_id = ?", (paper_instance_id,)).fetchone()
    if not paper:
        db.close()
        raise HTTPException(404, "Paper trading instance not found")
    instance_id = str(uuid.uuid4())
    now = int(time.time())
    db.execute(
        """INSERT INTO live_instances
           (instance_id, name, strategy_config_id, params_json, symbols,
            initial_capital, status, started_at, timeframe, schedule_time)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (instance_id, paper["name"] + " (實盤)", paper["strategy_config_id"],
         paper["params_json"], paper["symbols"], paper["initial_capital"],
         LiveStatus.INITIALIZING.value, now, paper["timeframe"], "16:30"),
    )
    db.commit()
    row = db.execute("SELECT * FROM live_instances WHERE instance_id = ?", (instance_id,)).fetchone()
    db.close()
    return _row_to_instance(row).model_dump()


@router.get("/{instance_id}")
def get_instance(instance_id: str):
    db = get_db()
    row = db.execute("SELECT * FROM live_instances WHERE instance_id = ?", (instance_id,)).fetchone()
    db.close()
    if not row:
        raise HTTPException(404, "Instance not found")
    return _row_to_instance(row).model_dump()


@router.delete("/{instance_id}")
def stop_instance(instance_id: str, purge: bool = Query(False)):
    db = get_db()
    row = db.execute("SELECT * FROM live_instances WHERE instance_id = ?", (instance_id,)).fetchone()
    if not row:
        db.close()
        raise HTTPException(404, "Instance not found")

    if purge:
        db.execute("DELETE FROM live_orders WHERE instance_id = ?", (instance_id,))
        db.execute("DELETE FROM live_instances WHERE instance_id = ?", (instance_id,))
    else:
        now = int(time.time())
        # Close all Alpaca positions for this instance's symbols
        symbols = json.loads(row["symbols"])
        if symbols:
            from live_trading.alpaca import configured as alpaca_configured, close_position
            if alpaca_configured():
                for sym in symbols:
                    try:
                        close_position(sym)
                    except Exception:
                        pass
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
    from live_trading.alpaca import configured as alpaca_configured, list_positions
    if not alpaca_configured():
        return []
    try:
        raw = list_positions()
    except Exception:
        return []
    return [
        {
            "symbol": p.get("symbol"),
            "side": "long" if float(p.get("qty", 0)) > 0 else "short" if float(p.get("qty", 0)) < 0 else "flat",
            "qty": abs(float(p.get("qty", 0))),
            "entry_price": float(p.get("avg_entry_price", 0)),
            "current_price": float(p.get("current_price", 0)),
            "unrealized_pnl": float(p.get("unrealized_pl", 0)),
            "market_value": float(p.get("market_value", 0)),
            "cost_basis": float(p.get("cost_basis", 0)),
            "change_pct": float(p.get("unrealized_plpc", 0)) * 100,
        }
        for p in raw if abs(float(p.get("qty", 0))) > 0
    ]


@router.get("/{instance_id}/orders")
def get_orders(instance_id: str):
    db = get_db()
    rows = db.execute(
        "SELECT * FROM live_orders WHERE instance_id = ? ORDER BY created_at DESC", (instance_id,)
    ).fetchall()
    db.close()
    return [dict(r) for r in rows]


@router.post("/{instance_id}/orders")
def create_manual_order(instance_id: str, req: CreateManualOrderRequest):
    db = get_db()
    inst = db.execute("SELECT * FROM live_instances WHERE instance_id = ?", (instance_id,)).fetchone()
    if not inst:
        db.close()
        raise HTTPException(404, "Instance not found")
    now = int(time.time())
    order_id = str(uuid.uuid4())
    db.execute(
        "INSERT INTO live_orders (order_id, instance_id, symbol, side, order_type, qty, status, created_at, updated_at, reason) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (order_id, instance_id, req.symbol, req.side.value, (req.order_type or OrderType.MARKET).value,
         req.qty, "PENDING", now, now, json.dumps({"action": "manual", "source": "user"})),
    )
    db.commit()
    db.close()
    return {"order_id": order_id}


@router.post("/{instance_id}/orders/{order_id}/cancel")
def cancel_order(instance_id: str, order_id: str):
    from live_trading.alpaca import configured as alpaca_configured, cancel_order as alpaca_cancel
    db = get_db()
    order = db.execute(
        "SELECT * FROM live_orders WHERE order_id = ? AND instance_id = ?", (order_id, instance_id)
    ).fetchone()
    if not order:
        db.close()
        raise HTTPException(404, "Order not found")
    if order["status"] != "PENDING":
        db.close()
        raise HTTPException(400, f"Cannot cancel order with status {order['status']}")
    now = int(time.time())
    # If already submitted to Alpaca, cancel on Alpaca too
    if order["alpaca_order_id"] and alpaca_configured():
        try:
            alpaca_cancel(order["alpaca_order_id"])
        except Exception:
            pass
    db.execute(
        "UPDATE live_orders SET status = ?, updated_at = ?, reason = ? WHERE order_id = ?",
        ("CANCELLED", now, json.dumps({"action": "cancelled", "source": "user"}), order_id),
    )
    db.commit()
    db.close()
    return {"detail": "ok"}


@router.post("/{instance_id}/flatten")
def flatten_positions(instance_id: str):
    from live_trading.alpaca import configured as alpaca_configured, close_position
    if not alpaca_configured():
        raise HTTPException(400, "Alpaca not configured")
    db = get_db()
    inst = db.execute("SELECT * FROM live_instances WHERE instance_id = ?", (instance_id,)).fetchone()
    if not inst:
        db.close()
        raise HTTPException(404, "Instance not found")
    symbols = json.loads(inst["symbols"]) if isinstance(inst["symbols"], str) else inst["symbols"]
    results = []
    for sym in symbols:
        try:
            r = close_position(sym)
            results.append({"symbol": sym, "result": "ok" if r else "failed"})
        except Exception as e:
            results.append({"symbol": sym, "result": str(e)})
    db.close()
    return {"results": results}
