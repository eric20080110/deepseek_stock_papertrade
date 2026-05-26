import numpy as np
import pandas as pd

IS_ROTATION = True
ROTATION_SYMBOLS = ["AMD", "TSLA", "AMZN", "AAPL", "SPXL"]
SAFE_SYMBOL = "SPY"
SPY_SYMBOL = "SPY"


def generate_signals(ohlcv: pd.DataFrame, params: dict) -> pd.Series:
    """Stub — rotation strategies use run_rotation_backtest, not per-symbol signals."""
    return pd.Series(np.zeros(len(ohlcv), dtype=int), index=ohlcv.index)


def compute_indicators(close_arr: np.ndarray, params: dict) -> dict:
    lb1 = int(params.get("lookback_1m", 21))
    lb3 = int(params.get("lookback_3m", 63))
    lb6 = int(params.get("lookback_6m", 126))
    s = pd.Series(close_arr)

    def _ret(lb: int) -> np.ndarray:
        shifted = s.shift(lb)
        return ((s - shifted) / shifted.abs().clip(lower=1e-8) * 100).values

    return {
        "ret_1m": _ret(lb1),
        "ret_3m": _ret(lb3),
        "ret_6m": _ret(lb6),
    }


def score_asset(ind: dict, close: float, i: int, params: dict) -> float:
    r1 = ind["ret_1m"][i]
    r3 = ind["ret_3m"][i]
    r6 = ind["ret_6m"][i]
    if any(np.isnan(v) for v in (r1, r3, r6)):
        return float("nan")
    w1 = float(params.get("weight_1m", 1.0))
    w3 = float(params.get("weight_3m", 1.0))
    w6 = float(params.get("weight_6m", 1.0))
    return r1 * w1 + r3 * w3 + r6 * w6
