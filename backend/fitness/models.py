from pydantic import BaseModel
from typing import Optional


class ObjectiveVector(BaseModel):
    cagr: float = 0.0
    max_drawdown: float = 0.0
    sharpe: float = 0.0


class ThresholdMetrics(BaseModel):
    profit_factor: float = 0.0
    win_rate: float = 0.0
    r2: float = 0.0
    trade_count: int = 0
    oos_score: float = 0.0


class IndividualScore(BaseModel):
    strategy_id: str
    passed_absolute_threshold: bool = False
    passed_dynamic_threshold: bool = False
    oos_consistency_score: float = 0.0
    pareto_rank: Optional[int] = None
    crowding_distance: Optional[float] = None
    is_elite: bool = False
    objective_vector: ObjectiveVector = ObjectiveVector()
    threshold_metrics: ThresholdMetrics = ThresholdMetrics()
    elimination_reason: Optional[str] = None


class GenerationSummary(BaseModel):
    generation: int = 0
    total_individuals: int = 0
    passed_absolute: int = 0
    passed_dynamic: int = 0
    pareto_front_size: int = 0
    elite_count: int = 0
    best_cagr: float = 0.0
    best_sharpe: float = 0.0
    best_drawdown: float = 0.0
    dynamic_thresholds: dict[str, float] = {}
    pareto_front_ids: list[str] = []
