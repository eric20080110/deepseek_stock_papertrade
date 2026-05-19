import json
import time
import uuid
from typing import Optional

from database import get_db
from evolution.models import EvolutionTask, TaskConfig, TaskStatus


class TaskManager:
    def __init__(self):
        self._running_task: Optional[EvolutionTask] = None

    def create_task(self, config: TaskConfig) -> EvolutionTask:
        conn = get_db()
        task_id = str(uuid.uuid4())
        now = int(time.time())
        row = conn.execute(
            "SELECT name FROM strategy_configs WHERE config_id = ?",
            (config.strategy_config_id,),
        ).fetchone()
        default_name = row["name"] if row else task_id[:8]
        conn.execute(
            """INSERT INTO evolution_tasks
               (task_id, status, created_at, config_json, total_generations, name)
               VALUES (?, 'QUEUED', ?, ?, ?, ?)""",
            (task_id, now, config.model_dump_json(), config.max_generations or 0, default_name),
        )
        conn.commit()
        conn.close()
        return self.get_task(task_id)

    def get_task(self, task_id: str) -> Optional[EvolutionTask]:
        conn = get_db()
        row = conn.execute(
            "SELECT * FROM evolution_tasks WHERE task_id = ?", (task_id,)
        ).fetchone()
        conn.close()
        if not row:
            return None
        return self._row_to_task(row)

    def list_tasks(self) -> list[EvolutionTask]:
        conn = get_db()
        rows = conn.execute(
            "SELECT * FROM evolution_tasks ORDER BY created_at DESC"
        ).fetchall()
        conn.close()
        return [t for r in rows if (t := self._row_to_task(r)) is not None]

    def update_task(self, task_id: str, **kwargs):
        conn = get_db()
        sets = ", ".join(f"{k} = ?" for k in kwargs)
        vals = list(kwargs.values()) + [task_id]
        conn.execute(
            f"UPDATE evolution_tasks SET {sets} WHERE task_id = ?", vals
        )
        conn.commit()
        conn.close()

    def cancel_task(self, task_id: str) -> bool:
        task = self.get_task(task_id)
        if not task:
            return False
        if task.status == TaskStatus.COMPLETED:
            return False
        self.update_task(task_id, status="CANCELLED", completed_at=int(time.time()))
        if self._running_task and self._running_task.task_id == task_id:
            self._running_task = None
        return True

    def save_generation(self, task_id: str, generation: int, result: dict):
        conn = get_db()
        conn.execute(
            """INSERT INTO task_generations (task_id, generation, result_json, created_at)
               VALUES (?, ?, ?, ?)""",
            (task_id, generation, json.dumps(result), int(time.time())),
        )
        conn.commit()
        conn.close()

    def get_next_queued(self) -> Optional[EvolutionTask]:
        conn = get_db()
        row = conn.execute(
            "SELECT * FROM evolution_tasks WHERE status = 'QUEUED' ORDER BY created_at ASC LIMIT 1"
        ).fetchone()
        conn.close()
        if not row:
            return None
        return self._row_to_task(row)

    def dequeue_and_run(self) -> Optional[EvolutionTask]:
        if self._running_task and self._running_task.status == TaskStatus.RUNNING:
            return None
        task = self.get_next_queued()
        if not task:
            return None
        now = int(time.time())
        self.update_task(
            task.task_id,
            status="RUNNING",
            started_at=now,
            current_generation=0,
            progress_pct=0.0,
        )
        task.status = TaskStatus.RUNNING
        task.started_at = now
        self._running_task = task
        return task

    def complete_task(self, task_id: str, summary: dict):
        now = int(time.time())
        self.update_task(
            task_id,
            status="COMPLETED",
            completed_at=now,
            progress_pct=100.0,
            result_summary_json=json.dumps(summary),
        )
        if self._running_task and self._running_task.task_id == task_id:
            self._running_task = None

    def fail_task(self, task_id: str, error: str):
        now = int(time.time())
        self.update_task(
            task_id,
            status="FAILED",
            completed_at=now,
            error_message=error,
        )
        if self._running_task and self._running_task.task_id == task_id:
            self._running_task = None

    def save_individuals(self, task_id: str, generation: int, individuals: list[dict]):
        conn = get_db()
        rows = []
        for ind in individuals:
            rows.append((
                task_id, generation,
                ind.get("strategy_id", ""),
                json.dumps(ind.get("params", {})),
                ind.get("pareto_rank"),
                ind.get("crowding_distance"),
                1 if ind.get("is_elite") else 0,
                ind.get("cagr", 0),
                ind.get("max_drawdown", 0),
                ind.get("sharpe_ratio", 0),
                ind.get("profit_factor", 0),
                ind.get("win_rate", 0),
                ind.get("r2", 0),
                ind.get("trade_count", 0),
                ind.get("oos_consistency_score", 0),
                1 if ind.get("passed_absolute") else 0,
                1 if ind.get("passed_dynamic") else 0,
                ind.get("elimination_reason"),
                json.dumps({
                    "v": ind.get("equity_curve", []),
                    "t": ind.get("equity_timestamps", []),
                }) if ind.get("equity_curve") else None,
                json.dumps(ind.get("symbol_results", {})) if ind.get("symbol_results") else None,
            ))
        conn.executemany(
            """INSERT INTO individuals
               (task_id, generation, strategy_id, params_json,
                pareto_rank, crowding_distance, is_elite,
                cagr, max_drawdown, sharpe_ratio, profit_factor,
                win_rate, r2, trade_count, oos_consistency_score,
                passed_absolute, passed_dynamic, elimination_reason,
                equity_curve_json, symbol_results_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            rows,
        )
        conn.commit()
        conn.close()

    def save_pareto_front(self, task_id: str, generation: int, front_data: list[dict]):
        conn = get_db()
        conn.execute(
            """INSERT INTO pareto_fronts (task_id, generation, front_json)
               VALUES (?, ?, ?)""",
            (task_id, generation, json.dumps(front_data)),
        )
        conn.commit()
        conn.close()

    def get_individuals(
        self, task_id: str, generation: int = None, pareto_rank: int = None,
        elite_only: bool = False, limit: int = 1000, offset: int = 0,
    ) -> list[dict]:
        conn = get_db()
        conditions = ["task_id = ?"]
        params = [task_id]
        if generation is not None:
            conditions.append("generation = ?")
            params.append(generation)
        if pareto_rank is not None:
            conditions.append("pareto_rank = ?")
            params.append(pareto_rank)
        if elite_only:
            conditions.append("is_elite = 1")
        sql = f"SELECT * FROM individuals WHERE {' AND '.join(conditions)} ORDER BY generation DESC, pareto_rank ASC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        rows = conn.execute(sql, params).fetchall()
        conn.close()
        result = []
        for r in rows:
            d = dict(r)
            # Strip large blob fields from list responses — use /equity-curve endpoint instead
            d.pop("equity_curve_json", None)
            d.pop("symbol_results_json", None)
            result.append(d)
        return result

    def get_pareto_fronts(self, task_id: str) -> list[dict]:
        conn = get_db()
        rows = conn.execute(
            "SELECT * FROM pareto_fronts WHERE task_id = ? ORDER BY generation ASC",
            (task_id,),
        ).fetchall()
        conn.close()
        result = []
        for r in rows:
            d = dict(r)
            d["front_data"] = json.loads(d.pop("front_json"))
            result.append(d)
        return result

    def get_generations(self, task_id: str) -> list[dict]:
        conn = get_db()
        rows = conn.execute(
            "SELECT * FROM task_generations WHERE task_id = ? ORDER BY generation ASC",
            (task_id,),
        ).fetchall()
        conn.close()
        return [json.loads(r["result_json"]) for r in rows]

    def _row_to_task(self, row) -> Optional[EvolutionTask]:
        config_dict = json.loads(row["config_json"])
        try:
            status = TaskStatus(row["status"])
        except ValueError:
            return None
        return EvolutionTask(
            task_id=row["task_id"],
            status=status,
            created_at=row["created_at"],
            started_at=row["started_at"],
            completed_at=row["completed_at"],
            config=TaskConfig(**config_dict),
            current_generation=row["current_generation"] or 0,
            total_generations=row["total_generations"] or 0,
            progress_pct=row["progress_pct"] or 0.0,
            error_message=row["error_message"],
            result_summary=json.loads(row["result_summary_json"]) if row["result_summary_json"] else None,
            name=row["name"] if "name" in row.keys() else None,
        )
