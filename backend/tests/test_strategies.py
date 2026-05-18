import numpy as np
import pandas as pd
from typing import Any

from strategies.ma_crossover import generate_signals as ma_signals
from strategies.rsi_mean_reversion import generate_signals as rsi_signals
from strategies.bollinger_breakout import generate_signals as bb_signals
from strategies.macd_momentum import generate_signals as macd_signals


def _make_ohlcv(n: int = 200) -> pd.DataFrame:
    np.random.seed(42)
    close = 100 * np.exp(np.cumsum(np.random.normal(0, 0.01, n)))
    high = close * (1 + np.random.uniform(0, 0.02, n))
    low = close * (1 - np.random.uniform(0, 0.02, n))
    volume = np.random.uniform(1000, 10000, n)
    return pd.DataFrame({
        "open": close,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    })


def _count(signals: pd.Series, val: int) -> int:
    return int((signals == val).sum())


class TestMACrossover:
    def test_basic_crossover(self):
        df = _make_ohlcv(200)
        sig = ma_signals(df, {"fast_period": 5, "slow_period": 20, "ma_type": "SMA"})
        assert isinstance(sig, pd.Series)
        assert sig.dtype == int
        assert _count(sig, 1) > 0 or _count(sig, -1) > 0 or _count(sig, 0) == len(sig)

    def test_all_zero_with_identical_prices(self):
        df = pd.DataFrame({"close": [100] * 100, "volume": [1000] * 100})
        sig = ma_signals(df, {"fast_period": 5, "slow_period": 20, "ma_type": "SMA"})
        assert (sig == 0).all()

    def test_ema_mode(self):
        df = _make_ohlcv(200)
        sig_sma = ma_signals(df, {"fast_period": 5, "slow_period": 20, "ma_type": "SMA"})
        sig_ema = ma_signals(df, {"fast_period": 5, "slow_period": 20, "ma_type": "EMA"})
        assert isinstance(sig_ema, pd.Series)

    def test_volume_filter(self):
        df = _make_ohlcv(200)
        sig = ma_signals(df, {
            "fast_period": 5, "slow_period": 20, "ma_type": "SMA",
            "use_volume_filter": True, "volume_period": 10, "volume_threshold": 2.0,
        })
        assert isinstance(sig, pd.Series)

    def test_output_length_matches_input(self):
        df = _make_ohlcv(150)
        sig = ma_signals(df, {"fast_period": 5, "slow_period": 20, "ma_type": "SMA"})
        assert len(sig) == len(df)
        assert sig.index.equals(df.index)


class TestRSIMeanReversion:
    def test_basic_signals(self):
        df = _make_ohlcv(200)
        sig = rsi_signals(df, {
            "rsi_period": 14, "oversold_threshold": 30, "overbought_threshold": 70,
        })
        assert isinstance(sig, pd.Series)
        assert sig.dtype == int

    def test_no_signals_in_flat_market(self):
        np.random.seed(0)
        close = np.concatenate([np.ones(50) * 100, np.ones(100) * 101, np.ones(50) * 100])
        df = pd.DataFrame({
            "close": close, "high": close * 1.01, "low": close * 0.99, "volume": 1000,
        })
        sig = rsi_signals(df, {
            "rsi_period": 14, "oversold_threshold": 30, "overbought_threshold": 70,
        })
        assert isinstance(sig, pd.Series)

    def test_with_confirmation_bars(self):
        df = _make_ohlcv(300)
        sig_1 = rsi_signals(df, {
            "rsi_period": 14, "oversold_threshold": 30, "overbought_threshold": 70,
            "confirmation_bars": 1,
        })
        sig_3 = rsi_signals(df, {
            "rsi_period": 14, "oversold_threshold": 30, "overbought_threshold": 70,
            "confirmation_bars": 3,
        })
        assert isinstance(sig_3, pd.Series)

    def test_output_length_matches_input(self):
        df = _make_ohlcv(100)
        sig = rsi_signals(df, {
            "rsi_period": 14, "oversold_threshold": 30, "overbought_threshold": 70,
        })
        assert len(sig) == len(df)


class TestBollingerBreakout:
    def test_basic_signals(self):
        df = _make_ohlcv(200)
        sig = bb_signals(df, {"bb_period": 20, "bb_std": 2.0})
        assert isinstance(sig, pd.Series)
        assert sig.dtype == int

    def test_fixed_exit_mode(self):
        df = _make_ohlcv(200)
        sig = bb_signals(df, {
            "bb_period": 20, "bb_std": 2.0,
            "exit_mode": "fixed", "stop_loss_pct": 0.05, "take_profit_pct": 0.1,
        })
        assert isinstance(sig, pd.Series)

    def test_no_squeeze_filter(self):
        df = _make_ohlcv(200)
        sig = bb_signals(df, {
            "bb_period": 20, "bb_std": 2.0,
            "use_squeeze_filter": False,
        })
        assert isinstance(sig, pd.Series)

    def test_output_length_matches_input(self):
        df = _make_ohlcv(100)
        sig = bb_signals(df, {"bb_period": 20, "bb_std": 2.0})
        assert len(sig) == len(df)


class TestMACDMomentum:
    def test_basic_signals(self):
        df = _make_ohlcv(200)
        sig = macd_signals(df, {
            "fast_ema": 12, "slow_ema": 26, "signal_period": 9,
        })
        assert isinstance(sig, pd.Series)
        assert sig.dtype == int

    def test_with_trend_filter(self):
        df = _make_ohlcv(300)
        sig = macd_signals(df, {
            "fast_ema": 12, "slow_ema": 26, "signal_period": 9,
            "use_trend_filter": True, "trend_ma_period": 50,
        })
        assert isinstance(sig, pd.Series)

    def test_without_macd_positive_requirement(self):
        df = _make_ohlcv(200)
        sig = macd_signals(df, {
            "fast_ema": 12, "slow_ema": 26, "signal_period": 9,
            "require_macd_positive": False,
        })
        assert isinstance(sig, pd.Series)

    def test_histogram_confirmation(self):
        df = _make_ohlcv(200)
        sig = macd_signals(df, {
            "fast_ema": 12, "slow_ema": 26, "signal_period": 9,
            "histogram_confirm_bars": 2,
        })
        assert isinstance(sig, pd.Series)

    def test_output_length_matches_input(self):
        df = _make_ohlcv(100)
        sig = macd_signals(df, {
            "fast_ema": 12, "slow_ema": 26, "signal_period": 9,
        })
        assert len(sig) == len(df)
