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

    if ma_type == "EMA":
        fast_ma = close.ewm(span=fast_p, adjust=False).mean().values
        slow_ma = close.ewm(span=slow_p, adjust=False).mean().values
    else:
        fast_ma = close.rolling(window=fast_p).mean().values
        slow_ma = close.rolling(window=slow_p).mean().values

    n = len(ohlcv)
    d = fast_ma - slow_ma
    prev_d = np.empty_like(d)
    prev_d[0] = 0.0
    prev_d[1:] = d[:-1]

    valid = ~np.isnan(d) & ~np.isnan(prev_d)
    long_cross = valid & (prev_d <= 0) & (d > 0)
    short_cross = valid & (prev_d >= 0) & (d < 0)
    long_cross[0] = False
    short_cross[0] = False

    if use_vf:
        vol = ohlcv.get("volume", pd.Series(0.0, index=ohlcv.index)).values
        vol_ma = pd.Series(vol).rolling(window=vol_period).mean().values
        vol_ok = (vol > vol_ma * vol_threshold) & ~np.isnan(vol_ma)
        long_cross &= vol_ok

    sig = np.zeros(n, dtype=np.int8)
    sig[long_cross] = 1
    sig[short_cross] = -1
    return pd.Series(sig.astype(int), index=ohlcv.index)
