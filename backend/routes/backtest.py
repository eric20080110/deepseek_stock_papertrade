import json
import numpy as np
import pandas as pd

from fastapi import APIRouter, HTTPException
from typing import Optional, Any

from backtest.engine import run_backtest
from backtest.models import BacktestRequest, InstanceResult
from backtest.data_cache import DATA_CACHE
from database import get_db

router = APIRouter(prefix="/backtest", tags=["backtest"])


def _resolve_params(strategy_id: str, params: dict[str, Any]) -> dict[str, Any]:
    if params:
        return params
    from strategies.registry import STRATEGY_REGISTRY
    from seed import TEMPLATES
    for t in TEMPLATES:
        if t["template_id"] == strategy_id:
            return {p["name"]: p.get("default") for p in t["parameters"]}
    return params


def _generate_synthetic_data(
    symbol: str,
    n_bars: int = 500,
    start_price: float = 50000.0,
) -> pd.DataFrame:
    np.random.seed(hash(symbol) % (2**31))
    dates = pd.date_range(end="2025-12-31", periods=n_bars, freq="D")
    returns = np.random.normal(0.0005, 0.02, n_bars)
    price = start_price * np.exp(np.cumsum(returns))
    noise = np.random.uniform(-0.005, 0.005, n_bars)
    high = price * (1 + abs(noise) + 0.01 + np.random.uniform(0, 0.005, n_bars))
    low = price * (1 - abs(noise) - 0.01 - np.random.uniform(0, 0.005, n_bars))
    volume = np.random.uniform(100, 10000, n_bars)

    return pd.DataFrame(
        {
            "open": price,
            "high": high,
            "low": low,
            "close": price,
            "volume": volume,
        },
        index=dates,
    )


@router.post("/run", response_model=InstanceResult)
def run_backtest_endpoint(req: BacktestRequest):
    data_map: dict[str, pd.DataFrame] = {}
    for sym in req.symbols:
        cached = DATA_CACHE.ensure(sym)
        if cached is not None:
            df = cached
        else:
            df = _generate_synthetic_data(sym)
            DATA_CACHE.store(sym, df)
        if req.start_date and req.end_date:
            df = df.loc[req.start_date:req.end_date]
        data_map[sym] = df

    resolved_params = _resolve_params(req.strategy_id, req.params)

    try:
        result = run_backtest(
            strategy_id=req.strategy_id,
            params=resolved_params,
            symbols=req.symbols,
            data_map=data_map,
            initial_capital=req.initial_capital,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/strategies/{config_id}/run")
def run_backtest_for_strategy(
    config_id: str,
    symbols: str = "BTC/USDT,ETH/USDT",
    initial_capital: float = 10_000.0,
):
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM strategy_configs WHERE config_id = ?", (config_id,)
    ).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Strategy not found")

    params_dict = {}
    for p in json.loads(row["parameters_json"]):
        params_dict[p["name"]] = p.get("default")
    sid = row["template_id"] or row["config_id"][:8]

    symbol_list = [s.strip() for s in symbols.split(",")]
    data_map = {}
    for sym in symbol_list:
        cached = DATA_CACHE.ensure(sym)
        if cached is not None:
            data_map[sym] = cached
        else:
            df = _generate_synthetic_data(sym)
            DATA_CACHE.store(sym, df)
            data_map[sym] = df

    result = run_backtest(
        strategy_id=sid,
        params=params_dict,
        symbols=symbol_list,
        data_map=data_map,
        initial_capital=initial_capital,
    )
    return result
