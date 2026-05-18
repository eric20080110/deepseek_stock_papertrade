import json
from fastapi import APIRouter, HTTPException
from typing import Optional

from paper_trading.engine import PaperTradingEngine
from paper_trading.models import CreateInstanceRequest, InstanceStatus
from backtest.data_cache import DATA_CACHE

router = APIRouter(prefix="/paper-trading", tags=["paper_trading"])
engine = PaperTradingEngine()


@router.get("")
def list_instances():
    return engine.list_instances()


@router.post("")
def create_instance(req: CreateInstanceRequest):
    try:
        inst = engine.create_instance(req)
        engine.run_initialization(inst.instance_id)
        return engine.get_instance(inst.instance_id)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/{instance_id}")
def get_instance(instance_id: str):
    inst = engine.get_instance(instance_id)
    if not inst:
        raise HTTPException(404, "Instance not found")
    return inst


@router.put("/{instance_id}/pause")
def pause_instance(instance_id: str):
    if not engine.pause_instance(instance_id):
        raise HTTPException(400, "Cannot pause instance")
    return engine.get_instance(instance_id)


@router.put("/{instance_id}/resume")
def resume_instance(instance_id: str):
    if not engine.resume_instance(instance_id):
        raise HTTPException(400, "Cannot resume instance")
    return engine.get_instance(instance_id)


@router.delete("/{instance_id}")
def stop_instance(instance_id: str, purge: bool = False):
    if purge:
        engine.delete_instance(instance_id)
        return {"detail": "Instance deleted"}
    engine.stop_instance(instance_id)
    return {"detail": "Instance stopped"}


@router.put("/{instance_id}/continue")
def continue_instance(instance_id: str):
    inst = engine.get_instance(instance_id)
    if not inst:
        raise HTTPException(404, "Instance not found")
    if inst.status != InstanceStatus.STOPPED:
        raise HTTPException(400, "Only stopped instances can be continued")
    engine.delete_instance(instance_id)
    from paper_trading.models import CreateInstanceRequest, SourceType
    req = CreateInstanceRequest(
        name=inst.name,
        source=SourceType(inst.source),
        source_task_id=inst.source_task_id,
        source_individual_id=inst.source_individual_id,
        strategy_config_id=inst.strategy_config_id,
        params=json.loads(inst.params_json) if isinstance(inst.params_json, str) else inst.params_json,
        symbols=json.loads(inst.symbols) if isinstance(inst.symbols, str) else inst.symbols,
        initial_capital=inst.initial_capital,
        timeframe=inst.timeframe,
    )
    try:
        new_inst = engine.create_instance(req)
        engine.run_initialization(new_inst.instance_id)
        return engine.get_instance(new_inst.instance_id)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.delete("/{instance_id}/force")
def delete_instance(instance_id: str):
    engine.delete_instance(instance_id)
    return {"detail": "Instance deleted"}


@router.get("/{instance_id}/trades")
def get_trades(instance_id: str, limit: int = 100):
    return engine.get_trades(instance_id, limit)


@router.get("/{instance_id}/chart")
def get_chart(instance_id: str):
    inst = engine.get_instance(instance_id)
    if not inst:
        raise HTTPException(404, "Instance not found")
    symbols = json.loads(inst.symbols) if isinstance(inst.symbols, str) else inst.symbols
    timeframe = inst.timeframe or "1d"
    result: dict = {"prices": {}, "trades": []}
    for sym in symbols:
        df = DATA_CACHE.ensure(sym, timeframe=timeframe)
        if df is not None and not df.empty:
            from datetime import datetime
            dates = [datetime.utcfromtimestamp(t).strftime("%m-%d %H:%M") for t in df.index.tolist()]
            values = [round(float(p), 2) for p in df["close"].tolist()]
            result["prices"][sym] = {"dates": dates, "values": values}
    raw_trades = engine.get_trades(instance_id, 500)
    result["trades"] = [
        {
            "symbol": t["symbol"],
            "side": t["side"],
            "price": t["price"],
            "time": t["executed_time"],
            "pnl": t.get("realized_pnl"),
        }
        for t in raw_trades
    ]
    return result


@router.get("/{instance_id}/positions")
def get_positions(instance_id: str):
    return engine.get_positions(instance_id)


@router.put("/{instance_id}/auto-tick")
def set_auto_tick(instance_id: str, enabled: bool = True, interval_sec: int = 10):
    inst = engine.get_instance(instance_id)
    if not inst:
        raise HTTPException(404, "Instance not found")
    engine.set_auto_tick(instance_id, enabled, interval_sec)
    return engine.get_instance(instance_id)


@router.post("/{instance_id}/tick")
def tick_instance(instance_id: str):
    result = engine.tick(instance_id)
    if result is None:
        inst = engine.get_instance(instance_id)
        if not inst:
            raise HTTPException(404, "Instance not found")
        return {"status": inst.status.value, "message": "Not running"}
    return result


@router.post("/webhook/binance")
def binance_webhook(payload: dict):
    symbol = (payload.get("data", payload).get("s", payload.get("symbol", "")) or "").replace("USDT", "/USDT")
    if "/" not in symbol:
        symbol = symbol
    bar = payload.get("data", payload).get("k", payload.get("kline", {}))
    if not bar:
        return {"ok": False, "message": "Missing kline data"}
    instances = engine.list_instances()
    ticked = []
    for inst in instances:
        syms = json.loads(inst.symbols) if isinstance(inst.symbols, str) else inst.symbols
        if inst.status != InstanceStatus.RUNNING:
            continue
        if symbol and symbol not in syms:
            continue
        engine.tick(inst.instance_id)
        ticked.append(inst.instance_id)
    return {"ok": True, "ticked": ticked}
