import pandas as pd
from typing import Optional


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

    def has(self, symbol: str, timeframe: Optional[str] = None) -> bool:
        return self._key(symbol, timeframe) in self._cache

    def remove(self, symbol: str, timeframe: Optional[str] = None):
        self._cache.pop(self._key(symbol, timeframe), None)

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
    ) -> Optional[pd.DataFrame]:
        df = self.load(symbol, timeframe)
        if df is not None:
            if start_date and end_date and timeframe:
                if self._stale(df, end_date, timeframe):
                    df = None
                else:
                    lo, hi = self._ts(start_date), self._ts(end_date)
                    mask = (df.index >= lo) & (df.index <= hi)
                    if mask.any():
                        return df.loc[mask]
            if df is not None:
                return df

        if timeframe:
            from data_fetcher import fetch_ohlcv
            fetched = fetch_ohlcv(symbol, timeframe, start_date or "", end_date or "")
            if fetched is not None:
                self.store(symbol, fetched, timeframe)
                return fetched

        return None


DATA_CACHE = DataCache()
