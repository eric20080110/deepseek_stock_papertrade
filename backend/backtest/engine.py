import time
import numpy as np
import pandas as pd
from multiprocessing import Pool
from typing import Optional
from numba import njit

from .config import SETTINGS
from .models import TradeRecord, SymbolResult, InstanceResult
from .metrics import compute_metrics
from .data_cache import DATA_CACHE
from strategies.registry import STRATEGY_REGISTRY
from strategies.base import get_strategy_module


@njit(cache=True)
def _check_sl_tp(high_seg, low_seg, position, entry_price, sl_pct, tp_pct):
    if position == 1:
        sl_lvl = entry_price * (1.0 - sl_pct)
        tp_lvl = entry_price * (1.0 + tp_pct)
        for j in range(len(low_seg)):
            if sl_pct > 0.0 and low_seg[j] <= sl_lvl:
                return j
            if tp_pct > 0.0 and high_seg[j] >= tp_lvl:
                return j
    else:
        sl_lvl = entry_price * (1.0 + sl_pct)
        tp_lvl = entry_price * (1.0 - tp_pct)
        for j in range(len(high_seg)):
            if sl_pct > 0.0 and high_seg[j] >= sl_lvl:
                return j
            if tp_pct > 0.0 and low_seg[j] <= tp_lvl:
                return j
    return -1


@njit(cache=True)
def _run_backtest_core(
    sig, close, high, low, slip_arr, timestamps,
    initial_capital, taker_fee, stop_loss_pct, take_profit_pct, process,
):
    n = len(close)
    equity_arr = np.empty(n + 1, dtype=np.float64)
    equity_arr[0] = initial_capital
    equity_pos = 1

    max_trades = n // 2 + 2
    tr_entry_time = np.empty(max_trades, dtype=np.int64)
    tr_exit_time = np.empty(max_trades, dtype=np.int64)
    tr_entry_bar = np.empty(max_trades, dtype=np.int64)
    tr_exit_bar = np.empty(max_trades, dtype=np.int64)
    tr_entry_price = np.empty(max_trades, dtype=np.float64)
    tr_exit_price = np.empty(max_trades, dtype=np.float64)
    tr_quantity = np.empty(max_trades, dtype=np.float64)
    tr_pnl = np.empty(max_trades, dtype=np.float64)
    tr_pnl_pct = np.empty(max_trades, dtype=np.float64)
    tr_direction = np.empty(max_trades, dtype=np.int8)
    n_trades = 0

    position = 0
    cash = initial_capital
    holdings = 0.0
    entry_price_v = 0.0
    ct_entry_time = np.int64(0)
    ct_entry_bar = np.int64(0)
    ct_entry_price = 0.0
    ct_quantity = 0.0
    has_trade = False

    prev = 1

    for pi in range(len(process)):
        i = process[pi]

        if i > prev:
            if holdings == 0.0:
                for _ in range(i - prev):
                    equity_arr[equity_pos] = cash
                    equity_pos += 1
            else:
                breached = False
                if stop_loss_pct > 0.0 or take_profit_pct > 0.0:
                    bi = _check_sl_tp(
                        high[prev:i], low[prev:i],
                        position, entry_price_v,
                        stop_loss_pct, take_profit_pct,
                    )
                    if bi >= 0:
                        breached = True
                        for k in range(bi):
                            equity_arr[equity_pos] = cash + holdings * close[prev + k]
                            equity_pos += 1

                        exit_px = close[prev + bi]
                        eslip = slip_arr[prev + bi]
                        if position == 1:
                            exit_px_adj = exit_px * (1.0 - eslip)
                            trade_pnl = holdings * (exit_px_adj - entry_price_v)
                            cash += holdings * exit_px_adj
                        else:
                            exit_px_adj = exit_px * (1.0 + eslip)
                            trade_pnl = -holdings * (entry_price_v - exit_px_adj)
                            cash -= -holdings * exit_px_adj
                        fee = abs(holdings * exit_px_adj) * taker_fee
                        cash -= fee
                        net_pnl = trade_pnl - fee

                        if has_trade and n_trades < max_trades:
                            denom = ct_quantity * ct_entry_price
                            tr_entry_time[n_trades] = ct_entry_time
                            tr_exit_time[n_trades] = timestamps[prev + bi]
                            tr_entry_bar[n_trades] = ct_entry_bar
                            tr_exit_bar[n_trades] = prev + bi
                            tr_entry_price[n_trades] = ct_entry_price
                            tr_exit_price[n_trades] = exit_px_adj
                            tr_quantity[n_trades] = ct_quantity
                            tr_pnl[n_trades] = net_pnl
                            tr_pnl_pct[n_trades] = net_pnl / denom * 100.0 if denom != 0.0 else 0.0
                            tr_direction[n_trades] = position
                            n_trades += 1
                        has_trade = False
                        position = 0
                        holdings = 0.0

                        remaining = (i - prev) - bi - 1
                        for _ in range(remaining):
                            equity_arr[equity_pos] = cash
                            equity_pos += 1

                if not breached:
                    for k in range(i - prev):
                        equity_arr[equity_pos] = cash + holdings * close[prev + k]
                        equity_pos += 1

        if i >= n:
            break

        curr_close = close[i]
        signal = np.int8(sig[i - 1])

        # Exit
        if signal != 0 and signal != position and has_trade:
            eslip = slip_arr[i]
            if position == 1:
                exit_px = curr_close * (1.0 - eslip)
                trade_pnl = holdings * (exit_px - entry_price_v)
                cash += holdings * exit_px
            else:
                exit_px = curr_close * (1.0 + eslip)
                trade_pnl = -holdings * (entry_price_v - exit_px)
                cash -= -holdings * exit_px
            fee = abs(holdings * exit_px) * taker_fee
            cash -= fee
            net_pnl = trade_pnl - fee

            if n_trades < max_trades:
                denom = ct_quantity * ct_entry_price
                tr_entry_time[n_trades] = ct_entry_time
                tr_exit_time[n_trades] = timestamps[i]
                tr_entry_bar[n_trades] = ct_entry_bar
                tr_exit_bar[n_trades] = i
                tr_entry_price[n_trades] = ct_entry_price
                tr_exit_price[n_trades] = exit_px
                tr_quantity[n_trades] = ct_quantity
                tr_pnl[n_trades] = net_pnl
                tr_pnl_pct[n_trades] = net_pnl / denom * 100.0 if denom != 0.0 else 0.0
                tr_direction[n_trades] = position
                n_trades += 1
            has_trade = False
            position = 0
            holdings = 0.0

        # Entry
        if signal != 0 and signal != position:
            eslip = slip_arr[i]
            entry_px = curr_close * (1.0 + eslip) if signal == 1 else curr_close * (1.0 - eslip)
            qty = (initial_capital * 0.99) / entry_px
            fee = qty * entry_px * taker_fee
            if qty * entry_px + fee <= initial_capital:
                if signal == 1:
                    cash -= qty * entry_px + fee
                    holdings = qty
                else:
                    cash += qty * entry_px - fee
                    holdings = -qty
                position = signal
                entry_price_v = entry_px
                ct_entry_time = timestamps[i]
                ct_entry_bar = np.int64(i)
                ct_entry_price = entry_px
                ct_quantity = qty
                has_trade = True

        prev = i

    # Final open position
    if has_trade and position != 0:
        final_px = close[n - 1]
        if position == 1:
            trade_pnl = holdings * (final_px - entry_price_v)
            cash += holdings * final_px
        else:
            trade_pnl = -holdings * (entry_price_v - final_px)
            cash -= -holdings * final_px
        if n_trades < max_trades:
            denom = ct_quantity * ct_entry_price
            tr_entry_time[n_trades] = ct_entry_time
            tr_exit_time[n_trades] = timestamps[n - 1]
            tr_entry_bar[n_trades] = ct_entry_bar
            tr_exit_bar[n_trades] = n - 1
            tr_entry_price[n_trades] = ct_entry_price
            tr_exit_price[n_trades] = final_px
            tr_quantity[n_trades] = ct_quantity
            tr_pnl[n_trades] = trade_pnl
            tr_pnl_pct[n_trades] = trade_pnl / denom * 100.0 if denom != 0.0 else 0.0
            tr_direction[n_trades] = position
            n_trades += 1

    return (
        equity_arr[:equity_pos],
        n_trades,
        tr_entry_time[:n_trades],
        tr_exit_time[:n_trades],
        tr_entry_bar[:n_trades],
        tr_exit_bar[:n_trades],
        tr_entry_price[:n_trades],
        tr_exit_price[:n_trades],
        tr_quantity[:n_trades],
        tr_pnl[:n_trades],
        tr_pnl_pct[:n_trades],
        tr_direction[:n_trades],
    )


def run_symbol_backtest(
    symbol: str,
    data: pd.DataFrame,
    params: dict,
    strategy_id: str,
    initial_capital: float,
    stop_loss_pct: float = 0.0,
    take_profit_pct: float = 0.0,
) -> Optional[SymbolResult]:
    if len(data) < SETTINGS.min_bars:
        return None

    close = data["close"].values
    high = data["high"].values
    low = data["low"].values
    volume = data["volume"].values
    n = len(data)

    if n > 1:
        idx_vals = data.index.values
        if hasattr(idx_vals, "dtype") and "datetime64" in str(idx_vals.dtype):
            timestamps = (idx_vals.astype(np.int64) // 10**9).astype(np.int64)
        else:
            timestamps = idx_vals.astype(np.int64)
        avg_bar_sec = float(timestamps[-1] - timestamps[0]) / (n - 1)
        bars_per_year = int(365.25 * 86400 / avg_bar_sec) if avg_bar_sec > 0 else 365
    else:
        timestamps = np.zeros(1, dtype=np.int64)
        bars_per_year = 365

    strategy_module = get_strategy_module(strategy_id)
    if strategy_module is None:
        return None

    signals = strategy_module.generate_signals(data, params)
    sig = np.asarray(signals.values, dtype=np.int8)

    entry_qty = (initial_capital * 0.99) / np.maximum(close, 1.0)
    vol_ratio = np.where(volume > 0, entry_qty / volume, 0.0)
    slip_arr = np.minimum(vol_ratio * 0.001, SETTINGS.max_slippage_rate)
    slip_arr[vol_ratio < SETTINGS.slippage_volume_ratio] = 0.0

    sig_diff = np.where(sig[:-1] != sig[1:])[0] + 2
    process = sig_diff[sig_diff < n]
    process = np.unique(np.concatenate([process, [n]])).astype(np.int64) if len(process) else np.array([n], dtype=np.int64)

    (
        equity_curve,
        n_trades,
        entry_times, exit_times,
        entry_bars, exit_bars,
        entry_prices, exit_prices,
        quantities, pnls, pnl_pcts, directions,
    ) = _run_backtest_core(
        sig, close, high, low,
        slip_arr.astype(np.float64),
        timestamps,
        float(initial_capital),
        float(SETTINGS.taker_fee_rate),
        float(stop_loss_pct),
        float(take_profit_pct),
        process,
    )

    trades = [
        TradeRecord(
            symbol=symbol,
            entry_time=int(entry_times[k]),
            exit_time=int(exit_times[k]),
            entry_bar=int(entry_bars[k]),
            exit_bar=int(exit_bars[k]),
            entry_price=float(entry_prices[k]),
            exit_price=float(exit_prices[k]),
            quantity=float(quantities[k]),
            pnl=round(float(pnls[k]), 2),
            pnl_pct=round(float(pnl_pcts[k]), 4),
            direction=int(directions[k]),
        )
        for k in range(n_trades)
    ]

    equity_list = [float(v) for v in equity_curve]
    equity_timestamps = [int(t) for t in timestamps.tolist()]

    metrics_dict = compute_metrics(equity_list, trades, n, bars_per_year)
    avg_dv = float(np.mean(volume)) if n > 0 else 0.0

    return SymbolResult(
        symbol=symbol,
        total_return=metrics_dict["total_return"],
        annualized_return=metrics_dict["annualized_return"],
        sharpe_ratio=metrics_dict["sharpe_ratio"],
        sortino_ratio=metrics_dict["sortino_ratio"],
        calmar_ratio=metrics_dict["calmar_ratio"],
        max_drawdown=metrics_dict["max_drawdown"],
        win_rate=metrics_dict["win_rate"],
        profit_factor=metrics_dict["profit_factor"],
        trade_count=metrics_dict["trade_count"],
        equity_curve=equity_list,
        equity_timestamps=equity_timestamps,
        trades=trades,
        avg_daily_volume=avg_dv,
    )


def _run_symbol_wrapper(args: tuple) -> Optional[SymbolResult]:
    if len(args) >= 7:
        symbol, data, params, strategy_id, initial_capital, stop_loss_pct, take_profit_pct = args
    else:
        symbol, data, params, strategy_id, initial_capital = args
        stop_loss_pct = take_profit_pct = 0.0
    df = DATA_CACHE.ensure(symbol)
    if df is None:
        df = data
    if df is None or df.empty:
        return None
    return run_symbol_backtest(symbol, df, params, strategy_id, initial_capital, stop_loss_pct, take_profit_pct)


def run_ensemble_backtest(
    strategies: list[tuple[str, dict]],  # [(strategy_id, params), ...]
    symbols: list[str],
    data_map: dict[str, pd.DataFrame],
    initial_capital: float = 10_000.0,
    ensemble_threshold: float = 0.2,
    stop_loss_pct: float = 0.0,
    take_profit_pct: float = 0.0,
) -> InstanceResult:
    """Run signal-averaging ensemble backtest across multiple strategies."""
    start = time.time()

    for sym, df in data_map.items():
        DATA_CACHE.store(sym, df)

    symbol_results: dict[str, SymbolResult] = {}

    for sym in symbols:
        df = data_map.get(sym)
        if df is None or len(df) < SETTINGS.min_bars:
            continue

        close = df["close"].values
        high = df["high"].values
        low = df["low"].values
        volume = df["volume"].values
        n = len(df)

        if n > 1:
            idx_vals = df.index.values
            if hasattr(idx_vals, "dtype") and "datetime64" in str(idx_vals.dtype):
                timestamps = (idx_vals.astype(np.int64) // 10**9).astype(np.int64)
            else:
                timestamps = idx_vals.astype(np.int64)
            avg_bar_sec = float(timestamps[-1] - timestamps[0]) / (n - 1)
            bars_per_year = int(365.25 * 86400 / avg_bar_sec) if avg_bar_sec > 0 else 365
        else:
            timestamps = np.zeros(1, dtype=np.int64)
            bars_per_year = 365

        all_sigs = []
        for strategy_id, params in strategies:
            mod = get_strategy_module(strategy_id)
            if mod is None:
                continue
            signals = mod.generate_signals(df, params)
            all_sigs.append(signals.values.astype(np.float64))

        if not all_sigs:
            continue

        # Average signals across strategies
        avg_sig = np.mean(all_sigs, axis=0)
        # Threshold to int8
        sig = np.zeros(n, dtype=np.int8)
        sig[avg_sig > ensemble_threshold] = 1
        sig[avg_sig < -ensemble_threshold] = -1

        entry_qty = (initial_capital * 0.99) / np.maximum(close, 1.0)
        vol_ratio = np.where(volume > 0, entry_qty / volume, 0.0)
        slip_arr = np.minimum(vol_ratio * 0.001, SETTINGS.max_slippage_rate)
        slip_arr[vol_ratio < SETTINGS.slippage_volume_ratio] = 0.0

        sig_diff = np.where(sig[:-1] != sig[1:])[0] + 2
        process = sig_diff[sig_diff < n]
        process = np.unique(np.concatenate([process, [n]])).astype(np.int64) if len(process) else np.array([n], dtype=np.int64)

        (equity_curve, n_trades, entry_times, exit_times,
         entry_bars, exit_bars, entry_prices, exit_prices,
         quantities, pnls, pnl_pcts, directions) = _run_backtest_core(
            sig, close, high, low,
            slip_arr.astype(np.float64), timestamps,
            float(initial_capital), float(SETTINGS.taker_fee_rate),
            float(stop_loss_pct), float(take_profit_pct), process,
        )

        trades = [
            TradeRecord(symbol=sym, entry_time=int(entry_times[k]), exit_time=int(exit_times[k]),
                        entry_bar=int(entry_bars[k]), exit_bar=int(exit_bars[k]),
                        entry_price=float(entry_prices[k]), exit_price=float(exit_prices[k]),
                        quantity=float(quantities[k]), pnl=round(float(pnls[k]), 2),
                        pnl_pct=round(float(pnl_pcts[k]), 4), direction=int(directions[k]))
            for k in range(n_trades)
        ]
        equity_list = [float(v) for v in equity_curve]
        metrics_dict = compute_metrics(equity_list, trades, n, bars_per_year)
        avg_dv = float(np.mean(volume)) if n > 0 else 0.0

        symbol_results[sym] = SymbolResult(
            symbol=sym, total_return=metrics_dict["total_return"],
            annualized_return=metrics_dict["annualized_return"],
            sharpe_ratio=metrics_dict["sharpe_ratio"],
            sortino_ratio=metrics_dict["sortino_ratio"],
            calmar_ratio=metrics_dict["calmar_ratio"],
            max_drawdown=metrics_dict["max_drawdown"],
            win_rate=metrics_dict["win_rate"],
            profit_factor=metrics_dict["profit_factor"],
            trade_count=metrics_dict["trade_count"],
            equity_curve=equity_list,
            equity_timestamps=[int(t) for t in timestamps.tolist()],
            trades=trades, avg_daily_volume=avg_dv,
        )

    total_volume = sum(r.avg_daily_volume for r in symbol_results.values())
    weights = {}
    if total_volume > 0:
        for sym, r in symbol_results.items():
            weights[sym] = r.avg_daily_volume / total_volume
    else:
        n = len(symbol_results)
        for sym in symbol_results:
            weights[sym] = 1.0 / n if n > 0 else 0.0

    metric_keys = ["total_return", "annualized_return", "sharpe_ratio", "max_drawdown",
                   "win_rate", "profit_factor", "trade_count"]
    weighted_metrics = {}
    for key in metric_keys:
        val = sum(getattr(r, key) * weights[sym] for sym, r in symbol_results.items())
        weighted_metrics[key] = round(val, 4)

    return InstanceResult(
        strategy_id="ensemble",
        params={"n_strategies": len(strategies), "threshold": ensemble_threshold},
        symbol_results=symbol_results,
        weighted_metrics=weighted_metrics,
        weights=weights,
        backtest_duration_sec=round(time.time() - start, 4),
    )


def run_backtest(
    strategy_id: str,
    params: dict,
    symbols: list[str],
    data_map: dict[str, pd.DataFrame],
    initial_capital: float = 10_000.0,
    parallel: bool = True,
    stop_loss_pct: float = 0.0,
    take_profit_pct: float = 0.0,
) -> InstanceResult:
    start = time.time()

    for sym, df in data_map.items():
        DATA_CACHE.store(sym, df)

    if parallel and len(symbols) > 1:
        args_list = [
            (sym, data_map.get(sym), params, strategy_id, initial_capital, stop_loss_pct, take_profit_pct)
            for sym in symbols
        ]
        with Pool() as pool:
            results = pool.map(_run_symbol_wrapper, args_list)
    else:
        results = []
        for sym in symbols:
            df = data_map.get(sym)
            if df is not None:
                results.append(
                    run_symbol_backtest(sym, df, params, strategy_id, initial_capital, stop_loss_pct, take_profit_pct)
                )

    symbol_results: dict[str, SymbolResult] = {}
    for r in results:
        if r is not None:
            symbol_results[r.symbol] = r

    total_volume = sum(r.avg_daily_volume for r in symbol_results.values())
    weights: dict[str, float] = {}
    if total_volume > 0:
        for sym, r in symbol_results.items():
            weights[sym] = r.avg_daily_volume / total_volume
    else:
        n = len(symbol_results)
        for sym in symbol_results:
            weights[sym] = 1.0 / n if n > 0 else 0.0

    metric_keys = ["total_return", "annualized_return", "sharpe_ratio", "max_drawdown",
                   "win_rate", "profit_factor", "trade_count"]
    weighted_metrics: dict[str, float] = {}
    for key in metric_keys:
        val = sum(getattr(r, key) * weights[sym] for sym, r in symbol_results.items())
        weighted_metrics[key] = round(val, 4)

    return InstanceResult(
        strategy_id=strategy_id,
        params=params,
        symbol_results=symbol_results,
        weighted_metrics=weighted_metrics,
        weights=weights,
        backtest_duration_sec=round(time.time() - start, 4),
    )
