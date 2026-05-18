import os
import json
import time
import pandas as pd
from typing import Optional

_CACHE_DIR = os.environ.get("OHLCV_CACHE_DIR") or os.path.expanduser("~/.cache/stockcode/ohlcv")


def _ensure_dir():
    os.makedirs(_CACHE_DIR, exist_ok=True)


def _cache_path(symbol: str, timeframe: str) -> str:
    safe = symbol.replace("/", "_").replace(" ", "_")
    return os.path.join(_CACHE_DIR, f"{safe}_{timeframe}.parquet")


def _meta_path(symbol: str, timeframe: str) -> str:
    safe = symbol.replace("/", "_").replace(" ", "_")
    return os.path.join(_CACHE_DIR, f"{safe}_{timeframe}.meta.json")


def _save_meta(symbol: str, timeframe: str, df: pd.DataFrame):
    ts_idx = df.index
    first = int(ts_idx[0]) if hasattr(ts_idx, "dtype") else int(ts_idx[0].timestamp())
    last = int(ts_idx[-1]) if hasattr(ts_idx, "dtype") else int(ts_idx[-1].timestamp())
    meta = {
        "symbol": symbol,
        "timeframe": timeframe,
        "bar_count": len(df),
        "first_ts": first,
        "last_ts": last,
        "fetched_at": int(time.time()),
    }
    with open(_meta_path(symbol, timeframe), "w") as f:
        json.dump(meta, f)


def _load_meta(symbol: str, timeframe: str) -> Optional[dict]:
    try:
        with open(_meta_path(symbol, timeframe)) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def get(
    symbol: str,
    timeframe: str,
    start_ts: Optional[int] = None,
    end_ts: Optional[int] = None,
) -> Optional[pd.DataFrame]:
    path = _cache_path(symbol, timeframe)
    if not os.path.exists(path):
        return None
    try:
        df = pd.read_parquet(path)
        if df.empty:
            return None
    except Exception:
        return None
    if start_ts is not None:
        df = df[df.index >= start_ts]
    if end_ts is not None:
        df = df[df.index <= end_ts]
    return df if not df.empty else None


def put(symbol: str, timeframe: str, df: pd.DataFrame):
    if df is None or df.empty:
        return
    _ensure_dir()
    path = _cache_path(symbol, timeframe)
    df.to_parquet(path, compression="snappy", index=True)
    _save_meta(symbol, timeframe, df)


def has(symbol: str, timeframe: str) -> bool:
    return os.path.exists(_cache_path(symbol, timeframe))


def stale(
    symbol: str,
    timeframe: str,
    max_age_seconds: Optional[int] = None,
) -> bool:
    meta = _load_meta(symbol, timeframe)
    if meta is None:
        return True
    if max_age_seconds is not None:
        if time.time() - meta["fetched_at"] > max_age_seconds:
            return True
    return False


def remove(symbol: str, timeframe: str):
    for p in (_cache_path(symbol, timeframe), _meta_path(symbol, timeframe)):
        if os.path.exists(p):
            os.remove(p)


def clear():
    if os.path.isdir(_CACHE_DIR):
        for f in os.listdir(_CACHE_DIR):
            os.remove(os.path.join(_CACHE_DIR, f))


def set_cache_dir(path: str):
    global _CACHE_DIR
    _CACHE_DIR = path
