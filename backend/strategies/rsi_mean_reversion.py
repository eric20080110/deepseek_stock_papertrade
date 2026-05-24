import pandas as pd
import numpy as np
from numba import njit


@njit(cache=True)
def _compute_signals(rsi, n, oversold, overbought, confirm_bars, tp_rsi):
    sig = np.zeros(n, dtype=np.int8)
    cross_under_count = 0
    cross_over_count = 0
    for i in range(1, n):
        if np.isnan(rsi[i]):
            continue
        prev_rsi = rsi[i - 1]
        curr_rsi = rsi[i]

        if prev_rsi > oversold and curr_rsi <= oversold:
            cross_under_count = 1
        elif curr_rsi <= oversold:
            cross_under_count += 1
        else:
            cross_under_count = 0

        if prev_rsi < overbought and curr_rsi >= overbought:
            cross_over_count = 1
        elif curr_rsi >= overbought:
            cross_over_count += 1
        else:
            cross_over_count = 0

        if cross_under_count >= confirm_bars:
            sig[i] = 1
        elif cross_over_count >= confirm_bars:
            sig[i] = -1

        if curr_rsi >= tp_rsi and sig[i] == 0:
            sig[i] = -1

    return sig


def generate_signals(ohlcv: pd.DataFrame, params: dict) -> pd.Series:
    rsi_period = int(params["rsi_period"])
    oversold = float(params["oversold_threshold"])
    overbought = float(params["overbought_threshold"])
    confirm_bars = int(params.get("confirmation_bars", 1))
    tp_rsi = float(params.get("take_profit_rsi", 50))

    close = ohlcv["close"]
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(window=rsi_period).mean()
    loss = (-delta.clip(upper=0)).rolling(window=rsi_period).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi = (100.0 - (100.0 / (1.0 + rs))).values.astype(np.float64)

    sig = _compute_signals(rsi, len(rsi), oversold, overbought, confirm_bars, tp_rsi)
    return pd.Series(sig.astype(int), index=ohlcv.index)
