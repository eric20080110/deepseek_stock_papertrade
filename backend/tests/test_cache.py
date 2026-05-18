import os
import time
import numpy as np
import pandas as pd
import tempfile

from backtest.parquet_cache import (
    get as pq_get, put as pq_put, has as pq_has,
    stale as pq_stale, remove as pq_remove, clear as pq_clear,
    set_cache_dir,
)


class TestParquetCache:
    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        set_cache_dir(self.tmpdir)

    def teardown_method(self):
        pq_clear()

    def _df(self, n=100) -> pd.DataFrame:
        dates = pd.date_range("2024-01-01", periods=n, freq="h")
        close = 100 * np.exp(np.cumsum(np.random.normal(0, 0.01, n)))
        return pd.DataFrame({
            "open": close, "high": close * 1.01, "low": close * 0.99,
            "close": close, "volume": np.random.uniform(1000, 10000, n),
        }, index=dates.asi8 // 10**9)

    def test_put_get_roundtrip(self):
        df = self._df()
        pq_put("BTC/USDT", "1h", df)
        loaded = pq_get("BTC/USDT", "1h")
        assert loaded is not None
        assert len(loaded) == len(df)
        assert float(loaded["close"].iloc[0]) == float(df["close"].iloc[0])

    def test_get_nonexistent(self):
        assert pq_get("NONEXIST", "1h") is None

    def test_has(self):
        assert not pq_has("BTC/USDT", "1h")
        pq_put("BTC/USDT", "1h", self._df())
        assert pq_has("BTC/USDT", "1h")

    def test_remove(self):
        pq_put("BTC/USDT", "1h", self._df())
        pq_remove("BTC/USDT", "1h")
        assert not pq_has("BTC/USDT", "1h")

    def test_stale_freshly_written(self):
        pq_put("BTC/USDT", "1h", self._df())
        assert not pq_stale("BTC/USDT", "1h", max_age_seconds=86400)

    def test_stale_missing(self):
        assert pq_stale("NONEXIST", "1h")

    def test_get_with_range(self):
        df = self._df(200)
        pq_put("BTC/USDT", "1h", df)
        ts = df.index.values
        mid = int(ts[len(ts) // 2])
        subset = pq_get("BTC/USDT", "1h", start_ts=mid)
        assert subset is not None
        assert len(subset) <= len(df)
        assert subset.index[0] >= mid

    def test_persists_across_cache_instances(self):
        pq_put("BTC/USDT", "1h", self._df())
        loaded = pq_get("BTC/USDT", "1h")
        assert loaded is not None
        assert len(loaded) == 100

    def test_symbol_with_special_chars(self):
        pq_put("BTC/USDT:USDT", "1h", self._df())
        assert pq_has("BTC/USDT:USDT", "1h")


class TestRateLimitManager:
    def test_initial_state(self):
        from data_fetcher import RateLimitManager
        rl = RateLimitManager()
        assert rl._consecutive_429 == 0
        assert rl._circuit_open_until == 0.0

    def test_record_request(self):
        from data_fetcher import RateLimitManager
        rl = RateLimitManager()
        rl.record_request(5)
        w10, w1m = rl._current_weight()
        assert w10 >= 5
        assert w1m >= 5

    def test_reset_on_success(self):
        from data_fetcher import RateLimitManager
        rl = RateLimitManager()
        rl._consecutive_429 = 3
        rl.on_success()
        assert rl._consecutive_429 == 0

    def test_weight_pruning(self):
        from data_fetcher import RateLimitManager
        rl = RateLimitManager()
        import time
        rl._weight_10s.append((time.time() - 20, 50))
        w10, _ = rl._current_weight()
        assert w10 == 0
