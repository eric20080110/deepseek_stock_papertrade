import pandas as pd
import numpy as np
from numba import njit


@njit(cache=True)
def _compute_signals(macd_line, signal_line, histogram, close, trend_ma,
                     use_trend_filter, require_macd_pos, hist_confirm, n):
    sig = np.zeros(n, dtype=np.int8)
    hist_same_count = 0
    for i in range(1, n):
        if np.isnan(macd_line[i]) or np.isnan(signal_line[i]):
            hist_same_count = 0
            continue

        h = histogram[i]
        h_prev = histogram[i - 1]
        if h > 0.0:
            hist_same_count = hist_same_count + 1 if h_prev > 0.0 else 1
        elif h < 0.0:
            hist_same_count = hist_same_count + 1 if h_prev < 0.0 else -1
        else:
            hist_same_count = 0

        prev_macd = macd_line[i - 1]
        curr_macd = macd_line[i]
        curr_sig = signal_line[i]

        long_cond = prev_macd <= curr_sig and curr_macd > curr_sig
        short_cond = prev_macd >= curr_sig and curr_macd < curr_sig

        if require_macd_pos:
            long_cond = long_cond and curr_macd > 0.0
            short_cond = short_cond and curr_macd < 0.0

        if use_trend_filter and not np.isnan(trend_ma[i]):
            long_cond = long_cond and close[i] > trend_ma[i]
            short_cond = short_cond and close[i] < trend_ma[i]

        if long_cond and abs(hist_same_count) >= hist_confirm:
            sig[i] = 1
        elif short_cond and abs(hist_same_count) >= hist_confirm:
            sig[i] = -1

    return sig


def generate_signals(ohlcv: pd.DataFrame, params: dict) -> pd.Series:
    fast_ema_p = int(params["fast_ema"])
    slow_ema_p = int(params["slow_ema"])
    signal_p = int(params["signal_period"])
    hist_confirm = int(params.get("histogram_confirm_bars", 1))
    require_macd_pos = bool(params.get("require_macd_positive", True))
    use_tf = bool(params.get("use_trend_filter", False))
    tf_period = int(params.get("trend_ma_period", 100))
    tf_type = params.get("trend_ma_type", "SMA")

    close = ohlcv["close"]
    fast_ema = close.ewm(span=fast_ema_p, adjust=False).mean()
    slow_ema = close.ewm(span=slow_ema_p, adjust=False).mean()
    macd_line = (fast_ema - slow_ema).values.astype(np.float64)
    signal_line = pd.Series(macd_line).ewm(span=signal_p, adjust=False).mean().values.astype(np.float64)
    histogram = macd_line - signal_line

    close_v = close.values.astype(np.float64)
    if use_tf:
        if tf_type == "EMA":
            trend_ma = close.ewm(span=tf_period, adjust=False).mean().values.astype(np.float64)
        else:
            trend_ma = close.rolling(window=tf_period).mean().values.astype(np.float64)
    else:
        trend_ma = np.full(len(close), np.nan)

    sig = _compute_signals(
        macd_line, signal_line, histogram, close_v, trend_ma,
        use_tf, require_macd_pos, hist_confirm, len(close),
    )
    return pd.Series(sig.astype(int), index=ohlcv.index)
