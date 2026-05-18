import pandas as pd
import numpy as np


def generate_signals(ohlcv: pd.DataFrame, params: dict) -> pd.Series:
    fast_p = int(params["fast_period"])
    slow_p = int(params["slow_period"])
    ma_type = params.get("ma_type", "SMA")
    use_vf = params.get("use_volume_filter", False)
    vol_period = int(params.get("volume_period", 20))
    vol_threshold = float(params.get("volume_threshold", 1.5))

    close = ohlcv["close"]
    volume = ohlcv.get("volume", pd.Series(index=ohlcv.index, dtype=float))

    if ma_type == "EMA":
        fast_ma = close.ewm(span=fast_p, adjust=False).mean()
        slow_ma = close.ewm(span=slow_p, adjust=False).mean()
    else:
        fast_ma = close.rolling(window=fast_p).mean()
        slow_ma = close.rolling(window=slow_p).mean()

    vol_ma = volume.rolling(window=vol_period).mean() if use_vf else None

    signals = pd.Series(0, index=ohlcv.index, dtype=int)
    for i in range(1, len(ohlcv)):
        if np.isnan(fast_ma.iloc[i]) or np.isnan(slow_ma.iloc[i]):
            continue
        prev_fast = fast_ma.iloc[i - 1]
        prev_slow = slow_ma.iloc[i - 1]
        curr_fast = fast_ma.iloc[i]
        curr_slow = slow_ma.iloc[i]

        if use_vf and vol_ma is not None and vol_ma.iloc[i] > 0:
            vol_ok = volume.iloc[i] > vol_ma.iloc[i] * vol_threshold
        else:
            vol_ok = True

        if prev_fast <= prev_slow and curr_fast > curr_slow and vol_ok:
            signals.iloc[i] = 1
        elif prev_fast >= prev_slow and curr_fast < curr_slow:
            signals.iloc[i] = -1

    return signals
