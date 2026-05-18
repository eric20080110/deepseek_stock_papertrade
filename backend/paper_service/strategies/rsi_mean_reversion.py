import pandas as pd
import numpy as np


def generate_signals(ohlcv: pd.DataFrame, params: dict) -> pd.Series:
    rsi_period = int(params["rsi_period"])
    oversold = int(params["oversold_threshold"])
    overbought = int(params["overbought_threshold"])
    confirm_bars = int(params.get("confirmation_bars", 1))
    tp_rsi = int(params.get("take_profit_rsi", 50))
    close = ohlcv["close"]; high = ohlcv["high"]; low = ohlcv["low"]
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(window=rsi_period).mean()
    loss = (-delta.clip(upper=0)).rolling(window=rsi_period).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    signals = pd.Series(0, index=ohlcv.index, dtype=int)
    cross_under, cross_over = 0, 0
    for i in range(1, len(ohlcv)):
        if np.isnan(rsi.iloc[i]): continue
        pr, cr = rsi.iloc[i-1], rsi.iloc[i]
        cross_under = cross_under + 1 if pr > oversold and cr <= oversold else (cross_under + 1 if cr <= oversold else 0)
        cross_over = cross_over + 1 if pr < overbought and cr >= overbought else (cross_over + 1 if cr >= overbought else 0)
        if cross_under >= confirm_bars: signals.iloc[i] = 1
        elif cross_over >= confirm_bars: signals.iloc[i] = -1
        if cr >= tp_rsi and signals.iloc[i] == 0: signals.iloc[i] = -1
    return signals
