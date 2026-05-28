import json
import time
import pandas as pd
from typing import Optional

from profile_helper import log as _plog

from param_space.space import ParameterSpace
from models import (
    ContinuousParam, IntegerParam, CategoricalParam, BooleanParam,
    OrderingConstraint, ConditionalConstraint, CategoricalGroupConstraint,
)

from backtest.engine import run_backtest
from backtest.data_cache import DATA_CACHE

from fitness.scoring import FitnessScorer, score_individuals
from fitness.config import FitnessSettings

from evolution.config import SETTINGS as EVO_SETTINGS
from evolution.models import EvolutionTask, TaskConfig, GenerationResult
from evolution.operators import GeneticOperators
from evolution.scheduler import ParallelScheduler
from evolution.task_manager import TaskManager


def _parse_param_defs(parameters: list[dict], constraints: list[dict]) -> ParameterSpace:
    parsed_params = []
    for p in parameters:
        t = p["type"]
        if t == "continuous":
            parsed_params.append(ContinuousParam(**p))
        elif t == "integer":
            parsed_params.append(IntegerParam(**p))
        elif t == "categorical":
            parsed_params.append(CategoricalParam(**p))
        elif t == "boolean":
            parsed_params.append(BooleanParam(**p))
    parsed_constraints = []
    for c in constraints:
        ct = c["type"]
        if ct == "ordering":
            parsed_constraints.append(OrderingConstraint(**c))
        elif ct == "conditional":
            parsed_constraints.append(ConditionalConstraint(**c))
        elif ct == "categorical_group":
            parsed_constraints.append(CategoricalGroupConstraint(**c))
    return ParameterSpace(parsed_params, parsed_constraints)


def _create_walk_forward_windows(
    data_map: dict[str, pd.DataFrame],
    n_windows: int,
    train_pct: float = 0.7,
) -> list[tuple[dict[str, pd.DataFrame], dict[str, pd.DataFrame]]]:
    """Split data into N walk-forward windows. Each window: IS = train_pct, OOS = 1-train_pct.
    Windows are anchored at the end of the data and slide backward.
    Returns list of (is_map, oos_map) tuples."""
    min_len = min(len(df) for df in data_map.values())
    if min_len < 100 or n_windows <= 1:
        oos_cut = int(min_len * max(train_pct, 0.5))
        is_map = {sym: df.iloc[:oos_cut] for sym, df in data_map.items()}
        oos_map = {sym: df.iloc[oos_cut:] for sym, df in data_map.items()}
        if any(len(df) < 2 for df in oos_map.values()):
            oos_map = {}
        return [(is_map, oos_map)]

    oos_frac = 1.0 - train_pct
    each_oos = max(50, int(min_len * oos_frac / n_windows))
    each_is = int(each_oos * train_pct / oos_frac)
    step = each_oos

    windows = []
    for w in range(n_windows):
        end = min_len - (n_windows - w - 1) * step
        start = max(0, end - each_is - each_oos)
        mid = start + each_is
        is_map = {sym: df.iloc[start:mid] for sym, df in data_map.items()}
        oos_map = {sym: df.iloc[mid:end] for sym, df in data_map.items()}
        if any(len(df) < 2 for df in oos_map.values()):
            oos_map = {}
        windows.append((is_map, oos_map))
    return windows


class EvolutionEngine:
    def __init__(self):
        self.task_manager = TaskManager()
        self.fitness_scorer = FitnessScorer()
        self._is_running = False

    def _load_strategy_space(self, config_id: str) -> Optional[ParameterSpace]:
        from database import get_db
        conn = get_db()
        row = conn.execute(
            "SELECT * FROM strategy_configs WHERE config_id = ?", (config_id,)
        ).fetchone()
        conn.close()
        if not row:
            return None
        params = json.loads(row["parameters_json"])
        constraints = json.loads(row["constraints_json"])
        return _parse_param_defs(params, constraints)

    def _check_early_stop(
        self, current_front: list[dict], prev_front: list[dict], stagnant_count: int
    ) -> tuple[bool, int]:
        if not prev_front:
            return False, stagnant_count
        improved = False
        for cur in current_front:
            for prev in prev_front:
                if (cur["cagr"] >= prev["cagr"] and cur["dd"] <= prev["dd"]
                        and cur["sharpe"] >= prev["sharpe"]):
                    improved = True
                    break
        if not improved:
            stagnant_count += 1
        else:
            stagnant_count = 0
        stop = stagnant_count >= (EVO_SETTINGS.default_early_stop_generations)
        return stop, stagnant_count

    def run_task(self, task_id: str, on_generation=None, on_progress=None) -> None:
        task = self.task_manager.get_task(task_id)
        if not task:
            return

        from database import get_db
        conn = get_db()
        config_row = conn.execute(
            "SELECT * FROM strategy_configs WHERE config_id = ?",
            (task.config.strategy_config_id,),
        ).fetchone()
        conn.close()
        if not config_row:
            self.task_manager.fail_task(task_id, f"Strategy config {task.config.strategy_config_id} not found")
            return
        template_id = config_row["template_id"] or config_row["config_id"]

        space = _parse_param_defs(
            json.loads(config_row["parameters_json"]),
            json.loads(config_row["constraints_json"]),
        )

        cfg = task.config
        timeframe = cfg.timeframe or "1d"
        pop_size = cfg.population_size or EVO_SETTINGS.get_default_population(timeframe)
        max_gen = cfg.max_generations or EVO_SETTINGS.get_default_generations(timeframe)
        early_stop = cfg.early_stop_generations or EVO_SETTINGS.default_early_stop_generations

        # Rotation strategies: always fetch their fixed symbol universe on daily bars
        from strategies.base import get_strategy_module as _get_mod
        _mod = _get_mod(template_id)
        if _mod and getattr(_mod, "IS_ROTATION", False):
            rot_syms = list(getattr(_mod, "ROTATION_SYMBOLS", cfg.symbols))
            spy_sym = getattr(_mod, "SPY_SYMBOL", "SPY")
            if spy_sym not in rot_syms:
                rot_syms.append(spy_sym)
            symbols = rot_syms
            timeframe = "1d"  # rotation indicators (SMA200, ROC63) require daily bars
        else:
            symbols = cfg.symbols

        data_map = {}
        _t0 = time.perf_counter()
        for sym in symbols:
            df = DATA_CACHE.ensure(
                sym,
                timeframe=timeframe,
                start_date=cfg.start_date,
                end_date=cfg.end_date,
            )
            if df is not None:
                DATA_CACHE.store(sym, df, timeframe=timeframe)
                data_map[sym] = df
        _t1 = time.perf_counter()
        _plog(f"Data fetch for {len(symbols)} symbols: {_t1-_t0:.2f}s")

        if not data_map:
            self.task_manager.fail_task(task_id, "No data available for any symbol")
            return

        walk_windows = _create_walk_forward_windows(data_map, cfg.walk_forward_windows)

        strategy_id = template_id

        operators = GeneticOperators(space)

        pop = []
        seed = task.config.seed_params
        if seed:
            space.repair(seed)
            pop.append(seed)
            for _ in range(pop_size - 1):
                child = operators.mutate(dict(seed))
                space.repair(child)
                pop.append(child)
        else:
            for _ in range(pop_size):
                ind = space.sample()
                pop.append(ind.params)

        prev_front: list[dict] = []
        stagnant_count = 0

        scheduler = ParallelScheduler()
        pool_total = 0.0
        score_total = 0.0
        save_total = 0.0
        select_total = 0.0

        try:
            for gen in range(max_gen):
                gen_start = time.perf_counter()

                _t0 = time.perf_counter()
                results = scheduler.run_backtests(
                    individuals=pop,
                    strategy_id=strategy_id,
                    symbols=symbols,
                    data_map=walk_windows[0][0],
                    oos_data_map=walk_windows[0][1],
                    walk_data_maps=walk_windows if len(walk_windows) > 1 else None,
                    on_progress=lambda i, t: on_progress(gen + 1, i, t) if on_progress else None,
                )
                _t1 = time.perf_counter()
                pool_total += _t1 - _t0

                if not results:
                    self.task_manager.fail_task(task_id, "All backtests failed")
                    return

                is_metrics = []
                oos_metrics = []
                for r in results:
                    wm = r["weighted_metrics"]
                    is_metrics.append({
                        "strategy_id": r["strategy_id"],
                        "annualized_return": wm.get("annualized_return", 0),
                        "sharpe_ratio": wm.get("sharpe_ratio", 0),
                        "max_drawdown": wm.get("max_drawdown", 0),
                        "profit_factor": wm.get("profit_factor", 0),
                        "win_rate": wm.get("win_rate", 0),
                        "trade_count": wm.get("trade_count", 0),
                        "equity_curve": wm.get("equity_curve", []),
                        "equity_timestamps": wm.get("equity_timestamps", []),
                    })
                    oos_wm = r.get("oos_metrics")
                    if oos_wm:
                        oos_metrics.append({
                            "strategy_id": r["strategy_id"],
                            "annualized_return": oos_wm.get("annualized_return", 0),
                            "sharpe_ratio": oos_wm.get("sharpe_ratio", 0),
                            "max_drawdown": oos_wm.get("max_drawdown", 0),
                        })
                    else:
                        oos_metrics.append({
                            "strategy_id": r["strategy_id"],
                            "annualized_return": 0,
                            "sharpe_ratio": 0,
                            "max_drawdown": 0,
                        })

                _t2 = time.perf_counter()
                scores, summary = score_individuals(is_metrics, oos_metrics)
                _t3 = time.perf_counter()
                score_total += _t3 - _t2

                survived = [s for s in scores if s.pareto_rank is not None]
                front = [s for s in survived if s.pareto_rank == 1]
                front_data = [
                    {"id": s.strategy_id, "cagr": s.objective_vector.cagr,
                     "dd": s.objective_vector.max_drawdown, "sharpe": s.objective_vector.sharpe,
                     "oos": s.oos_consistency_score}
                    for s in front
                ]

                ind_records = []
                for idx, (s, res_item) in enumerate(zip(scores, results)):
                    wm = res_item.get("weighted_metrics", {})
                    ind_records.append({
                        "strategy_id": s.strategy_id,
                        "params": pop[idx] if idx < len(pop) else {},
                        "pareto_rank": s.pareto_rank,
                        "crowding_distance": s.crowding_distance,
                        "is_elite": s.is_elite,
                        "cagr": s.objective_vector.cagr,
                        "max_drawdown": s.objective_vector.max_drawdown,
                        "sharpe_ratio": s.objective_vector.sharpe,
                        "profit_factor": s.threshold_metrics.profit_factor,
                        "win_rate": s.threshold_metrics.win_rate,
                        "r2": s.threshold_metrics.r2,
                        "trade_count": s.threshold_metrics.trade_count,
                        "oos_consistency_score": s.oos_consistency_score,
                        "passed_absolute": s.passed_absolute_threshold,
                        "passed_dynamic": s.passed_dynamic_threshold,
                        "elimination_reason": s.elimination_reason,
                        "equity_curve": wm.get("equity_curve", []),
                        "equity_timestamps": wm.get("equity_timestamps", []),
                        "symbol_results": res_item.get("symbol_results", {}),
                    })
                _t4 = time.perf_counter()
                self.task_manager.save_individuals(task_id, gen + 1, ind_records)
                self.task_manager.save_pareto_front(task_id, gen + 1, front_data)
                _t5 = time.perf_counter()
                save_total += _t5 - _t4

                gen_dur = time.perf_counter() - gen_start
                gen_result = GenerationResult(
                    generation=gen + 1,
                    total_generations=max_gen,
                    duration_sec=round(gen_dur, 4),
                    population_size=len(pop),
                    passed_absolute=summary.passed_absolute,
                    passed_dynamic=summary.passed_dynamic,
                    pareto_front_size=len(front),
                    pareto_front=front_data,
                    best_cagr=summary.best_cagr,
                    best_sharpe=summary.best_sharpe,
                    best_drawdown=summary.best_drawdown,
                    crossover_count=operators.crossover_count,
                    mutation_count=operators.mutation_count,
                    repair_count=operators.repair_count,
                    resample_count=operators.resample_count,
                    dynamic_thresholds=summary.dynamic_thresholds,
                )

                self.task_manager.save_generation(task_id, gen + 1, gen_result.model_dump())

                self.task_manager.update_task(
                    task_id,
                    current_generation=gen + 1,
                    progress_pct=round((gen + 1) / max_gen * 100, 1),
                )

                if on_generation:
                    on_generation(gen_result)

                task = self.task_manager.get_task(task_id)
                if task and task.status in ("CANCELLED",):
                    break

                should_stop, stagnant_count = self._check_early_stop(
                    front_data, prev_front, stagnant_count
                )
                prev_front = front_data
                operators.adapt_mutation_rate(not should_stop or gen == 0)

                if should_stop and gen + 1 < max_gen:
                    if on_generation:
                        on_generation(None, early_stop=True)
                    break

                elites = [s for s in front if s.is_elite]
                elite_params = []
                for s in elites:
                    idx = next((i for i, r in enumerate(results) if r["strategy_id"] == s.strategy_id), None)
                    if idx is not None and idx < len(pop):
                        elite_params.append(pop[idx])

                if not survived:
                    pop = [space.sample().params for _ in range(pop_size)]
                    operators.reset_stats()
                    continue

                _t6 = time.perf_counter()
                pool_size = int(pop_size * cfg.parent_pool_ratio)
                parent_pool = operators.tournament_select(survived, pool_size)

                parent_params = {}
                for s in parent_pool:
                    idx = next((i for i, r in enumerate(results) if r["strategy_id"] == s.strategy_id), None)
                    if idx is not None and idx < len(pop):
                        parent_params[s.strategy_id] = pop[idx]

                remaining = pop_size - len(elite_params)
                offspring = operators.produce_offspring(parent_pool, parent_params, remaining)
                pop = elite_params + offspring
                operators.reset_stats()
                _t7 = time.perf_counter()
                select_total += _t7 - _t6

            _plog(f"Task {task_id}: "
                  f"backtests={pool_total:.1f}s scoring={score_total:.1f}s "
                  f"save={save_total:.1f}s select={select_total:.1f}s "
                  f"total_per_gen={(pool_total+score_total+save_total+select_total)/max(gen+1,1):.2f}s/gen")

            task = self.task_manager.get_task(task_id)
            if task and task.status == "CANCELLED":
                return

            final_summary = {
                "total_generations": min(gen + 1, max_gen),
                "final_pareto_front": front_data,
                "best_cagr": summary.best_cagr,
                "best_sharpe": summary.best_sharpe,
                "best_drawdown": summary.best_drawdown,
            }
            self.task_manager.complete_task(task_id, final_summary)
        finally:
            scheduler.close()
