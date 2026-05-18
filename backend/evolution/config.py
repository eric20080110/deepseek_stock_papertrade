from dataclasses import dataclass, field
from typing import Optional
import multiprocessing


_TIMEFRAME_CONFIGS = {
    "1d":  {"pop": 200, "gens": 50,  "timeout": 30},
    "1h":  {"pop": 100, "gens": 30,  "timeout": 120},
    "30m": {"pop": 60,  "gens": 20,  "timeout": 180},
    "15m": {"pop": 50,  "gens": 15,  "timeout": 300},
    "5m":  {"pop": 30,  "gens": 10,  "timeout": 600},
    "1m":  {"pop": 20,  "gens": 8,   "timeout": 900},
}


@dataclass
class EvolutionSettings:
    max_workers: int = field(default_factory=lambda: max(1, multiprocessing.cpu_count() - 1))
    task_queue_max_size: int = 10
    websocket_heartbeat_interval: int = 30
    result_retention_days: int = 30
    default_population_1d: int = 200
    default_generations_1d: int = 50
    default_population_1h: int = 100
    default_generations_1h: int = 30
    default_population_30m: int = 60
    default_generations_30m: int = 20
    default_population_15m: int = 50
    default_generations_15m: int = 15
    default_population_5m: int = 30
    default_generations_5m: int = 10
    default_population_1m: int = 20
    default_generations_1m: int = 8
    default_crossover_rate: float = 0.8
    default_mutation_rate: float = 0.15
    default_early_stop_generations: int = 10
    tournament_k: int = 3
    adaptive_mutation_multiplier: float = 1.5
    adaptive_mutation_max: float = 0.4
    diversity_injection_ratio: float = 0.1
    single_timeout_1d: int = 30
    single_timeout_1h: int = 120
    single_timeout_30m: int = 180
    single_timeout_15m: int = 300
    single_timeout_5m: int = 600
    single_timeout_1m: int = 900

    @classmethod
    def default(cls) -> "EvolutionSettings":
        return cls()

    @staticmethod
    def bar_seconds(timeframe: str) -> int:
        return {"1d": 86400, "1h": 3600, "30m": 1800, "15m": 900, "5m": 300, "1m": 60}.get(timeframe, 3600)

    @staticmethod
    def bars_per_year(timeframe: str) -> int:
        return int(365.25 * 86400 / EvolutionSettings.bar_seconds(timeframe))

    @staticmethod
    def tf_config(timeframe: str) -> dict:
        return _TIMEFRAME_CONFIGS.get(timeframe, _TIMEFRAME_CONFIGS["1h"])

    def get_default_population(self, timeframe: str) -> int:
        return getattr(self, f"default_population_{timeframe}", self.default_population_1h)

    def get_default_generations(self, timeframe: str) -> int:
        return getattr(self, f"default_generations_{timeframe}", self.default_generations_1h)

    def get_single_timeout(self, timeframe: str) -> int:
        return getattr(self, f"single_timeout_{timeframe}", self.single_timeout_1h)


SETTINGS = EvolutionSettings.default()
