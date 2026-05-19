import json
import time
import random
import requests
import pandas as pd
from collections import deque
from typing import Optional

BINANCE_BASE = "https://fapi.binance.com"


class RateLimitManager:
    def __init__(self, max_weight_10s: int = 200, max_weight_1m: int = 2000):
        self._weight_10s: deque[tuple[float, int]] = deque()
        self._weight_1m: deque[tuple[float, int]] = deque()
        self._max_weight_10s = max_weight_10s
        self._max_weight_1m = max_weight_1m
        self._consecutive_429 = 0
        self._circuit_open_until = 0.0
        self._circuit_breaker_sec = 60.0

    def _prune(self):
        now = time.time()
        while self._weight_10s and self._weight_10s[0][0] < now - 10:
            self._weight_10s.popleft()
        while self._weight_1m and self._weight_1m[0][0] < now - 60:
            self._weight_1m.popleft()

    def _current_weight(self) -> tuple[int, int]:
        self._prune()
        w10 = sum(w for _, w in self._weight_10s)
        w1m = sum(w for _, w in self._weight_1m)
        return w10, w1m

    def wait_if_needed(self):
        now = time.time()
        if now < self._circuit_open_until:
            sleep = self._circuit_open_until - now
            time.sleep(sleep)
            return
        w10, w1m = self._current_weight()
        if w10 >= self._max_weight_10s:
            time.sleep(1.0 + random.random())
        if w1m >= self._max_weight_1m:
            time.sleep(5.0 + random.random() * 3)

    def record_request(self, weight: int = 1):
        now = time.time()
        self._weight_10s.append((now, weight))
        self._weight_1m.append((now, weight))

    def handle_429(self, retry_after: Optional[str] = None):
        self._consecutive_429 += 1
        if self._consecutive_429 >= 3:
            self._circuit_open_until = time.time() + self._circuit_breaker_sec
            self._consecutive_429 = 0
            time.sleep(self._circuit_breaker_sec)
            return
        delay = 5 * (2 ** (self._consecutive_429 - 1))
        if retry_after:
            try:
                delay = max(delay, int(retry_after))
            except ValueError:
                pass
        jitter = random.uniform(0, 1)
        time.sleep(min(delay + jitter, 120))

    def reset(self):
        self._consecutive_429 = 0

    def on_success(self):
        self._consecutive_429 = 0


_RATE_LIMITER = RateLimitManager()
_REQ_SLEEP = 0.1


def _symbol_binance(symbol: str) -> str:
    return symbol.replace("/", "")


def _get_weight(r: requests.Response) -> int:
    # Return fixed per-request weight for klines (limit=1500 costs ~10 on FAPI).
    # X-MBX-USED-WEIGHT-1m is cumulative for the minute, NOT per-request cost —
    # using it directly inflates the deque and causes excessive rate-limit sleeps.
    return 10


def _fetch_klines(
    symbol: str, timeframe: str, start_ms: int, end_ms: int
) -> Optional[pd.DataFrame]:
    bsym = _symbol_binance(symbol)
    rows = []
    cur = start_ms
    max_retries = 5

    while cur < end_ms:
        _RATE_LIMITER.wait_if_needed()
        for attempt in range(max_retries):
            try:
                r = requests.get(
                    f"{BINANCE_BASE}/fapi/v1/klines",
                    params={
                        "symbol": bsym,
                        "interval": timeframe,
                        "startTime": cur,
                        "endTime": end_ms,
                        "limit": 1500,
                    },
                    timeout=30,
                )
                _RATE_LIMITER.record_request(_get_weight(r))
                if r.status_code == 429:
                    _RATE_LIMITER.handle_429(r.headers.get("Retry-After"))
                    continue
                r.raise_for_status()
                _RATE_LIMITER.on_success()
                klines = r.json()
                break
            except requests.RequestException:
                if attempt == max_retries - 1:
                    return None
                time.sleep(2 ** attempt + random.random())
                continue
        else:
            return None

        if not klines:
            break
        for k in klines:
            rows.append(
                {
                    "timestamp": k[0] // 1000,
                    "open": float(k[1]),
                    "high": float(k[2]),
                    "low": float(k[3]),
                    "close": float(k[4]),
                    "volume": float(k[5]),
                }
            )
        cur = klines[-1][0] + 1
        time.sleep(_REQ_SLEEP)

    if not rows:
        return None
    df = pd.DataFrame(rows).drop_duplicates(subset="timestamp").sort_values("timestamp")
    df.set_index("timestamp", inplace=True)
    return df


def _load_sqlite(symbol: str, timeframe: str, start_ts: int, end_ts: int) -> Optional[pd.DataFrame]:
    from database import get_db
    conn = get_db()
    rows = conn.execute(
        """SELECT timestamp, open, high, low, close, volume
           FROM ohlcv_data
           WHERE symbol = ? AND timeframe = ? AND timestamp >= ? AND timestamp <= ?
           ORDER BY timestamp""",
        (symbol, timeframe, start_ts, end_ts),
    ).fetchall()
    conn.close()
    if not rows:
        return None
    records = [dict(r) for r in rows]
    df = pd.DataFrame(records).set_index("timestamp")
    return df


def _save_sqlite(df: pd.DataFrame, symbol: str, timeframe: str):
    from database import get_db
    conn = get_db()
    rows = []
    for ts, row in df.iterrows():
        rows.append(
            (
                symbol,
                timeframe,
                int(ts),
                float(row.get("open", 0)),
                float(row.get("high", 0)),
                float(row.get("low", 0)),
                float(row.get("close", 0)),
                float(row.get("volume", 0)),
            )
        )
    conn.executemany(
        """INSERT OR REPLACE INTO ohlcv_data
           (symbol, timeframe, timestamp, open, high, low, close, volume)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        rows,
    )
    conn.commit()
    conn.close()


_BAR_SECONDS = {"1d": 86400, "1h": 3600, "30m": 1800, "15m": 900, "5m": 300, "1m": 60}

_MAX_AGE_SECONDS: dict[str, int] = {
    "1m": 120,
    "5m": 600,
    "15m": 1800,
    "30m": 3600,
    "1h": 7200,
    "1d": 86400,
}


def _min_span(timeframe: str) -> int:
    bar_s = _BAR_SECONDS.get(timeframe, 3600)
    return bar_s * 600


def date_range(
    timeframe: str, start_date: str = "", end_date: str = ""
) -> tuple[int, int]:
    now = int(time.time())
    min_s = _min_span(timeframe)

    if end_date:
        end_ts = int(pd.Timestamp(end_date).timestamp())
    else:
        end_ts = now

    if start_date:
        start_ts = int(pd.Timestamp(start_date).timestamp())
    else:
        start_ts = end_ts - min_s

    return start_ts, end_ts


def fetch_ohlcv(
    symbol: str,
    timeframe: str = "1h",
    start_date: str = "",
    end_date: str = "",
) -> Optional[pd.DataFrame]:
    start_ts, end_ts = date_range(timeframe, start_date, end_date)
    bar_s = _BAR_SECONDS.get(timeframe, 3600)
    one_bar = bar_s
    max_age = _MAX_AGE_SECONDS.get(timeframe, 86400)

    from backtest.parquet_cache import get as pq_get, put as pq_put, stale as pq_stale

    # 1. Try parquet cache
    if not pq_stale(symbol, timeframe, max_age):
        df = pq_get(symbol, timeframe, start_ts, end_ts)
        if df is not None:
            requested_span = end_ts - start_ts
            actual_span = int(df.index[-1]) - int(df.index[0]) if len(df) > 1 else 0
            if requested_span <= one_bar or actual_span >= requested_span * 0.8:
                return df
            # Parquet exists but doesn't cover requested range — fall through to re-fetch

    # 2. Try SQLite cache
    cached = _load_sqlite(symbol, timeframe, start_ts, end_ts)
    if cached is not None:
        coverage = cached.index[-1] - cached.index[0]
        if coverage >= (end_ts - start_ts) * 0.95 and cached.index[-1] >= end_ts - one_bar:
            pq_put(symbol, timeframe, cached)
            return cached

    # 3. Fetch from Binance
    df = _fetch_klines(symbol, timeframe, start_ts * 1000, end_ts * 1000)
    if df is not None:
        _save_sqlite(df, symbol, timeframe)
        pq_put(symbol, timeframe, df)
        return _load_sqlite(symbol, timeframe, start_ts, end_ts)
    return cached


def force_refresh(
    symbol: str,
    timeframe: str = "1h",
    start_date: str = "",
    end_date: str = "",
) -> Optional[pd.DataFrame]:
    from backtest.parquet_cache import remove as pq_remove
    pq_remove(symbol, timeframe)
    return fetch_ohlcv(symbol, timeframe, start_date, end_date)
