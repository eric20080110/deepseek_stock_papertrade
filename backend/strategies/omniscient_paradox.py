import numpy as np
import pandas as pd

IS_ROTATION = True
ROTATION_SYMBOLS = ["SOXL", "TECL", "TQQQ", "FAS", "ERX", "UUP", "TMF", "BIL"]
SAFE_SYMBOL = "BIL"
SPY_SYMBOL = "SPY"


def generate_signals(ohlcv: pd.DataFrame, params: dict) -> pd.Series:
    """Stub — rotation strategies use run_rotation_backtest, not per-symbol signals."""
    return pd.Series(np.zeros(len(ohlcv), dtype=int), index=ohlcv.index)


def _wilder_rsi(close: np.ndarray, period: int) -> np.ndarray:
    n = len(close)
    rsi = np.full(n, np.nan)
    if n <= period:
        return rsi
    delta = np.diff(close)
    gain = np.maximum(delta, 0.0)
    loss = np.maximum(-delta, 0.0)
    avg_g = float(np.mean(gain[:period]))
    avg_l = float(np.mean(loss[:period]))
    for i in range(period, n - 1):
        avg_g = (avg_g * (period - 1) + gain[i]) / period
        avg_l = (avg_l * (period - 1) + loss[i]) / period
        rs = avg_g / avg_l if avg_l > 1e-12 else 100.0
        rsi[i + 1] = 100.0 - 100.0 / (1.0 + rs)
    return rsi


def compute_indicators(close_arr: np.ndarray, params: dict) -> dict:
    """Compute all indicators for one symbol. Returns dict of numpy arrays."""
    s = pd.Series(close_arr)
    fast_p = int(params.get("roc_fast_period", 9))
    med_p = int(params.get("roc_med_period", 21))
    slow_p = int(params.get("roc_slow_period", 63))
    vol_p = int(params.get("vol_period", 21))
    rsi_p = int(params.get("rsi_period", 14))
    sma_p = int(params.get("sma_period", 50))

    def roc(period):
        shifted = s.shift(period)
        return ((s - shifted) / shifted.abs().clip(lower=1e-8) * 100).values

    return {
        "roc_fast": roc(fast_p),
        "roc_med":  roc(med_p),
        "roc_slow": roc(slow_p),
        "vol":      s.rolling(vol_p).std(ddof=1).values,
        "rsi":      _wilder_rsi(close_arr, rsi_p),
        "sma":      s.rolling(sma_p).mean().values,
    }


def score_asset(ind: dict, close: float, i: int, params: dict) -> float:
    """Return composite score for asset at bar i. Returns nan if indicators not ready."""
    fast = ind["roc_fast"][i]
    med  = ind["roc_med"][i]
    slow = ind["roc_slow"][i]
    vol  = ind["vol"][i]
    rsi  = ind["rsi"][i]
    sma  = ind["sma"][i]

    if any(np.isnan(v) for v in (fast, med, slow, vol, rsi, sma)):
        return float("nan")

    fw = float(params.get("fast_weight", 0.5))
    mw = float(params.get("med_weight", 0.3))
    sw = float(params.get("slow_weight", 0.2))
    weighted_mom = fast * fw + med * mw + slow * sw
    risk_adj = weighted_mom / max(vol, 1e-8)
    trend_score = 1.0 if close > sma else 0.5
    rsi_ob = float(params.get("rsi_overbought", 85))
    rsi_os = float(params.get("rsi_oversold", 30))
    penalty = float(params.get("rsi_penalty", 0.9))
    rsi_factor = penalty if (rsi > rsi_ob or rsi < rsi_os) else 1.0
    return risk_adj * trend_score * rsi_factor
