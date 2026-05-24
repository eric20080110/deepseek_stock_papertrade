import pandas as pd
import numpy as np
from numba import njit


@njit(cache=True)
def _compute_signals(close, upper, lower, sma, squeeze_active, use_squeeze,
                     exit_mode_midline, sl_pct, tp_pct, midline_buffer, n):
    sig = np.zeros(n, dtype=np.int8)
    in_position = 0
    entry_price = 0.0
    for i in range(1, n):
        if np.isnan(upper[i]) or np.isnan(lower[i]):
            continue
        if use_squeeze and not squeeze_active[i]:
            continue

        if in_position == 0:
            if close[i] > upper[i - 1]:
                sig[i] = 1
                in_position = 1
                entry_price = close[i]
            elif close[i] < lower[i - 1]:
                sig[i] = -1
                in_position = -1
                entry_price = close[i]
        elif in_position == 1:
            if exit_mode_midline:
                if close[i] <= sma[i] * (1.0 + midline_buffer):
                    sig[i] = -1
                    in_position = 0
            else:
                ret = (close[i] - entry_price) / entry_price
                if ret <= -sl_pct or ret >= tp_pct:
                    sig[i] = -1
                    in_position = 0
        elif in_position == -1:
            if exit_mode_midline:
                if close[i] >= sma[i] * (1.0 - midline_buffer):
                    sig[i] = 1
                    in_position = 0
            else:
                ret = (entry_price - close[i]) / entry_price
                if ret <= -sl_pct or ret >= tp_pct:
                    sig[i] = 1
                    in_position = 0
    return sig


def generate_signals(ohlcv: pd.DataFrame, params: dict) -> pd.Series:
    bb_period = int(params["bb_period"])
    bb_std = float(params["bb_std"])
    use_squeeze = bool(params.get("use_squeeze_filter", True))
    squeeze_period = int(params.get("squeeze_period", 20))
    squeeze_threshold = float(params.get("squeeze_threshold", 0.6))
    exit_mode = params.get("exit_mode", "midline")
    sl_pct = float(params.get("stop_loss_pct", 0.05))
    tp_pct = float(params.get("take_profit_pct", 0.1))
    midline_buffer = float(params.get("midline_exit_buffer", 0.005))

    close = ohlcv["close"]
    sma = close.rolling(window=bb_period).mean()
    std = close.rolling(window=bb_period).std()
    upper = sma + bb_std * std
    lower = sma - bb_std * std
    bandwidth = (upper - lower) / sma
    avg_bandwidth = bandwidth.rolling(window=squeeze_period).mean()
    squeeze_active = (bandwidth < avg_bandwidth * squeeze_threshold).values

    sig = _compute_signals(
        close.values.astype(np.float64),
        upper.values.astype(np.float64),
        lower.values.astype(np.float64),
        sma.values.astype(np.float64),
        squeeze_active,
        use_squeeze,
        exit_mode == "midline",
        sl_pct,
        tp_pct,
        midline_buffer,
        len(close),
    )
    return pd.Series(sig.astype(int), index=ohlcv.index)
