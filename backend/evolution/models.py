from pydantic import BaseModel
from typing import Optional, Any
from enum import Enum


class TaskStatus(str, Enum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class TaskConfig(BaseModel):
    strategy_config_id: str
    symbols: list[str]
    start_date: str
    end_date: str
    timeframe: str = "1d"
    population_size: Optional[int] = None
    max_generations: Optional[int] = None
    crossover_rate: Optional[float] = None
    mutation_rate: Optional[float] = None
    parent_pool_ratio: float = 0.5
    early_stop_generations: Optional[int] = None
    seed_params: Optional[dict[str, Any]] = None
    walk_forward_windows: int = 1


class EvolutionTask(BaseModel):
    task_id: str
    status: TaskStatus = TaskStatus.QUEUED
    created_at: int
    started_at: Optional[int] = None
    completed_at: Optional[int] = None
    config: TaskConfig
    current_generation: int = 0
    total_generations: int = 0
    progress_pct: float = 0.0
    error_message: Optional[str] = None
    result_summary: Optional[dict[str, Any]] = None
    name: Optional[str] = None


class GenerationResult(BaseModel):
    generation: int
    total_generations: int
    duration_sec: float
    population_size: int
    passed_absolute: int
    passed_dynamic: int
    pareto_front_size: int
    pareto_front: list[dict[str, Any]]
    best_cagr: float
    best_sharpe: float
    best_drawdown: float
    crossover_count: int
    mutation_count: int
    repair_count: int
    resample_count: int
    dynamic_thresholds: dict[str, float] = {}
