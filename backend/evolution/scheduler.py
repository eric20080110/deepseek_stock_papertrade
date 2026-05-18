import uuid
import numpy as np
import pandas as pd
from multiprocessing import Pool, set_start_method
from functools import partial
from typing import Optional

from backtest.engine import run_symbol_backtest
from backtest.data_cache import DATA_CACHE
from evolution.config import SETTINGS

try:
    set_start_method("spawn")
except RuntimeError:
    pass

_WORKER_CTX: dict = {}


def _init_worker(strategy_id: str, symbols: list[str], data_map: dict, initial_capital: float):
    _WORKER_CTX["strategy_id"] = strategy_id
    _WORKER_CTX["symbols"] = symbols
    _WORKER_CTX["initial_capital"] = initial_capital
    for sym, df in data_map.items():
        DATA_CACHE.store(sym, df)


def _run_one(params: dict) -> Optional[dict]:
    sid = _WORKER_CTX["strategy_id"]
    symbols = _WORKER_CTX["symbols"]
    icap = _WORKER_CTX["initial_capital"]
    symbol_results = []
    for sym in symbols:
        df = DATA_CACHE.ensure(sym)
        if df is None:
            continue
        sr = run_symbol_backtest(
            symbol=sym, data=df, params=params,
            strategy_id=sid, initial_capital=icap,
        )
        if sr is None:
            continue
        symbol_results.append({
            "symbol": sr.symbol,
            "annualized_return": sr.annualized_return,
            "sharpe_ratio": sr.sharpe_ratio,
            "max_drawdown": sr.max_drawdown,
            "profit_factor": sr.profit_factor,
            "win_rate": sr.win_rate,
            "trade_count": sr.trade_count,
            "equity_curve": sr.equity_curve,
            "trades": [t.model_dump() for t in sr.trades],
        })

    if not symbol_results:
        return None

    weighted: dict = {}
    for key in ["annualized_return", "sharpe_ratio", "max_drawdown", "profit_factor", "win_rate", "trade_count"]:
        vals = [sr[key] for sr in symbol_results]
        weighted[key] = float(np.mean(vals)) if vals else 0.0

    equity_curves = [sr.get("equity_curve") for sr in symbol_results if sr.get("equity_curve")]
    if equity_curves:
        min_len = min(len(e) for e in equity_curves)
        weighted["equity_curve"] = [float(np.mean([e[i] for e in equity_curves])) for i in range(min_len)]
    else:
        weighted["equity_curve"] = []

    return {
        "strategy_id": str(uuid.uuid4()),
        "params": params,
        "symbol_results": {sr["symbol"]: sr for sr in symbol_results},
        "weighted_metrics": weighted,
    }


class ParallelScheduler:
    def __init__(self, max_workers: Optional[int] = None):
        self.max_workers = max_workers or SETTINGS.max_workers

    def run_backtests(
        self,
        individuals: list[dict],
        strategy_id: str,
        symbols: list[str],
        data_map: dict[str, pd.DataFrame],
        initial_capital: float = 10_000.0,
        on_progress: Optional[callable] = None,
    ) -> list[Optional[dict]]:
        if self.max_workers > 1 and len(individuals) > 1:
            with Pool(
                self.max_workers,
                initializer=_init_worker,
                initargs=(strategy_id, symbols, data_map, initial_capital),
            ) as pool:
                results = pool.map(_run_one, individuals)
            if on_progress:
                on_progress(len(individuals), len(individuals))
            return [r for r in results if r is not None]

        for sym in symbols:
            DATA_CACHE.store(sym, data_map[sym])

        results: list[Optional[dict]] = []
        for idx, ind in enumerate(individuals):
            r = _run_one(ind)
            if r:
                results.append(r)
            if on_progress:
                on_progress(idx + 1, len(individuals))
        return results
