import pandas as pd
from typing import Optional

from .parquet_cache import get as pq_get, put as pq_put

_MAX_AGE = {"1m": 120, "5m": 600, "15m": 1800, "30m": 3600, "1h": 7200, "1d": 86400}


class DataCache:
    def __init__(self):
        self._cache: dict[str, pd.DataFrame] = {}
        self._max_bytes = 1 * 1024**3

    def _key(self, symbol: str, timeframe: Optional[str] = None) -> str:
        return f"{symbol}|{timeframe}" if timeframe else symbol

    def load(self, symbol: str, timeframe: Optional[str] = None) -> Optional[pd.DataFrame]:
        return self._cache.get(self._key(symbol, timeframe))

    def store(self, symbol: str, df: pd.DataFrame, timeframe: Optional[str] = None):
        if self._estimated_size() > self._max_bytes:
            self._evict_lru()
        self._cache[self._key(symbol, timeframe)] = df
        if timeframe:
            pq_put(symbol, timeframe, df)

    def has(self, symbol: str, timeframe: Optional[str] = None) -> bool:
        if self._key(symbol, timeframe) in self._cache:
            return True
        if timeframe:
            from .parquet_cache import stale
            return not stale(symbol, timeframe)
        return False

    def remove(self, symbol: str, timeframe: Optional[str] = None):
        self._cache.pop(self._key(symbol, timeframe), None)
        if timeframe:
            from .parquet_cache import remove as pq_remove
            pq_remove(symbol, timeframe)

    def clear(self):
        self._cache.clear()

    def _estimated_size(self) -> int:
        total = 0
        for df in self._cache.values():
            total += df.memory_usage(deep=True).sum()
        return total

    def _evict_lru(self):
        if self._cache:
            self._cache.pop(next(iter(self._cache)))

    @staticmethod
    def _ts(s: str) -> int:
        return int(pd.Timestamp(s).timestamp())

    @staticmethod
    def _bar_seconds(timeframe: str) -> int:
        return {"1d": 86400, "1h": 3600, "30m": 1800, "15m": 900, "5m": 300, "1m": 60}.get(timeframe, 3600)

    def _stale(self, df: pd.DataFrame, end_date: str, timeframe: str) -> bool:
        if not end_date:
            return False
        one_bar = self._bar_seconds(timeframe)
        return df.index[-1] < self._ts(end_date) - one_bar

    def ensure(
        self,
        symbol: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        timeframe: Optional[str] = None,
        force_refresh: bool = False,
    ) -> Optional[pd.DataFrame]:
        # 1. Check in-memory cache (fastest)
        df = self.load(symbol, timeframe)
        if df is not None and not force_refresh:
            if start_date and end_date and timeframe:
                if self._stale(df, end_date, timeframe):
                    df = None
                else:
                    lo, hi = self._ts(start_date), self._ts(end_date)
                    mask = (df.index >= lo) & (df.index <= hi)
                    if mask.any():
                        sub = df.loc[mask]
                        requested_span = hi - lo
                        bar_s = self._bar_seconds(timeframe)
                        actual_span = int(sub.index[-1]) - int(sub.index[0])
                        if requested_span <= bar_s or actual_span >= requested_span * 0.8:
                            return sub
                        df = None  # insufficient coverage, fall through
            elif df is not None:
                return df

        if not timeframe:
            return None

        # 2. Check parquet cache (persistent, cross-process)
        from .parquet_cache import get as pq_get, stale as pq_stale_fn

        max_age = _MAX_AGE.get(timeframe, 86400)
        if not force_refresh and not pq_stale_fn(symbol, timeframe, max_age):
            pq_df = pq_get(symbol, timeframe)
            if pq_df is not None:
                if start_date and end_date:
                    lo, hi = self._ts(start_date), self._ts(end_date)
                    filtered = pq_df[(pq_df.index >= lo) & (pq_df.index <= hi)]
                    if not filtered.empty:
                        requested_span = hi - lo
                        bar_s = self._bar_seconds(timeframe)
                        actual_span = int(filtered.index[-1]) - int(filtered.index[0])
                        if requested_span <= bar_s or actual_span >= requested_span * 0.8:
                            self.store(symbol, pq_df, timeframe)
                            return filtered
                        # Coverage insufficient — fall through to re-fetch
                else:
                    self.store(symbol, pq_df, timeframe)
                    return pq_df if not pq_df.empty else None

        # 3. Fetch from remote (Binance or synthetic)
        from data_fetcher import fetch_ohlcv, force_refresh as _force_fetch

        fetched = _force_fetch(symbol, timeframe, start_date or "", end_date or "") if force_refresh \
            else fetch_ohlcv(symbol, timeframe, start_date or "", end_date or "")
        if fetched is not None:
            self.store(symbol, fetched, timeframe)
            return fetched

        return None


DATA_CACHE = DataCache()
