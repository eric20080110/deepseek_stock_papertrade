from dataclasses import dataclass


@dataclass
class FitnessSettings:
    is_ratio: float = 0.7
    oos_ratio: float = 0.3
    min_bars_required: int = 200
    abs_profit_factor_min: float = 1.0
    abs_win_rate_min: float = 0.0
    abs_r2_min: float = 0.0
    abs_trade_count_min: int = 1
    abs_oos_consistency_min: float = 0.3
    abs_mc_prob_positive_min: float = 50.0
    abs_mc_ci_lower_return_min: float = -30.0
    dynamic_elimination_pct: float = 0.2
    elite_survival_rank: int = 1
    parent_pool_ratio: float = 0.5
    threshold_relaxation_floor: float = 0.1

    @classmethod
    def default(cls) -> "FitnessSettings":
        return cls()


SETTINGS = FitnessSettings.default()
