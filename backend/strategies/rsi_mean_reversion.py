import pandas as pd
import numpy as np


def generate_signals(ohlcv: pd.DataFrame, params: dict) -> pd.Series:
    rsi_period = int(params["rsi_period"])
    oversold = int(params["oversold_threshold"])
    overbought = int(params["overbought_threshold"])
    confirm_bars = int(params.get("confirmation_bars", 1))
    sl_mode = params.get("stop_loss_mode", "fixed_pct")
    sl_pct = float(params.get("stop_loss_pct", 0.03))
    atr_period = int(params.get("atr_period", 14))
    atr_mult = float(params.get("atr_multiplier", 2.0))
    tp_rsi = int(params.get("take_profit_rsi", 50))

    close = ohlcv["close"]
    high = ohlcv["high"]
    low = ohlcv["low"]

    delta = close.diff()
    gain = delta.clip(lower=0).rolling(window=rsi_period).mean()
    loss = (-delta.clip(upper=0)).rolling(window=rsi_period).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))

    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low - close.shift()).abs()
    ], axis=1).max(axis=1)
    atr = tr.rolling(window=atr_period).mean()

    signals = pd.Series(0, index=ohlcv.index, dtype=int)
    cross_under_count = 0
    cross_over_count = 0

    for i in range(1, len(ohlcv)):
        if np.isnan(rsi.iloc[i]):
            continue
        prev_rsi = rsi.iloc[i - 1]
        curr_rsi = rsi.iloc[i]

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
            signals.iloc[i] = 1
        elif cross_over_count >= confirm_bars:
            signals.iloc[i] = -1

        if curr_rsi >= tp_rsi and signals.iloc[i] == 0:
            signals.iloc[i] = -1

    return signals
