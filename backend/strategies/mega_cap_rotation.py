import time
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler
from profile_helper import log as _plog

IS_ROTATION = True
ROTATION_SYMBOLS = ["AAPL", "AMZN", "GOOGL", "META", "MSFT", "NVDA", "TSLA", "AMD"]
SAFE_SYMBOL = "QQQ"
SPY_SYMBOL = "QQQ"

_close_cache: dict[str, np.ndarray] = {}
_model: RandomForestClassifier | None = None
_scaler: StandardScaler | None = None
_trained: bool = False
_qqq_ret_10d: np.ndarray | None = None


_train_count: int = 0
_train_total_s: float = 0.0

def _train_model(params: dict | None = None) -> bool:
    global _model, _scaler, _trained, _train_count, _train_total_s

    needed = set(ROTATION_SYMBOLS) | {SAFE_SYMBOL}
    have = set(_close_cache.keys())
    if not needed.issubset(have):
        return False

    n_est = int((params or {}).get("n_estimators", 100))
    max_d = int((params or {}).get("max_depth", 4))

    _t0 = time.perf_counter()
    qqq = _close_cache[SAFE_SYMBOL]
    features, labels = [], []

    for sym in ROTATION_SYMBOLS:
        arr = _close_cache[sym]
        n = min(len(arr), len(qqq))
        if n < 15:
            continue
        s = pd.Series(arr[:n])
        b = pd.Series(qqq[:n])
        ret_10d = s.pct_change(10)
        q_ret_10d = b.pct_change(10)

        for i in range(10, n - 5):
            r10 = ret_10d.iloc[i]
            a10 = r10 - q_ret_10d.iloc[i]
            if np.isnan(r10) or np.isnan(a10):
                continue
            fut_s = arr[i + 5] / arr[i] - 1 if arr[i] > 0 else 0
            fut_q = qqq[i + 5] / qqq[i] - 1 if qqq[i] > 0 else 0
            features.append([r10, a10])
            labels.append(1 if fut_s > fut_q else 0)

    if len(features) < 50:
        return False

    _scaler = StandardScaler()
    _model = RandomForestClassifier(n_estimators=n_est, max_depth=max_d, random_state=42)
    _model.fit(_scaler.fit_transform(features), labels)
    _trained = True
    _elapsed = time.perf_counter() - _t0
    _train_count += 1
    _train_total_s += _elapsed
    _plog(f"RF train #{_train_count}: {_elapsed:.2f}s "
          f"n_est={n_est} max_d={max_d} samples={len(features)}")
    return True


def generate_signals(ohlcv: pd.DataFrame, params: dict) -> pd.Series:
    return pd.Series(np.zeros(len(ohlcv), dtype=int), index=ohlcv.index)


def compute_indicators(close_arr: np.ndarray, symbol: str, params: dict) -> dict:
    _close_cache[symbol] = close_arr

    ret_10d = np.full(len(close_arr), np.nan)
    if len(close_arr) >= 11:
        ret_10d = pd.Series(close_arr).pct_change(10).values

    global _qqq_ret_10d
    if symbol == SAFE_SYMBOL:
        _qqq_ret_10d = ret_10d.copy()

    return {"ret_10d": ret_10d, "close": close_arr}


def batch_predict(indicators: dict, risk_symbols: list[str], safe_symbol: str, params: dict):
    global _model, _scaler, _trained

    if not _trained:
        _train_model(params)
    if _model is None or _scaler is None or not _trained:
        return

    global _qqq_ret_10d
    if _qqq_ret_10d is None:
        return

    n = len(next(iter(indicators.values()))["ret_10d"])
    max_bars = min(n, len(_qqq_ret_10d))

    for sym in risk_symbols:
        ind = indicators[sym]
        ret_10d = ind["ret_10d"]
        active_ret = ret_10d[:max_bars] - _qqq_ret_10d[:max_bars]
        features = np.column_stack([ret_10d[:max_bars], active_ret])

        valid = ~(np.isnan(features[:, 0]) | np.isnan(features[:, 1]))
        probs = np.full(max_bars, np.nan, dtype=np.float64)
        if valid.any():
            probs[valid] = _model.predict_proba(
                _scaler.transform(features[valid])
            )[:, 1]

        ind["probs"] = probs


_score_count: int = 0
_score_total_s: float = 0.0

def score_asset(ind: dict, symbol: str, close: float, i: int, params: dict) -> float:
    probs = ind.get("probs")
    if probs is None or i >= len(probs):
        return float("nan")
    prob = probs[i]
    if np.isnan(prob):
        return float("nan")

    min_confidence = float(params.get("min_confidence", 0.70))
    if prob > min_confidence:
        return (prob - min_confidence) * 100.0
    else:
        return (prob - min_confidence) * 5.0
