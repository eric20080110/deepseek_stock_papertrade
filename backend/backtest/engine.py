import time
import numpy as np
import pandas as pd
from multiprocessing import Pool
from functools import partial
from typing import Optional

from .config import SETTINGS
from .models import TradeRecord, SymbolResult, InstanceResult
from .metrics import compute_metrics
from .data_cache import DATA_CACHE
from strategies.registry import STRATEGY_REGISTRY
from strategies.base import get_strategy_module


def _check_sl_tp_breach(
    high_seg: np.ndarray,
    low_seg: np.ndarray,
    position: int,
    entry_price: float,
    stop_loss_pct: float,
    take_profit_pct: float,
) -> Optional[int]:
    """Return index of first bar in segment where SL or TP is breached, or None."""
    if position == 1:
        sl_lvl = entry_price * (1.0 - stop_loss_pct)
        tp_lvl = entry_price * (1.0 + take_profit_pct)
        for j in range(len(low_seg)):
            if stop_loss_pct > 0 and low_seg[j] <= sl_lvl:
                return j
            if take_profit_pct > 0 and high_seg[j] >= tp_lvl:
                return j
    else:
        sl_lvl = entry_price * (1.0 + stop_loss_pct)
        tp_lvl = entry_price * (1.0 - take_profit_pct)
        for j in range(len(high_seg)):
            if stop_loss_pct > 0 and high_seg[j] >= sl_lvl:
                return j
            if take_profit_pct > 0 and low_seg[j] <= tp_lvl:
                return j
    return None


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
            timestamps = idx_vals.astype(np.int64) // 10**9
        else:
            timestamps = idx_vals.astype(np.float64)
        avg_bar_sec = float(timestamps[-1] - timestamps[0]) / (n - 1)
        bars_per_year = int(365.25 * 86400 / avg_bar_sec) if avg_bar_sec > 0 else 365
    else:
        timestamps = np.zeros(1, dtype=np.float64)
        bars_per_year = 365

    strategy_module = get_strategy_module(strategy_id)
    if strategy_module is None:
        return None

    signals = strategy_module.generate_signals(data, params)
    sig = np.asarray(signals.values, dtype=np.int8)

    # --- Pre-compute per-bar arrays (vectorized) ---
    entry_qty = (initial_capital * 0.99) / np.maximum(close, 1.0)
    vol_ratio = np.where(volume > 0, entry_qty / volume, 0.0)
    slip_arr = np.minimum(vol_ratio * 0.001, SETTINGS.max_slippage_rate)
    slip_arr[vol_ratio < SETTINGS.slippage_volume_ratio] = 0.0
    max_slip = SETTINGS.max_slippage_rate
    taker_fee = SETTINGS.taker_fee_rate

    # Find bars where signal changes (index into sig, add 1 for loop offset)
    sig_diff = np.where(sig[:-1] != sig[1:])[0] + 2
    # Deduplicate and sort (already sorted from where)
    process = sig_diff[sig_diff < n]
    process = np.unique(np.concatenate([process, [n]])) if len(process) else np.array([n], dtype=np.int64)

    # --- Stateful trade loop (only over signal-change bars) ---
    position: int = 0
    cash = float(initial_capital)
    holdings = 0.0
    entry_price_v = 0.0
    equity_bars: list[float] = []
    trades: list[TradeRecord] = []
    current_trade: Optional[dict] = None
    prev = 1

    for i in process:
        # Fill equity for the segment where position/holdings/cash are constant
        if i > prev:
            if not holdings:
                equity_bars.extend([cash] * (i - prev))
            else:
                breached = False
                if stop_loss_pct > 0 or take_profit_pct > 0:
                    bi = _check_sl_tp_breach(
                        high[prev:i], low[prev:i],
                        position, entry_price_v,
                        stop_loss_pct, take_profit_pct,
                    )
                    if bi is not None:
                        breached = True
                        # fill equity before breach (still in position)
                        if bi > 0:
                            seg = cash + holdings * close[prev:prev + bi]
                            equity_bars.extend(float(v) for v in seg)
                        # close at breach bar
                        exit_px = float(close[prev + bi])
                        eslip = float(slip_arr[prev + bi])
                        exit_px_adj = exit_px * (1.0 - eslip) if position == 1 else exit_px * (1.0 + eslip)

                        if position == 1:
                            trade_pnl = holdings * (exit_px_adj - entry_price_v)
                            cash += holdings * exit_px_adj
                        else:
                            trade_pnl = -holdings * (entry_price_v - exit_px_adj)
                            cash -= -holdings * exit_px_adj
                        fee = abs(holdings * exit_px_adj) * taker_fee
                        cash -= fee
                        net_pnl = trade_pnl - fee

                        trades.append(TradeRecord(
                            symbol=symbol,
                            entry_time=int(current_trade["entry_time"]),
                            exit_time=int(timestamps[prev + bi]),
                            entry_bar=current_trade["entry_bar"],
                            exit_bar=prev + bi,
                            entry_price=current_trade["entry_price"],
                            exit_price=exit_px_adj,
                            quantity=current_trade["quantity"],
                            pnl=round(net_pnl, 2),
                            pnl_pct=round(
                                net_pnl / (current_trade["quantity"] * current_trade["entry_price"]) * 100, 4
                            ),
                            direction=position,
                        ))
                        current_trade = None
                        position = 0
                        holdings = 0.0

                        # fill equity after breach (flat) until next process point
                        remaining = (i - prev) - bi - 1
                        if remaining > 0:
                            equity_bars.extend([cash] * remaining)

                if not breached:
                    seg = cash + holdings * close[prev:i]
                    equity_bars.extend(float(v) for v in seg)

        if i >= n:
            break

        curr_close = float(close[i])
        signal = int(sig[i - 1])

        # --- Exit ---
        if signal != 0 and signal != position and current_trade is not None:
            eslip = float(slip_arr[i])
            exit_px = curr_close * (1.0 - eslip) if position == 1 else curr_close * (1.0 + eslip)

            if position == 1:
                trade_pnl = holdings * (exit_px - entry_price_v)
                cash += holdings * exit_px
            else:
                trade_pnl = -holdings * (entry_price_v - exit_px)
                cash -= -holdings * exit_px
            fee = abs(holdings * exit_px) * taker_fee
            cash -= fee
            net_pnl = trade_pnl - fee

            trades.append(TradeRecord(
                symbol=symbol,
                entry_time=int(current_trade["entry_time"]),
                exit_time=int(timestamps[i]),
                entry_bar=current_trade["entry_bar"],
                exit_bar=i,
                entry_price=current_trade["entry_price"],
                exit_price=exit_px,
                quantity=current_trade["quantity"],
                pnl=round(net_pnl, 2),
                pnl_pct=round(net_pnl / (current_trade["quantity"] * current_trade["entry_price"]) * 100, 4),
                direction=position,
            ))
            current_trade = None
            position = 0
            holdings = 0.0

        # --- Entry ---
        if signal != 0 and signal != position:
            eslip = float(slip_arr[i])
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
                current_trade = {
                    "entry_time": int(timestamps[i]),
                    "entry_bar": i,
                    "entry_price": entry_px,
                    "quantity": qty,
                }

        prev = i

    # Handle final open position
    if current_trade is not None and position != 0:
        final_px = float(close[-1])
        if position == 1:
            trade_pnl = holdings * (final_px - entry_price_v)
            cash += holdings * final_px
        else:
            trade_pnl = -holdings * (entry_price_v - final_px)
            cash -= -holdings * final_px
        holdings = 0.0
        trades.append(TradeRecord(
            symbol=symbol,
            entry_time=current_trade["entry_time"],
            exit_time=int(timestamps[-1]),
            entry_bar=current_trade["entry_bar"],
            exit_bar=n - 1,
            entry_price=current_trade["entry_price"],
            exit_price=final_px,
            quantity=current_trade["quantity"],
            pnl=round(trade_pnl, 2),
            pnl_pct=round(trade_pnl / (current_trade["quantity"] * current_trade["entry_price"]) * 100, 4),
            direction=position,
        ))

    equity_curve = [float(initial_capital)] + equity_bars
    equity_timestamps = [int(t) for t in timestamps.tolist()]

    metrics_dict = compute_metrics(equity_curve, trades, n, bars_per_year)
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
        equity_curve=equity_curve,
        equity_timestamps=equity_timestamps,
        trades=trades,
        avg_daily_volume=float(avg_dv),
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

    strategy_id_short = strategy_id.split(".")[-1].replace("_", "")

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

    total_volume = sum(
        r.avg_daily_volume for r in symbol_results.values()
    )
    weights: dict[str, float] = {}
    if total_volume > 0:
        for sym, r in symbol_results.items():
            weights[sym] = r.avg_daily_volume / total_volume
    else:
        n = len(symbol_results)
        for sym in symbol_results:
            weights[sym] = 1.0 / n if n > 0 else 0.0

    weighted_metrics: dict[str, float] = {}
    metric_keys = [
        "total_return",
        "annualized_return",
        "sharpe_ratio",
        "max_drawdown",
        "win_rate",
        "profit_factor",
        "trade_count",
    ]
    for key in metric_keys:
        val = sum(
            getattr(r, key) * weights[sym]
            for sym, r in symbol_results.items()
        )
        weighted_metrics[key] = round(val, 4)

    duration = time.time() - start

    return InstanceResult(
        strategy_id=strategy_id,
        params=params,
        symbol_results=symbol_results,
        weighted_metrics=weighted_metrics,
        weights=weights,
        backtest_duration_sec=round(duration, 4),
    )
