import random
import numpy as np
from typing import Optional

from param_space.space import ParameterSpace
from evolution.config import SETTINGS
from fitness.models import IndividualScore


class GeneticOperators:
    def __init__(self, param_space: ParameterSpace):
        self.param_space = param_space
        self.mutation_rate = SETTINGS.default_mutation_rate
        self.crossover_count = 0
        self.mutation_count = 0
        self.repair_count = 0
        self.resample_count = 0
        self._stagnant_generations = 0
        self._base_mutation_rate = SETTINGS.default_mutation_rate

    def tournament_select(
        self, scored: list[IndividualScore], pool_size: int
    ) -> list[IndividualScore]:
        pool = []
        for _ in range(pool_size):
            k = min(SETTINGS.tournament_k, len(scored))
            contestants = random.sample(scored, k)
            best = min(contestants, key=lambda s: (
                s.pareto_rank or 999,
                -(s.crowding_distance or 0),
            ))
            pool.append(best)
        return pool

    def crossover(
        self, parent_a: dict, parent_b: dict
    ) -> tuple[dict, dict]:
        vec_a = self.param_space.encode(parent_a)
        vec_b = self.param_space.encode(parent_b)

        mask = np.random.random(len(vec_a)) < 0.5
        child1_vec = np.where(mask, vec_a, vec_b)
        child2_vec = np.where(~mask, vec_a, vec_b)

        child1 = self.param_space.decode(child1_vec)
        child2 = self.param_space.decode(child2_vec)

        self.crossover_count += 1
        return child1, child2

    def mutate(self, params: dict) -> dict:
        vec = self.param_space.encode(params)
        for i in range(len(vec)):
            if random.random() < self.mutation_rate:
                vec[i] = self._mutate_value(vec[i], i)
        decoded = self.param_space.decode(vec)
        self.mutation_count += 1
        return decoded

    def _mutate_value(self, val: float, idx: int) -> float:
        noise = np.random.normal(0, abs(val) * 0.1 + 0.01)
        return val + noise

    def produce_offspring(
        self,
        parent_pool: list[IndividualScore],
        parent_params: dict[str, dict],
        target_count: int,
    ) -> list[dict]:
        offspring: list[dict] = []
        attempts = 0
        max_attempts = target_count * 10

        while len(offspring) < target_count and attempts < max_attempts:
            attempts += 1
            a, b = random.sample(parent_pool, 2)
            pa = parent_params.get(a.strategy_id, {})
            pb = parent_params.get(b.strategy_id, {})

            if random.random() < SETTINGS.default_crossover_rate:
                c1, c2 = self.crossover(pa, pb)
                candidates = [c1, c2]
            else:
                candidates = [dict(pa), dict(pb)]

            for child in candidates:
                child = self.mutate(child)
                repair_result = self.param_space.repair(child)
                self.repair_count += 1
                if repair_result.get("resampled"):
                    self.resample_count += 1
                final_params = repair_result.get("params", child)
                offspring.append(final_params)
                if len(offspring) >= target_count:
                    break

        while len(offspring) < target_count:
            ind = self.param_space.sample()
            offspring.append(ind.params)
            self.resample_count += 1

        return offspring[:target_count]

    def adapt_mutation_rate(self, front_improved: bool):
        if front_improved:
            self._stagnant_generations = 0
            self.mutation_rate = self._base_mutation_rate
        else:
            self._stagnant_generations += 1
            if self._stagnant_generations >= 3:
                self.mutation_rate = min(
                    self._base_mutation_rate * SETTINGS.adaptive_mutation_multiplier,
                    SETTINGS.adaptive_mutation_max,
                )

    def reset_stats(self):
        self.crossover_count = 0
        self.mutation_count = 0
        self.repair_count = 0
        self.resample_count = 0
