import pandas as pd
import numpy as np


def generate_signals(ohlcv: pd.DataFrame, params: dict) -> pd.Series:
    fast_ema_p = int(params["fast_ema"])
    slow_ema_p = int(params["slow_ema"])
    signal_p = int(params["signal_period"])
    hist_confirm = int(params.get("histogram_confirm_bars", 1))
    require_macd_pos = params.get("require_macd_positive", True)
    use_tf = params.get("use_trend_filter", False)
    tf_period = int(params.get("trend_ma_period", 100))
    tf_type = params.get("trend_ma_type", "SMA")
    close = ohlcv["close"]
    fast_ema = close.ewm(span=fast_ema_p, adjust=False).mean()
    slow_ema = close.ewm(span=slow_ema_p, adjust=False).mean()
    macd_line = fast_ema - slow_ema
    signal_line = macd_line.ewm(span=signal_p, adjust=False).mean()
    histogram = macd_line - signal_line
    if use_tf:
        trend_ma = close.ewm(span=tf_period, adjust=False).mean() if tf_type == "EMA" else close.rolling(window=tf_period).mean()
    signals = pd.Series(0, index=ohlcv.index, dtype=int)
    hist_count = 0
    for i in range(1, len(ohlcv)):
        if np.isnan(macd_line.iloc[i]) or np.isnan(signal_line.iloc[i]): continue
        pm, cm, cs = macd_line.iloc[i-1], macd_line.iloc[i], signal_line.iloc[i]
        hist_count = hist_count + 1 if histogram.iloc[i] > 0 and histogram.iloc[i-1] > 0 else (hist_count + 1 if histogram.iloc[i] < 0 and histogram.iloc[i-1] < 0 else (1 if histogram.iloc[i] > 0 else (-1 if histogram.iloc[i] < 0 else 0)))
        long_cond = pm <= cs and cm > cs
        short_cond = pm >= cs and cm < cs
        if require_macd_pos: long_cond = long_cond and cm > 0; short_cond = short_cond and cm < 0
        if use_tf and not np.isnan(trend_ma.iloc[i]):
            long_cond = long_cond and close.iloc[i] > trend_ma.iloc[i]
            short_cond = short_cond and close.iloc[i] < trend_ma.iloc[i]
        if long_cond and abs(hist_count) >= hist_confirm: signals.iloc[i] = 1
        elif short_cond and abs(hist_count) >= hist_confirm: signals.iloc[i] = -1
    return signals
