from fitness.scoring import FitnessScorer, score_individuals, compute_r2
from fitness.models import IndividualScore, ObjectiveVector, ThresholdMetrics


class TestComputeR2:
    def test_perfect_trend(self):
        r2 = compute_r2([100, 110, 120, 130, 140])
        assert r2 > 0.9

    def test_flat_line(self):
        r2 = compute_r2([100, 100, 100, 100])
        assert r2 == 1.0

    def test_too_short(self):
        assert compute_r2([100]) == 0.0
        assert compute_r2([100, 200]) == 0.0


class TestFitnessScorer:
    def setup_method(self):
        self.scorer = FitnessScorer()

    def test_oos_consistency_perfect(self):
        is_m = {"annualized_return": 0.1, "sharpe_ratio": 1.5, "max_drawdown": -0.1}
        oos_m = {"annualized_return": 0.1, "sharpe_ratio": 1.5, "max_drawdown": -0.1}
        score = self.scorer.compute_oos_consistency(is_m, oos_m)
        assert score == 1.0

    def test_oos_consistency_half(self):
        is_m = {"annualized_return": 0.2, "sharpe_ratio": 2.0, "max_drawdown": -0.2}
        oos_m = {"annualized_return": 0.1, "sharpe_ratio": 1.0, "max_drawdown": -0.1}
        score = self.scorer.compute_oos_consistency(is_m, oos_m)
        assert 0.4 < score < 0.6

    def test_oos_consistency_worse_oos(self):
        is_m = {"annualized_return": 0.1, "sharpe_ratio": 1.0, "max_drawdown": -0.05}
        oos_m = {"annualized_return": -0.05, "sharpe_ratio": -0.5, "max_drawdown": -0.2}
        score = self.scorer.compute_oos_consistency(is_m, oos_m)
        expected = (0.0 + 0.0 + 1.0) / 3
        assert score == expected

    def test_check_absolute_threshold_passes(self):
        passed, reason = self.scorer.check_absolute_threshold(
            {"profit_factor": 1.5, "win_rate": 40, "trade_count": 20, "equity_curve": [100, 110, 120]},
            0.5,
        )
        assert passed
        assert reason is None

    def test_check_absolute_threshold_fails_profit_factor(self):
        passed, reason = self.scorer.check_absolute_threshold(
            {"profit_factor": 0.5, "win_rate": 40, "trade_count": 20, "equity_curve": [100, 110]},
            0.5,
        )
        assert not passed
        assert "profit factor" in reason.lower()

    def test_check_absolute_threshold_fails_oos(self):
        passed, reason = self.scorer.check_absolute_threshold(
            {"profit_factor": 2.0, "win_rate": 50, "trade_count": 30, "equity_curve": [100, 110, 120]},
            0.1,
        )
        assert not passed
        assert "oos" in reason.lower()


class TestScoreIndividuals:
    def test_basic_scoring(self):
        is_list = [{"strategy_id": "s1", "annualized_return": 0.2, "sharpe_ratio": 2.0, "max_drawdown": 0.1, "profit_factor": 2.0, "win_rate": 50, "trade_count": 30, "equity_curve": [100, 110]}]
        oos_list = [{"strategy_id": "s1", "annualized_return": 0.15, "sharpe_ratio": 1.5, "max_drawdown": 0.08}]
        scores, summary = score_individuals(is_list, oos_list)
        assert len(scores) == 1
        assert summary.total_individuals == 1

    def test_multiple_individuals(self):
        is_list = [
            {"strategy_id": "s1", "annualized_return": 0.3, "sharpe_ratio": 2.5, "max_drawdown": 0.05, "profit_factor": 3.0, "win_rate": 55, "trade_count": 40, "equity_curve": [100, 130]},
            {"strategy_id": "s2", "annualized_return": 0.05, "sharpe_ratio": 0.5, "max_drawdown": 0.3, "profit_factor": 1.1, "win_rate": 30, "trade_count": 10, "equity_curve": [100, 95]},
        ]
        oos_list = [
            {"strategy_id": "s1", "annualized_return": 0.2, "sharpe_ratio": 1.8, "max_drawdown": 0.08},
            {"strategy_id": "s2", "annualized_return": 0.01, "sharpe_ratio": 0.1, "max_drawdown": 0.35},
        ]
        scores, summary = score_individuals(is_list, oos_list)
        assert len(scores) == 2
        for s in scores:
            assert s.pareto_rank is not None or s.elimination_reason is not None

    def test_pareto_front_ordering(self):
        is_list = [
            {"strategy_id": "worst", "annualized_return": 0.01, "sharpe_ratio": 0.1, "max_drawdown": 0.4, "profit_factor": 1.05, "win_rate": 25, "trade_count": 5, "equity_curve": [100, 90]},
            {"strategy_id": "mid", "annualized_return": 0.2, "sharpe_ratio": 1.5, "max_drawdown": 0.15, "profit_factor": 2.0, "win_rate": 45, "trade_count": 30, "equity_curve": [100, 120]},
            {"strategy_id": "best", "annualized_return": 0.5, "sharpe_ratio": 3.0, "max_drawdown": 0.02, "profit_factor": 5.0, "win_rate": 60, "trade_count": 50, "equity_curve": [100, 150]},
        ]
        oos_list = [{"annualized_return": 0.1, "sharpe_ratio": 1.0, "max_drawdown": 0.1}] * 3
        scores, summary = score_individuals(is_list, oos_list)
        best = next(s for s in scores if s.strategy_id == "best")
        assert best.pareto_rank == 1
        assert best.passed_absolute_threshold
