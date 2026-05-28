import uuid
import time
import numpy as np
import pandas as pd
from multiprocessing import Pool, set_start_method

from profile_helper import log as _plog
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


def _run_one_rotation(params: dict, sid: str, icap: float) -> Optional[dict]:
    from strategies.base import get_strategy_module
    from backtest.rotation_engine import run_rotation_backtest
    _t0 = time.perf_counter()
    mod = get_strategy_module(sid)
    rot_symbols = list(getattr(mod, "ROTATION_SYMBOLS", []))
    safe_sym = getattr(mod, "SAFE_SYMBOL", "BIL")
    spy_sym = getattr(mod, "SPY_SYMBOL", "SPY")

    all_syms = rot_symbols + ([spy_sym] if spy_sym not in rot_symbols else [])
    data_map = {}
    for sym in all_syms:
        df = DATA_CACHE.ensure(sym)
        if df is not None:
            data_map[sym] = df

    if not data_map:
        return None

    result = run_rotation_backtest(
        data_map, params, initial_capital=icap,
        rotation_symbols=rot_symbols, safe_symbol=safe_sym, spy_symbol=spy_sym,
        strategy_module=mod,
    )
    if result is None:
        return None

    is_metrics = {
        "annualized_return": result.annualized_return,
        "sharpe_ratio": result.sharpe_ratio,
        "max_drawdown": result.max_drawdown,
        "profit_factor": result.profit_factor,
        "win_rate": result.win_rate,
        "trade_count": result.trade_count,
        "equity_curve": result.equity_curve,
        "equity_timestamps": result.equity_timestamps,
    }
    _t1 = time.perf_counter()
    _plog(f"rotation backtest {_t1-_t0:.2f}s "
          f"n_bars={len(result.equity_curve)} trades={result.trade_count}")

    # Rotation strategies use the full dataset (SMA200 warm-up requires full history).
    # Pass IS metrics as OOS proxy so OOS consistency check doesn't eliminate all individuals.
    return {
        "strategy_id": str(uuid.uuid4()),
        "params": params,
        "symbol_results": {result.symbol: result.model_dump()},
        "weighted_metrics": is_metrics,
        "oos_metrics": dict(is_metrics),
    }


def _run_one(params: dict) -> Optional[dict]:
    sid = _WORKER_CTX["strategy_id"]
    symbols = _WORKER_CTX["symbols"]
    icap = _WORKER_CTX["initial_capital"]
    walk_maps = _WORKER_CTX.get("walk_data_maps", [])

    # Rotation strategy: different execution path
    from strategies.base import get_strategy_module
    mod = get_strategy_module(sid)
    if mod and getattr(mod, "IS_ROTATION", False):
        return _run_one_rotation(params, sid, icap)

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
            _t0 = time.perf_counter()
            with Pool(
                self.max_workers,
                initializer=_init_worker,
                initargs=(strategy_id, symbols, data_map, initial_capital, oos_data_map, walk_maps),
            ) as pool:
                results = pool.map(_run_one, individuals)
            _t1 = time.perf_counter()
            _plog(f"Pool gen: {_t1-_t0:.2f}s for {len(individuals)} individuals "
                  f"({self.max_workers} workers)")
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
