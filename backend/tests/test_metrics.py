import numpy as np
import pandas as pd
from backtest.metrics import (
    compute_sharpe, compute_sortino, compute_calmar, compute_max_drawdown,
    compute_annualized_return, compute_win_rate, compute_profit_factor, compute_metrics,
)


class _FakeTrade:
    def __init__(self, pnl: float):
        self.pnl = pnl


class TestMetrics:
    def test_sharpe_positive_returns(self):
        eq = [100, 101, 102, 103, 104, 105]
        s = compute_sharpe(eq, 365)
        assert s > 0

    def test_sharpe_flat(self):
        eq = [100, 100, 100, 100]
        s = compute_sharpe(eq, 365)
        assert s == 0.0

    def test_sharpe_empty(self):
        assert compute_sharpe([], 365) == 0.0
        assert compute_sharpe([100], 365) == 0.0

    def test_max_drawdown_no_drawdown(self):
        eq = [100, 101, 102, 103]
        dd = compute_max_drawdown(eq)
        assert dd == 0.0

    def test_max_drawdown_with_drawdown(self):
        eq = [100, 110, 90, 95, 80, 85]
        dd = compute_max_drawdown(eq)
        assert dd > 0
        assert dd < 100

    def test_max_drawdown_correct_value(self):
        eq = [100, 100, 50]
        dd = compute_max_drawdown(eq)
        assert dd == 50.0

    def test_max_drawdown_empty(self):
        assert compute_max_drawdown([]) == 0.0

    def test_annualized_return_positive(self):
        eq = [100, 110]
        r = compute_annualized_return(eq, 365, 365)
        assert abs(r - 0.1) < 0.001

    def test_annualized_return_negative(self):
        eq = [100, 90]
        r = compute_annualized_return(eq, 365, 365)
        assert r < 0

    def test_annualized_return_zero_capital(self):
        assert compute_annualized_return([0, 100], 365, 365) == 0.0

    def test_annualized_return_empty(self):
        assert compute_annualized_return([], 365, 365) == 0.0

    def test_win_rate_all_wins(self):
        trades = [_FakeTrade(10), _FakeTrade(20), _FakeTrade(30)]
        assert compute_win_rate(trades) == 100.0

    def test_win_rate_all_losses(self):
        trades = [_FakeTrade(-10), _FakeTrade(-20)]
        assert compute_win_rate(trades) == 0.0

    def test_win_rate_mixed(self):
        trades = [_FakeTrade(10), _FakeTrade(-5), _FakeTrade(3)]
        assert compute_win_rate(trades) == 66.67

    def test_win_rate_empty(self):
        assert compute_win_rate([]) == 0.0

    def test_profit_factor_all_profit(self):
        trades = [_FakeTrade(10), _FakeTrade(20)]
        assert compute_profit_factor(trades) == 999.0

    def test_profit_factor_mixed(self):
        trades = [_FakeTrade(100), _FakeTrade(-20), _FakeTrade(-10)]
        expected = round(100 / 30, 4)
        assert compute_profit_factor(trades) == expected

    def test_profit_factor_no_trades(self):
        assert compute_profit_factor([]) == 0.0

    def test_profit_factor_all_loss(self):
        trades = [_FakeTrade(-10), _FakeTrade(-20)]
        assert compute_profit_factor(trades) == 0.0

    def test_compute_metrics_full(self):
        eq = [100, 105, 103, 108, 102, 110]
        trades = [_FakeTrade(5), _FakeTrade(-2), _FakeTrade(6)]
        m = compute_metrics(eq, trades, len(eq) - 1, 365)
        assert "total_return" in m
        assert "annualized_return" in m
        assert "sharpe_ratio" in m
        assert "sortino_ratio" in m
        assert "calmar_ratio" in m
        assert "max_drawdown" in m
        assert "win_rate" in m
        assert "profit_factor" in m
        assert "trade_count" in m
        assert m["total_return"] > 0
        assert m["trade_count"] == 3


class TestSortino:
    def test_sortino_mixed_returns(self):
        eq = [100, 102, 98, 103, 97, 105]
        s = compute_sortino(eq, 365)
        assert s > 0

    def test_sortino_empty(self):
        assert compute_sortino([], 365) == 0.0
        assert compute_sortino([100], 365) == 0.0

    def test_sortino_only_gains(self):
        eq = [100, 101, 102]
        s = compute_sortino(eq, 365)
        assert s == 0.0


class TestCalmar:
    def test_calmar_positive(self):
        eq = [100, 105, 102, 108]
        c = compute_calmar(eq, 3, 365)
        assert c > 0

    def test_calmar_no_drawdown(self):
        eq = [100, 101, 102, 103]
        c = compute_calmar(eq, 3, 365)
        assert c == 0.0

    def test_calmar_empty(self):
        assert compute_calmar([], 365, 365) == 0.0
