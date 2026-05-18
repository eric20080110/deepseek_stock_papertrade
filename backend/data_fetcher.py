import json
import time
import requests
import pandas as pd
from typing import Optional

BINANCE_BASE = "https://fapi.binance.com"
_REQ_SLEEP = 0.1


def _symbol_binance(symbol: str) -> str:
    return symbol.replace("/", "")


def _fetch_klines(
    symbol: str, timeframe: str, start_ms: int, end_ms: int
) -> Optional[pd.DataFrame]:
    bsym = _symbol_binance(symbol)
    rows = []
    cur = start_ms
    while cur < end_ms:
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
            if r.status_code == 429:
                time.sleep(5)
                continue
            r.raise_for_status()
            klines = r.json()
        except Exception:
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


def _min_span(timeframe: str) -> int:
    bar_s = _BAR_SECONDS.get(timeframe, 3600)
    return max(bar_s * 200, 30 * 86400)


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
    cached = _load_sqlite(symbol, timeframe, start_ts, end_ts)
    if cached is not None:
        coverage = cached.index[-1] - cached.index[0]
        if coverage >= (end_ts - start_ts) * 0.95 and cached.index[-1] >= end_ts - one_bar:
            return cached

    df = _fetch_klines(symbol, timeframe, start_ts * 1000, end_ts * 1000)
    if df is not None:
        _save_sqlite(df, symbol, timeframe)
        return _load_sqlite(symbol, timeframe, start_ts, end_ts)
    return cached
