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

    # GARCH(1,1)-like volatility with fat-tailed t-distribution
    omega = 0.000001
    alpha = 0.12
    beta = 0.84
    sigma2 = 0.0004
    returns = np.zeros(n_bars)
    for i in range(n_bars):
        sigma2 = omega + alpha * (returns[i - 1] ** 2 if i > 0 else 0) + beta * sigma2
        returns[i] = np.random.standard_t(4) * np.sqrt(sigma2)
    returns += 0.0005

    price = start_price * np.exp(np.cumsum(returns))
    vol_scale = np.sqrt(sigma2) / np.sqrt(0.0004) if sigma2 > 0 else 1.0
    base_vol = 0.01 * vol_scale
    noise = np.random.uniform(-base_vol, base_vol, n_bars)
    high = price * (1 + abs(noise) + base_vol + np.random.uniform(0, base_vol, n_bars))
    low = price * (1 - abs(noise) - base_vol - np.random.uniform(0, base_vol, n_bars))
    volume = np.random.lognormal(
        mean=np.log(abs(returns) * 1e5 + 100),
        sigma=0.5,
        size=n_bars,
    )

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
            stop_loss_pct=req.stop_loss_pct,
            take_profit_pct=req.take_profit_pct,
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
