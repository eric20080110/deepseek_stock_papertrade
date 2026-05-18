import numpy as np
import pandas as pd
from backtest.engine import run_symbol_backtest, run_backtest
from backtest.models import SymbolResult, InstanceResult


def _make_data(n=200, seed=42) -> pd.DataFrame:
    np.random.seed(seed)
    dates = pd.date_range("2024-01-01", periods=n, freq="D")
    close = 100 * np.exp(np.cumsum(np.random.normal(0.0005, 0.01, n)))
    high = close * (1 + np.random.uniform(0, 0.01, n))
    low = close * (1 - np.random.uniform(0, 0.01, n))
    volume = np.random.uniform(1000, 10000, n)
    return pd.DataFrame({
        "open": close, "high": high, "low": low,
        "close": close, "volume": volume,
    }, index=dates)


class TestRunSymbolBacktest:
    def test_basic_execution(self):
        df = _make_data()
        sr = run_symbol_backtest("BTC/USDT", df, {
            "fast_period": 5, "slow_period": 20, "ma_type": "SMA",
        }, "ma_crossover", 10000)
        assert sr is not None
        assert isinstance(sr, SymbolResult)
        assert sr.symbol == "BTC/USDT"
        assert sr.trade_count >= 0
        assert sr.total_return is not None
        assert sr.sharpe_ratio is not None
        assert sr.max_drawdown is not None
        assert len(sr.equity_curve) > 0

    def test_returns_instance_result_type(self):
        df = _make_data()
        sr = run_symbol_backtest("ETH/USDT", df, {
            "fast_period": 5, "slow_period": 20, "ma_type": "SMA",
        }, "ma_crossover", 10000)
        assert isinstance(sr, SymbolResult)

    def test_min_bars_too_short(self):
        df = _make_data(n=10)
        sr = run_symbol_backtest("BTC/USDT", df, {
            "fast_period": 5, "slow_period": 20, "ma_type": "SMA",
        }, "ma_crossover", 10000)
        assert sr is None

    def test_insufficient_bars_returns_none(self):
        df = _make_data(n=49)
        sr = run_symbol_backtest("BTC/USDT", df, {"fast_period": 5, "slow_period": 20, "ma_type": "SMA"}, "ma_crossover", 10000)
        assert sr is None

    def test_metrics_range(self):
        df = _make_data(n=500)
        sr = run_symbol_backtest("BTC/USDT", df, {
            "fast_period": 10, "slow_period": 50, "ma_type": "SMA",
        }, "ma_crossover", 10000)
        assert sr is not None
        assert -100 <= sr.total_return <= 1000
        assert 0 <= sr.max_drawdown <= 100


class TestRunBacktest:
    def test_single_symbol(self):
        df = _make_data()
        data_map = {"BTC/USDT": df}
        result = run_backtest(
            "ma_crossover",
            {"fast_period": 5, "slow_period": 20, "ma_type": "SMA"},
            ["BTC/USDT"], data_map, 10000, parallel=False,
        )
        assert isinstance(result, InstanceResult)
        assert "BTC/USDT" in result.symbol_results
        assert "annualized_return" in result.weighted_metrics
        assert result.backtest_duration_sec > 0

    def test_multi_symbol(self):
        df1 = _make_data(seed=42)
        df2 = _make_data(seed=123)
        data_map = {"BTC/USDT": df1, "ETH/USDT": df2}
        result = run_backtest(
            "ma_crossover",
            {"fast_period": 5, "slow_period": 20, "ma_type": "SMA"},
            ["BTC/USDT", "ETH/USDT"], data_map, 10000, parallel=False,
        )
        assert len(result.symbol_results) == 2
        assert abs(sum(result.weights.values()) - 1.0) < 0.01

    def test_invalid_strategy_returns_no_results(self):
        df = _make_data()
        data_map = {"BTC/USDT": df}
        result = run_backtest(
            "non_existent_strategy",
            {},
            ["BTC/USDT"], data_map, 10000, parallel=False,
        )
        assert len(result.symbol_results) == 0


class TestStopLossTakeProfit:
    def test_stop_loss_changes_behavior(self):
        np.random.seed(42)
        dates = pd.date_range("2024-01-01", periods=200, freq="D")
        close = 100 * np.exp(np.cumsum(np.random.normal(-0.002, 0.02, 200)))
        high = close * 1.01
        low = close * 0.99
        df = pd.DataFrame({
            "open": close, "high": high, "low": low,
            "close": close, "volume": np.random.uniform(1000, 10000, 200),
        }, index=dates)

        no_sl = run_symbol_backtest("TEST", df, {
            "fast_period": 5, "slow_period": 20, "ma_type": "SMA",
        }, "ma_crossover", 10000, stop_loss_pct=0.0)
        with_sl = run_symbol_backtest("TEST", df, {
            "fast_period": 5, "slow_period": 20, "ma_type": "SMA",
        }, "ma_crossover", 10000, stop_loss_pct=0.05)

        assert no_sl is not None and with_sl is not None
        assert with_sl.total_return != no_sl.total_return

    def test_take_profit_locks_gains(self):
        np.random.seed(7)
        dates = pd.date_range("2024-01-01", periods=200, freq="D")
        close = 100 * np.exp(np.cumsum(np.random.normal(0.001, 0.015, 200)))
        high = close * 1.01
        low = close * 0.99
        df = pd.DataFrame({
            "open": close, "high": high, "low": low,
            "close": close, "volume": np.random.uniform(1000, 10000, 200),
        }, index=dates)

        no_tp = run_symbol_backtest("TEST", df, {
            "fast_period": 5, "slow_period": 20, "ma_type": "SMA",
        }, "ma_crossover", 10000, take_profit_pct=0.0)
        with_tp = run_symbol_backtest("TEST", df, {
            "fast_period": 5, "slow_period": 20, "ma_type": "SMA",
        }, "ma_crossover", 10000, take_profit_pct=0.03)

        assert no_tp is not None and with_tp is not None
        assert with_tp.trade_count >= no_tp.trade_count  # TP should add more trades

    def test_sl_and_tp_both_zero_no_change(self):
        df = _make_data()
        normal = run_symbol_backtest("TEST", df, {
            "fast_period": 5, "slow_period": 20, "ma_type": "SMA",
        }, "ma_crossover", 10000)
        with_zeros = run_symbol_backtest("TEST", df, {
            "fast_period": 5, "slow_period": 20, "ma_type": "SMA",
        }, "ma_crossover", 10000, stop_loss_pct=0.0, take_profit_pct=0.0)
        assert normal is not None and with_zeros is not None
        assert normal.total_return == with_zeros.total_return
        assert normal.trade_count == with_zeros.trade_count

    def test_sl_tp_via_run_backtest(self):
        df = _make_data()
        data_map = {"TEST": df}
        result = run_backtest(
            "ma_crossover",
            {"fast_period": 5, "slow_period": 20, "ma_type": "SMA"},
            ["TEST"], data_map, 10000, parallel=False,
            stop_loss_pct=0.1, take_profit_pct=0.2,
        )
        assert isinstance(result, InstanceResult)
        assert result.symbol_results["TEST"].trade_count >= 0


class TestWalkForward:
    def test_create_one_window_same_as_single_split(self):
        from evolution.engine import _create_walk_forward_windows
        df = _make_data(n=500)
        data_map = {"TEST": df}
        windows = _create_walk_forward_windows(data_map, 1)
        assert len(windows) == 1
        is_map, oos_map = windows[0]
        total = len(is_map["TEST"]) + len(oos_map["TEST"])
        assert total <= 500

    def test_create_multiple_windows(self):
        from evolution.engine import _create_walk_forward_windows
        df = _make_data(n=1000)
        data_map = {"TEST": df}
        windows = _create_walk_forward_windows(data_map, 3)
        assert len(windows) == 3
        for is_map, oos_map in windows:
            assert "TEST" in is_map
            assert "TEST" in oos_map
            assert len(is_map["TEST"]) > 0
            assert len(oos_map["TEST"]) > 0

    def test_windows_have_different_ranges(self):
        from evolution.engine import _create_walk_forward_windows
        df = _make_data(n=1000)
        data_map = {"TEST": df}
        windows = _create_walk_forward_windows(data_map, 2)
        starts = [w[0]["TEST"].index[0] for w in windows]
        assert len(set(starts)) > 1

    def test_walk_forward_via_scheduler(self):
        from evolution.scheduler import ParallelScheduler
        df = _make_data(n=500)
        data_map = {"TEST": df}
        windows = [(data_map, {})]
        scheduler = ParallelScheduler(max_workers=1)
        results = scheduler.run_backtests(
            individuals=[{"fast_period": 5, "slow_period": 20, "ma_type": "SMA"}],
            strategy_id="ma_crossover",
            symbols=["TEST"],
            data_map=data_map,
            walk_data_maps=windows,
        )
        assert len(results) > 0
        assert "weighted_metrics" in results[0]

    def test_walk_forward_backward_compatible(self):
        from evolution.scheduler import ParallelScheduler
        df = _make_data(n=500)
        data_map = {"TEST": df}
        scheduler = ParallelScheduler(max_workers=1)
        normal = scheduler.run_backtests(
            individuals=[{"fast_period": 5, "slow_period": 20, "ma_type": "SMA"}],
            strategy_id="ma_crossover",
            symbols=["TEST"],
            data_map=data_map,
        )
        wf = scheduler.run_backtests(
            individuals=[{"fast_period": 5, "slow_period": 20, "ma_type": "SMA"}],
            strategy_id="ma_crossover",
            symbols=["TEST"],
            data_map=data_map,
            oos_data_map={},
            walk_data_maps=[(data_map, {})],
        )
        assert normal[0]["weighted_metrics"]["trade_count"] == wf[0]["weighted_metrics"]["trade_count"]
