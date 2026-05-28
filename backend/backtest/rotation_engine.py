"""
Multi-asset rotation backtest engine for IS_ROTATION strategies.
Simulates daily portfolio rotation between a fixed set of ETFs.
"""
import uuid
import time
import numpy as np
import pandas as pd
from typing import Optional

from .models import TradeRecord, SymbolResult
from .metrics import compute_metrics
from profile_helper import log as _plog


def _align_data(data_map: dict[str, pd.DataFrame]) -> tuple[pd.DatetimeIndex, dict[str, np.ndarray]]:
    """Return common daily index and close arrays, forward-filled."""
    dfs = {}
    for sym, df in data_map.items():
        if df is None or df.empty:
            continue
        s = df["close"].copy()
        if not isinstance(s.index, pd.DatetimeIndex):
            try:
                s.index = pd.to_datetime(s.index, unit="s", utc=True).tz_localize(None)
            except Exception:
                s.index = pd.to_datetime(s.index)
        s = s[~s.index.duplicated(keep="last")]
        dfs[sym] = s

    if not dfs:
        return pd.DatetimeIndex([]), {}

    combined = pd.DataFrame(dfs).sort_index()
    combined = combined.ffill().dropna(how="all")
    idx = combined.index
    close_arrays = {sym: combined[sym].values for sym in combined.columns}
    return idx, close_arrays


def run_rotation_backtest(
    data_map: dict[str, pd.DataFrame],
    params: dict,
    initial_capital: float = 10_000.0,
    rotation_symbols: Optional[list[str]] = None,
    safe_symbol: str = "BIL",
    spy_symbol: str = "SPY",
    strategy_module=None,
) -> Optional[SymbolResult]:
    _bt_start = time.perf_counter()
    if strategy_module is not None:
        compute_indicators = strategy_module.compute_indicators
        score_asset = strategy_module.score_asset
    else:
        from strategies.omniscient_paradox import compute_indicators, score_asset

    if rotation_symbols is None:
        from strategies.omniscient_paradox import ROTATION_SYMBOLS
        rotation_symbols = ROTATION_SYMBOLS

    idx, close_arrays = _align_data(data_map)
    if len(idx) < 70:
        return None

    risk_symbols = [s for s in rotation_symbols if s != safe_symbol and s in close_arrays]
    if not risk_symbols:
        return None
    has_safe = safe_symbol in close_arrays
    has_spy = spy_symbol in close_arrays

    # Precompute indicators for each risk symbol
    _ind_start = time.perf_counter()
    indicators = {}
    for sym in risk_symbols:
        indicators[sym] = compute_indicators(close_arrays[sym], sym, params)
    # Also compute for safe symbol (ML strategies may need benchmark data)
    if has_safe and safe_symbol not in risk_symbols:
        indicators[safe_symbol] = compute_indicators(close_arrays[safe_symbol], safe_symbol, params)
    _ind_end = time.perf_counter()
    _plog(f"compute_indicators: {_ind_end-_ind_start:.3f}s "
          f"for {len(risk_symbols)} symbols n_bars={len(idx)}")

    # SPY SMA200 for market regime
    spy_sma_period = int(params.get("spy_sma_period", 200))
    if has_spy:
        spy_close = close_arrays[spy_symbol]
        spy_sma = pd.Series(spy_close).rolling(spy_sma_period).mean().values
    else:
        spy_sma = np.full(len(idx), np.nan)
        spy_close = np.ones(len(idx))

    confidence_threshold = float(params.get("confidence_threshold", 0.10))
    target_vol_param = float(params.get("target_vol", 0.80))
    lookback_vol = int(params.get("lookback_vol", 20))

    # Portfolio state
    n = len(idx)
    equity_curve = np.full(n, initial_capital)
    timestamps = []
    for t in idx:
        try:
            ts = int(pd.Timestamp(t).timestamp())
        except Exception:
            ts = 0
        timestamps.append(ts)

    cash = initial_capital
    asset_shares = 0.0
    safe_shares = 0.0
    current_asset: Optional[str] = None  # symbol of current holding
    current_asset_weight = 0.0
    trades: list[TradeRecord] = []

    taker_fee = 0.001
    prev_equity = initial_capital
    entry_time = 0
    entry_price_held = 0.0
    entry_bar = 0

    def _get_close(sym: str, i: int) -> float:
        arr = close_arrays.get(sym)
        if arr is None or i >= len(arr):
            return 0.0
        v = arr[i]
        return float(v) if not np.isnan(v) else 0.0

    def _vol_weight(sym: str, i: int) -> float:
        arr = close_arrays.get(sym)
        if arr is None:
            return 1.0
        start = max(0, i - lookback_vol)
        segment = arr[start:i]
        if len(segment) < 2:
            return 1.0
        rets = np.diff(segment) / np.maximum(segment[:-1], 1e-8)
        curr_vol = float(np.std(rets) * np.sqrt(252))
        if curr_vol < 1e-8:
            return 1.0
        return min(1.0, target_vol_param / curr_vol)

    for i in range(n):
        # Mark-to-market equity
        if current_asset is not None and current_asset != safe_symbol:
            px = _get_close(current_asset, i)
            safe_px = _get_close(safe_symbol, i) if has_safe else 1.0
            equity_curve[i] = (cash
                                + asset_shares * px
                                + safe_shares * safe_px)
        elif current_asset == safe_symbol:
            safe_px = _get_close(safe_symbol, i) if has_safe else 1.0
            equity_curve[i] = cash + safe_shares * safe_px
        else:
            equity_curve[i] = cash

        # Daily rebalance: compute scores
        spy_trend = True
        if has_spy and not np.isnan(spy_sma[i]):
            spy_trend = spy_close[i] > spy_sma[i]

        scores: dict[str, float] = {}
        for sym in risk_symbols:
            px = _get_close(sym, i)
            if px <= 0:
                continue
            sc = score_asset(indicators[sym], sym, px, i, params)
            if not np.isnan(sc):
                scores[sym] = sc

        if not scores:
            continue

        best_sym = max(scores, key=lambda s: scores[s])
        best_score = scores[best_sym]

        # Determine target asset
        target_asset = current_asset

        if current_asset is None:
            target_asset = best_sym if best_score > 0 else safe_symbol
        elif current_asset == safe_symbol:
            if best_score > 0.02:
                target_asset = best_sym
        else:
            current_score = scores.get(current_asset, -999.0)
            if best_score > current_score * (1 + confidence_threshold):
                target_asset = best_sym
            elif current_score < -0.02:
                target_asset = safe_symbol

        # SPY bearish override
        if not spy_trend and target_asset != safe_symbol:
            uup_score = scores.get("UUP", -999.0)
            target_score = scores.get(target_asset, -999.0)
            if uup_score > 0 and uup_score > target_score and "UUP" in close_arrays:
                target_asset = "UUP"
            elif target_score < 0:
                target_asset = safe_symbol

        # Volatility-targeted weight
        if target_asset and target_asset != safe_symbol:
            target_weight = _vol_weight(target_asset, i)
        elif target_asset == safe_symbol:
            target_weight = 1.0
        else:
            target_weight = 0.0

        # Execute rotation if target changed or weight drifted significantly
        if target_asset != current_asset:
            # Close current position
            if current_asset is not None:
                if current_asset != safe_symbol:
                    exit_px = _get_close(current_asset, i)
                    if exit_px > 0 and asset_shares > 0:
                        proceeds = asset_shares * exit_px
                        fee = proceeds * taker_fee
                        cash += proceeds - fee
                        pnl = proceeds - fee - asset_shares * entry_price_held
                        pnl_pct = pnl / (asset_shares * entry_price_held) * 100 if entry_price_held > 0 else 0.0
                        trades.append(TradeRecord(
                            symbol=current_asset,
                            entry_time=entry_time,
                            exit_time=timestamps[i],
                            entry_bar=entry_bar,
                            exit_bar=i,
                            entry_price=entry_price_held,
                            exit_price=exit_px,
                            quantity=asset_shares,
                            pnl=round(pnl, 2),
                            pnl_pct=round(pnl_pct, 4),
                            direction=1,
                        ))
                        asset_shares = 0.0
                else:
                    if has_safe:
                        safe_px = _get_close(safe_symbol, i)
                        if safe_px > 0 and safe_shares > 0:
                            cash += safe_shares * safe_px * (1 - taker_fee)
                            safe_shares = 0.0

            # Open new position
            if target_asset and target_asset != safe_symbol:
                entry_px = _get_close(target_asset, i)
                if entry_px > 0:
                    alloc = cash * target_weight
                    fee = alloc * taker_fee
                    net_alloc = alloc - fee
                    asset_shares = net_alloc / entry_px
                    cash -= alloc
                    entry_price_held = entry_px
                    entry_time = timestamps[i]
                    entry_bar = i
                    current_asset_weight = target_weight

                    # Put remainder in safe asset
                    rem = 1.0 - target_weight
                    if rem > 0.1 and has_safe:
                        safe_px = _get_close(safe_symbol, i)
                        if safe_px > 0:
                            safe_alloc = cash * (rem / (1.0 - target_weight + 1e-8))
                            safe_alloc = min(safe_alloc, cash)
                            fee_s = safe_alloc * taker_fee
                            safe_shares = (safe_alloc - fee_s) / safe_px
                            cash -= safe_alloc

            elif target_asset == safe_symbol:
                if has_safe:
                    safe_px = _get_close(safe_symbol, i)
                    if safe_px > 0:
                        fee = cash * taker_fee
                        safe_shares = (cash - fee) / safe_px
                        entry_price_held = safe_px
                        entry_time = timestamps[i]
                        entry_bar = i
                        cash = 0.0
                else:
                    entry_time = timestamps[i]
                    entry_bar = i

            current_asset = target_asset

        # Recompute equity after trade
        if current_asset and current_asset != safe_symbol:
            px = _get_close(current_asset, i)
            safe_px = _get_close(safe_symbol, i) if has_safe else 1.0
            equity_curve[i] = cash + asset_shares * px + safe_shares * safe_px
        elif current_asset == safe_symbol:
            safe_px = _get_close(safe_symbol, i) if has_safe else 1.0
            equity_curve[i] = cash + safe_shares * safe_px
        else:
            equity_curve[i] = cash

    _loop_end = time.perf_counter()
    _plog(f"rotation loop: {_loop_end-_ind_end:.2f}s "
          f"for {n} bars x {len(risk_symbols)} syms, "
          f"trades={len(trades)}")

    equity_list = [float(v) for v in equity_curve]
    metrics = compute_metrics(equity_list, trades, n, bars_per_year=252)

    _bt_end = time.perf_counter()
    _plog(f"rotation total: {_bt_end-_bt_start:.2f}s")

    return SymbolResult(
        symbol="ROTATION_PORTFOLIO",
        total_return=metrics["total_return"],
        annualized_return=metrics["annualized_return"],
        sharpe_ratio=metrics["sharpe_ratio"],
        sortino_ratio=metrics["sortino_ratio"],
        calmar_ratio=metrics["calmar_ratio"],
        max_drawdown=metrics["max_drawdown"],
        win_rate=metrics["win_rate"],
        profit_factor=metrics["profit_factor"],
        trade_count=metrics["trade_count"],
        equity_curve=equity_list,
        equity_timestamps=timestamps,
        trades=trades,
        avg_daily_volume=0.0,
    )
