import numpy as np
from typing import Optional

from .config import SETTINGS, FitnessSettings
from .models import (
    IndividualScore, ObjectiveVector, ThresholdMetrics, GenerationSummary,
)


def compute_r2(equity_curve: list[float]) -> float:
    if len(equity_curve) < 3:
        return 0.0
    y = np.array(equity_curve, dtype=np.float64)
    x = np.arange(len(y), dtype=np.float64)
    if np.std(y) == 0:
        return 1.0
    corr = np.corrcoef(x, y)[0, 1]
    return float(corr ** 2) if not np.isnan(corr) else 0.0


class FitnessScorer:
    def __init__(self, settings: Optional[FitnessSettings] = None):
        self.settings = settings or SETTINGS

    def compute_oos_consistency(
        self, is_metrics: dict, oos_metrics: dict
    ) -> float:
        ratios = []
        for key in ["annualized_return", "sharpe_ratio", "max_drawdown"]:
            is_val = is_metrics.get(key, 0) or 0
            oos_val = oos_metrics.get(key, 0) or 0
            if key == "max_drawdown":
                is_val = -is_val if is_val < 0 else is_val
                oos_val = -oos_val if oos_val < 0 else oos_val
                if is_val == 0:
                    continue
                ratio = min(oos_val / is_val, 1.0) if is_val > 0 and oos_val > 0 else 0.0
            else:
                if is_val <= 0:
                    ratio = 0.0
                elif oos_val <= 0:
                    ratio = 0.0
                else:
                    ratio = min(oos_val / is_val, 1.0)
            ratios.append(ratio)
        return float(np.mean(ratios)) if ratios else 0.0

    def check_absolute_threshold(
        self, metrics: dict, oos_score: float
    ) -> tuple[bool, Optional[str]]:
        s = self.settings
        pf = metrics.get("profit_factor", 0) or 0
        wr = metrics.get("win_rate", 0) or 0
        tc = metrics.get("trade_count", 0) or 0

        if pf <= s.abs_profit_factor_min:
            return False, f"Profit factor {pf:.2f} <= {s.abs_profit_factor_min}"
        if wr <= s.abs_win_rate_min:
            return False, f"Win rate {wr:.2f} <= {s.abs_win_rate_min}"
        if tc < s.abs_trade_count_min:
            return False, f"Trade count {tc} < {s.abs_trade_count_min}"
        if oos_score < s.abs_oos_consistency_min:
            return False, f"OOS score {oos_score:.3f} < {s.abs_oos_consistency_min}"

        eq = metrics.get("equity_curve", [])
        if len(eq) > 2:
            r2 = compute_r2(eq)
            if r2 < s.abs_r2_min:
                return False, f"R² {r2:.3f} < {s.abs_r2_min}"

        return True, None

    def compute_dynamic_thresholds(
        self, scores: list[IndividualScore]
    ) -> dict[str, float]:
        pct = self.settings.dynamic_elimination_pct
        cagrs = [s.objective_vector.cagr for s in scores]
        dd = [s.objective_vector.max_drawdown for s in scores]
        sharpes = [s.objective_vector.sharpe for s in scores]

        return {
            "cagr": float(np.percentile(cagrs, pct * 100)) if cagrs else 0,
            "max_drawdown": float(np.percentile(dd, (1 - pct) * 100)) if dd else 0,
            "sharpe": float(np.percentile(sharpes, pct * 100)) if sharpes else 0,
        }

    def check_dynamic_threshold(
        self, score: IndividualScore, thresholds: dict[str, float]
    ) -> bool:
        obj = score.objective_vector
        if obj.cagr < thresholds.get("cagr", -float("inf")):
            return False
        if obj.max_drawdown > thresholds.get("max_drawdown", float("inf")):
            return False
        if obj.sharpe < thresholds.get("sharpe", -float("inf")):
            return False
        return True

    def pareto_rank(
        self, scores: list[IndividualScore]
    ) -> list[IndividualScore]:
        for s in scores:
            s.pareto_rank = None
            s.crowding_distance = None

        remaining = list(scores)
        rank = 1
        while remaining:
            front = self._find_pareto_front(remaining)
            for s in front:
                s.pareto_rank = rank
            self._compute_crowding_distances(front)
            if rank == 1:
                for s in front:
                    s.is_elite = True
            remaining = [s for s in remaining if s.pareto_rank is None]
            rank += 1

        return scores

    def _find_pareto_front(
        self, individuals: list[IndividualScore]
    ) -> list[IndividualScore]:
        front = []
        for i, a in enumerate(individuals):
            dominated = False
            for b in individuals:
                if a is b:
                    continue
                if self._dominates(b, a):
                    dominated = True
                    break
            if not dominated:
                front.append(a)
        return front

    def _dominates(self, a: IndividualScore, b: IndividualScore) -> bool:
        oa = a.objective_vector
        ob = b.objective_vector
        cagr_better = oa.cagr >= ob.cagr
        dd_better = oa.max_drawdown <= ob.max_drawdown
        sharpe_better = oa.sharpe >= ob.sharpe
        strictly_better = (
            oa.cagr > ob.cagr or oa.max_drawdown < ob.max_drawdown or oa.sharpe > ob.sharpe
        )
        return cagr_better and dd_better and sharpe_better and strictly_better

    def _compute_crowding_distances(self, front: list[IndividualScore]):
        if len(front) <= 2:
            for s in front:
                s.crowding_distance = 1e9
            return

        n = len(front)
        for s in front:
            s.crowding_distance = 0.0

        for key in ["cagr", "max_drawdown", "sharpe"]:
            sorted_front = sorted(
                front, key=lambda s: getattr(s.objective_vector, key)
            )
            min_val = getattr(sorted_front[0].objective_vector, key)
            max_val = getattr(sorted_front[-1].objective_vector, key)
            rng = max_val - min_val
            if rng == 0:
                continue
            sorted_front[0].crowding_distance = 1e9
            sorted_front[-1].crowding_distance = 1e9
            for i in range(1, n - 1):
                val_hi = getattr(sorted_front[i + 1].objective_vector, key)
                val_lo = getattr(sorted_front[i - 1].objective_vector, key)
                contribution = (val_hi - val_lo) / rng
                sorted_front[i].crowding_distance = (
                    sorted_front[i].crowding_distance or 0
                ) + contribution

    def select_parent_pool(
        self, scores: list[IndividualScore], pool_size: int
    ) -> list[IndividualScore]:
        ranked = [s for s in scores if s.pareto_rank is not None]
        ranked.sort(key=lambda s: (s.pareto_rank, -(s.crowding_distance or 0)))
        return ranked[:pool_size]


def score_individuals(
    is_metrics_list: list[dict],
    oos_metrics_list: list[dict],
    generation: int = 0,
    scorer: Optional[FitnessScorer] = None,
) -> tuple[list[IndividualScore], GenerationSummary]:
    if scorer is None:
        scorer = FitnessScorer()

    scores: list[IndividualScore] = []

    for i, (is_m, oos_m) in enumerate(zip(is_metrics_list, oos_metrics_list)):
        sid = is_m.get("strategy_id", f"ind_{i}")
        oos_score = scorer.compute_oos_consistency(is_m, oos_m)

        obj = ObjectiveVector(
            cagr=is_m.get("annualized_return", 0) or 0,
            max_drawdown=is_m.get("max_drawdown", 0) or 0,
            sharpe=is_m.get("sharpe_ratio", 0) or 0,
        )
        tm = ThresholdMetrics(
            profit_factor=is_m.get("profit_factor", 0) or 0,
            win_rate=is_m.get("win_rate", 0) or 0,
            r2=compute_r2(is_m.get("equity_curve", [])),
            trade_count=int(is_m.get("trade_count", 0) or 0),
            oos_score=oos_score,
        )

        score = IndividualScore(
            strategy_id=sid,
            oos_consistency_score=oos_score,
            objective_vector=obj,
            threshold_metrics=tm,
        )
        scores.append(score)

    # Layer 1: Fixed absolute thresholds
    for s in scores:
        passed, reason = scorer.check_absolute_threshold(
            {
                "profit_factor": s.threshold_metrics.profit_factor,
                "win_rate": s.threshold_metrics.win_rate,
                "trade_count": s.threshold_metrics.trade_count,
                "equity_curve": [],
            },
            s.oos_consistency_score,
        )
        s.passed_absolute_threshold = passed
        if not passed:
            s.elimination_reason = reason

    survived_abs = [s for s in scores if s.passed_absolute_threshold]

    # Auto-relaxation: if too few survive
    if len(survived_abs) < max(1, len(scores) * scorer.settings.threshold_relaxation_floor):
        relaxed_s = FitnessScorer(FitnessSettings(
            abs_profit_factor_min=scorer.settings.abs_profit_factor_min * 0.8,
            abs_win_rate_min=scorer.settings.abs_win_rate_min * 0.8,
            abs_trade_count_min=max(1, int(scorer.settings.abs_trade_count_min * 0.8)),
            abs_oos_consistency_min=scorer.settings.abs_oos_consistency_min * 0.8,
        ))
        for s in scores:
            if not s.passed_absolute_threshold:
                passed, _ = relaxed_s.check_absolute_threshold(
                    {
                        "profit_factor": s.threshold_metrics.profit_factor,
                        "win_rate": s.threshold_metrics.win_rate,
                        "trade_count": s.threshold_metrics.trade_count,
                        "equity_curve": [],
                    },
                    s.oos_consistency_score,
                )
                if passed:
                    s.passed_absolute_threshold = True
                    s.elimination_reason = None
        survived_abs = [s for s in scores if s.passed_absolute_threshold]

    # Layer 2: Dynamic relative thresholds
    if survived_abs:
        dyn_thresholds = scorer.compute_dynamic_thresholds(survived_abs)
        for s in survived_abs:
            s.passed_dynamic_threshold = scorer.check_dynamic_threshold(s, dyn_thresholds)
            if not s.passed_dynamic_threshold:
                s.elimination_reason = "Dynamic threshold淘汰"
    else:
        dyn_thresholds = {}

    survived_dyn = [s for s in survived_abs if s.passed_dynamic_threshold]

    # Pareto ranking on survivors
    if survived_dyn:
        scorer.pareto_rank(survived_dyn)

    # Build generation summary
    front = [s for s in survived_dyn if s.pareto_rank == 1]
    summary = GenerationSummary(
        generation=generation,
        total_individuals=len(scores),
        passed_absolute=len(survived_abs),
        passed_dynamic=len(survived_dyn),
        pareto_front_size=len(front),
        elite_count=sum(1 for s in survived_dyn if s.is_elite),
        best_cagr=max((s.objective_vector.cagr for s in survived_dyn), default=0),
        best_sharpe=max((s.objective_vector.sharpe for s in survived_dyn), default=0),
        best_drawdown=min((s.objective_vector.max_drawdown for s in survived_dyn), default=0),
        dynamic_thresholds=dyn_thresholds,
        pareto_front_ids=[s.strategy_id for s in front],
    )

    return scores, summary
