import pandas as pd
import numpy as np


def generate_signals(ohlcv: pd.DataFrame, params: dict) -> pd.Series:
    bb_period = int(params["bb_period"])
    bb_std = float(params["bb_std"])
    use_squeeze = params.get("use_squeeze_filter", True)
    squeeze_period = int(params.get("squeeze_period", 20))
    squeeze_threshold = float(params.get("squeeze_threshold", 0.6))
    exit_mode = params.get("exit_mode", "midline")
    sl_pct = float(params.get("stop_loss_pct", 0.05))
    tp_pct = float(params.get("take_profit_pct", 0.1))
    midline_buffer = float(params.get("midline_exit_buffer", 0.005))
    close = ohlcv["close"]
    sma = close.rolling(window=bb_period).mean()
    std = close.rolling(window=bb_period).std()
    upper, lower = sma + bb_std * std, sma - bb_std * std
    bandwidth = (upper - lower) / sma
    avg_bandwidth = bandwidth.rolling(window=squeeze_period).mean()
    squeeze_active = bandwidth < avg_bandwidth * squeeze_threshold
    signals = pd.Series(0, index=ohlcv.index, dtype=int)
    in_pos, entry = 0, 0.0
    for i in range(1, len(ohlcv)):
        if np.isnan(upper.iloc[i]) or np.isnan(lower.iloc[i]): continue
        if use_squeeze and not squeeze_active.iloc[i]: continue
        if in_pos == 0:
            if close.iloc[i] > upper.iloc[i-1]: signals.iloc[i] = 1; in_pos = 1; entry = close.iloc[i]
            elif close.iloc[i] < lower.iloc[i-1]: signals.iloc[i] = -1; in_pos = -1; entry = close.iloc[i]
        elif in_pos == 1:
            if exit_mode == "midline":
                if close.iloc[i] <= sma.iloc[i] * (1 + midline_buffer): signals.iloc[i] = -1; in_pos = 0
            else:
                ret = (close.iloc[i] - entry) / entry
                if ret <= -sl_pct or ret >= tp_pct: signals.iloc[i] = -1; in_pos = 0
        elif in_pos == -1:
            if exit_mode == "midline":
                if close.iloc[i] >= sma.iloc[i] * (1 - midline_buffer): signals.iloc[i] = 1; in_pos = 0
            else:
                ret = (entry - close.iloc[i]) / entry
                if ret <= -sl_pct or ret >= tp_pct: signals.iloc[i] = 1; in_pos = 0
    return signals
