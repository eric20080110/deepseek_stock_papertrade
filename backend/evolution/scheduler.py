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


def _init_worker(strategy_id: str, symbols: list[str], data_map: dict, initial_capital: float,
                  oos_data_map: Optional[dict] = None, walk_data_maps: Optional[list] = None):
    _WORKER_CTX["strategy_id"] = strategy_id
    _WORKER_CTX["symbols"] = symbols
    _WORKER_CTX["initial_capital"] = initial_capital
    _WORKER_CTX["walk_data_maps"] = walk_data_maps or [(data_map, oos_data_map or {})]
    for sym, df in data_map.items():
        DATA_CACHE.store(sym, df)


def _run_backtest_on_map(symbols: list[str], params: dict, sid: str, icap: float, data_map: dict,
                         stop_loss_pct: float = 0.0, take_profit_pct: float = 0.0) -> list[dict]:
    results = []
    for sym in symbols:
        df = data_map.get(sym)
        if df is None or len(df) < 2:
            continue
        sr = run_symbol_backtest(
            symbol=sym, data=df, params=params,
            strategy_id=sid, initial_capital=icap,
            stop_loss_pct=stop_loss_pct, take_profit_pct=take_profit_pct,
        )
        if sr is None:
            continue
        results.append({
            "symbol": sr.symbol,
            "annualized_return": sr.annualized_return,
            "sharpe_ratio": sr.sharpe_ratio,
            "max_drawdown": sr.max_drawdown,
            "profit_factor": sr.profit_factor,
            "win_rate": sr.win_rate,
            "trade_count": sr.trade_count,
            "equity_curve": sr.equity_curve,
            "equity_timestamps": sr.equity_timestamps,
            "trades": [t.model_dump() for t in sr.trades],
        })
    return results


def _aggregate_results(results: list[dict]) -> dict:
    if not results:
        return {}
    weighted: dict = {}
    for key in ["annualized_return", "sharpe_ratio", "max_drawdown", "profit_factor", "win_rate", "trade_count"]:
        vals = [sr[key] for sr in results]
        weighted[key] = float(np.mean(vals)) if vals else 0.0
    equity_curves = [sr.get("equity_curve") for sr in results if sr.get("equity_curve")]
    if equity_curves:
        min_len = min(len(e) for e in equity_curves)
        weighted["equity_curve"] = [float(np.mean([e[i] for e in equity_curves])) for i in range(min_len)]
    else:
        weighted["equity_curve"] = []
    ts_list = [sr.get("equity_timestamps") for sr in results if sr.get("equity_timestamps")]
    weighted["equity_timestamps"] = ts_list[0] if ts_list else []
    return weighted


def _run_on_window(params: dict, symbols: list[str], sid: str, icap: float,
                   is_map: dict, oos_map: dict) -> Optional[dict]:
    is_results = _run_backtest_on_map(symbols, params, sid, icap, is_map)
    if not is_results:
        return None
    oos_results = _run_backtest_on_map(symbols, params, sid, icap, oos_map)
    weighted = _aggregate_results(is_results)
    oos_weighted = _aggregate_results(oos_results) if oos_results else None
    return {"is": weighted, "oos": oos_weighted, "symbol_results": {sr["symbol"]: sr for sr in is_results}}


def _run_one(params: dict) -> Optional[dict]:
    sid = _WORKER_CTX["strategy_id"]
    symbols = _WORKER_CTX["symbols"]
    icap = _WORKER_CTX["initial_capital"]
    walk_maps = _WORKER_CTX.get("walk_data_maps", [])

    window_results = []
    for is_map, oos_map in walk_maps:
        sym_data = {sym: DATA_CACHE.ensure(sym) for sym in symbols}
        resolved_is = {sym: is_map.get(sym, sym_data.get(sym)) for sym in symbols}
        resolved_oos = {sym: oos_map.get(sym, sym_data.get(sym)) for sym in symbols}
        r = _run_on_window(params, symbols, sid, icap, resolved_is, resolved_oos)
        if r is not None:
            window_results.append(r)

    if not window_results:
        return None

    # Average IS metrics across all windows
    is_keys = ["annualized_return", "sharpe_ratio", "max_drawdown", "profit_factor", "win_rate", "trade_count"]
    avg_is = {k: float(np.mean([w["is"][k] for w in window_results if w["is"]])) for k in is_keys}

    equity_curves = [w["is"].get("equity_curve") for w in window_results if w["is"] and w["is"].get("equity_curve")]
    if equity_curves:
        min_len = min(len(e) for e in equity_curves)
        avg_is["equity_curve"] = [float(np.mean([e[i] for e in equity_curves])) for i in range(min_len)]
    else:
        avg_is["equity_curve"] = []
    ts_list = [w["is"].get("equity_timestamps") for w in window_results if w["is"] and w["is"].get("equity_timestamps")]
    avg_is["equity_timestamps"] = ts_list[0] if ts_list else []

    # Average OOS metrics across windows that have data
    oos_list = [w.get("oos") for w in window_results if w.get("oos")]
    if oos_list:
        avg_oos = {k: float(np.mean([o[k] for o in oos_list])) for k in is_keys if k != "trade_count"}
        avg_oos["equity_curve"] = []
    else:
        avg_oos = None

    # Use per-symbol results from the first window
    symbol_results = window_results[0].get("symbol_results", {}) if window_results else {}

    return {
        "strategy_id": str(uuid.uuid4()),
        "params": params,
        "symbol_results": symbol_results,
        "weighted_metrics": avg_is,
        "oos_metrics": avg_oos,
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
        oos_data_map: Optional[dict[str, pd.DataFrame]] = None,
        walk_data_maps: Optional[list[tuple[dict, dict]]] = None,
        on_progress: Optional[callable] = None,
    ) -> list[Optional[dict]]:
        walk_maps = walk_data_maps or [(data_map, oos_data_map or {})]

        if self.max_workers > 1 and len(individuals) > 1:
            with Pool(
                self.max_workers,
                initializer=_init_worker,
                initargs=(strategy_id, symbols, data_map, initial_capital, oos_data_map, walk_maps),
            ) as pool:
                results = pool.map(_run_one, individuals)
            if on_progress:
                on_progress(len(individuals), len(individuals))
            return [r for r in results if r is not None]

        for sym in symbols:
            DATA_CACHE.store(sym, data_map[sym])
        _WORKER_CTX["walk_data_maps"] = walk_maps

        results: list[Optional[dict]] = []
        for idx, ind in enumerate(individuals):
            _WORKER_CTX["strategy_id"] = strategy_id
            _WORKER_CTX["symbols"] = symbols
            _WORKER_CTX["initial_capital"] = initial_capital
            r = _run_one(ind)
            if r:
                results.append(r)
            if on_progress:
                on_progress(idx + 1, len(individuals))
        return results
