import json
import math
import time
import threading
import asyncio
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from typing import Any, Optional

import pandas as pd

from database import sync_task_to_turso, get_db, get_turso, release_db, checkpoint_db, save_speed_record, get_avg_speed
from evolution.task_manager import TaskManager
from evolution.engine import EvolutionEngine
from evolution.models import TaskConfig, TaskStatus
from evolution.config import SETTINGS as EVO_SETTINGS
from data_fetcher import _BAR_SECONDS
from strategies.speed import get_speed_factor

router = APIRouter(prefix="/tasks", tags=["evolution"])
task_manager = TaskManager()
engine = EvolutionEngine()
_active_connections: dict[str, list[WebSocket]] = {}
_event_loop: asyncio.AbstractEventLoop | None = None


def set_event_loop(loop: asyncio.AbstractEventLoop):
    global _event_loop
    _event_loop = loop


def _notify_clients(task_id: str, data: dict):
    if _event_loop is None:
        return
    for ws in _active_connections.get(task_id, []):
        try:
            asyncio.run_coroutine_threadsafe(
                ws.send_text(json.dumps(data, ensure_ascii=False)), _event_loop
            )
        except Exception:
            pass


def _broadcast_generation(gen_result, task_id: str):
    if gen_result is None:
        return
    _notify_clients(task_id, {"type": "GENERATION_COMPLETED", "data": gen_result.model_dump()})


def _record_speed(task_id: str):
    try:
        task = task_manager.get_task(task_id)
        if not task or not task.started_at or not task.completed_at:
            return
        cfg = task.config
        if not cfg.symbols:
            return
        total_secs = task.completed_at - task.started_at
        if total_secs <= 0:
            return
        bar_s = _BAR_SECONDS.get(cfg.timeframe or "1d", 3600)
        start_ts = int(pd.Timestamp(cfg.start_date).timestamp())
        end_ts = int(pd.Timestamp(cfg.end_date).timestamp())
        bars_per_sym = max(1, (end_ts - start_ts) // bar_s)
        n_sym = len(cfg.symbols)
        pop = cfg.population_size or 200
        gens_done = task.current_generation or 1

        from strategies.base import get_strategy_module as _get_mod
        from evolution.config import SETTINGS as _EVO_SETTINGS
        conn = get_db()
        config_row = conn.execute(
            "SELECT template_id FROM strategy_configs WHERE config_id = ?",
            (cfg.strategy_config_id,),
        ).fetchone()
        conn.close()
        tid = (config_row["template_id"] or cfg.strategy_config_id) if config_row else cfg.strategy_config_id
        mod = _get_mod(tid)
        is_rotation = bool(mod and getattr(mod, "IS_ROTATION", False))

        n_windows = cfg.walk_forward_windows or 1
        total_bars = gens_done * pop * bars_per_sym
        if is_rotation:
            total_bars = int(total_bars * 1.5)
        else:
            total_bars = int(total_bars * n_sym * 2 * n_windows)

        save_speed_record(tid, task_id, float(total_bars), float(total_secs))
    except Exception:
        pass


def _run_task_background(task_id: str):
    started_at = int(time.time())
    task_manager.update_task(task_id, status="RUNNING", started_at=started_at)
    completed_msg = None
    try:
        def progress(gen, current, total):
            _notify_clients(task_id, {
                "type": "INDIVIDUAL_PROGRESS",
                "generation": gen,
                "current": current,
                "total": total,
            })
        engine.run_task(
            task_id,
            on_generation=lambda g: _broadcast_generation(g, task_id),
            on_progress=progress,
        )
        completed_msg = {"type": "TASK_COMPLETED", "task_id": task_id}
    except Exception as e:
        task_manager.fail_task(task_id, str(e))
        completed_msg = {"type": "TASK_FAILED", "task_id": task_id, "error": str(e)}

    # Record actual speed for future estimation calibration
    _record_speed(task_id)

    # Turso sync is best-effort: network errors must never flip a completed task to failed
    try:
        sync_task_to_turso(task_id)
    except Exception:
        pass
    finally:
        release_db()
        checkpoint_db()
        if completed_msg:
            _notify_clients(task_id, completed_msg)


class CreateTaskRequest(BaseModel):
    strategy_config_id: str
    symbols: list[str]
    start_date: str
    end_date: str
    timeframe: str = "1d"
    population_size: Optional[int] = None
    max_generations: Optional[int] = None
    crossover_rate: Optional[float] = None
    mutation_rate: Optional[float] = None
    early_stop_generations: Optional[int] = None
    seed_params: Optional[dict[str, Any]] = None


class EstimateRequest(BaseModel):
    strategy_config_id: str = ""
    symbols: list[str]
    start_date: str
    end_date: str
    timeframe: str = "1d"
    population_size: int = 200
    max_generations: int = 50
    walk_forward_windows: int = 1


def _get_template_id(config_id: str) -> tuple[Optional[str], Optional[dict]]:
    try:
        t = get_turso()
        row = t.execute(
            "SELECT template_id, parameters_json FROM strategy_configs WHERE config_id = ?",
            (config_id,),
        ).fetchone()
        if row:
            return row["template_id"] or config_id, row
    except Exception:
        pass
    conn = get_db()
    row = conn.execute(
        "SELECT template_id, parameters_json FROM strategy_configs WHERE config_id = ?",
        (config_id,),
    ).fetchone()
    conn.close()
    if row:
        return row["template_id"] or config_id, row
    return config_id, None


@router.post("/estimate")
def estimate_task(req: EstimateRequest):
    bar_s = _BAR_SECONDS.get(req.timeframe, 3600)
    start_ts = int(pd.Timestamp(req.start_date).timestamp())
    end_ts = int(pd.Timestamp(req.end_date).timestamp())
    bars_per_symbol = max(1, (end_ts - start_ts) // bar_s)

    workers = EVO_SETTINGS.max_workers
    pop = req.population_size
    n_sym = len(req.symbols)
    gens = req.max_generations
    n_windows = req.walk_forward_windows

    is_rotation = False
    template_id = ""
    if req.strategy_config_id:
        tid, _ = _get_template_id(req.strategy_config_id)
        template_id = tid or ""
        from strategies.base import get_strategy_module
        mod = get_strategy_module(template_id)
        is_rotation = bool(mod and getattr(mod, "IS_ROTATION", False))

    speed = get_avg_speed(template_id, get_speed_factor(template_id) * 95000.0)

    if is_rotation:
        rotation_overhead = 1.5
        total_bars_per_ind = bars_per_symbol * rotation_overhead
        total_bars_per_gen = pop * total_bars_per_ind
    else:
        backtests_per_ind = n_sym * 2 * n_windows
        total_bars_per_ind = bars_per_symbol * backtests_per_ind
        total_bars_per_gen = total_bars_per_ind * pop

    time_per_gen = total_bars_per_gen / workers / speed
    total_secs = gens * time_per_gen

    expected_gens = max(1, gens // 2)

    return {
        "estimated_seconds": round(total_secs),
        "expected_seconds": round(total_secs * expected_gens / gens),
        "bars_per_symbol": bars_per_symbol,
        "total_bars_per_backtest": total_bars_per_ind,
        "time_per_gen_sec": round(time_per_gen, 1),
        "num_workers": workers,
        "is_rotation": is_rotation,
        "speed_bps": round(speed, 1),
        "avg_gens_used": expected_gens,
    }


@router.post("")
def create_task(req: CreateTaskRequest):
    config = TaskConfig(**req.model_dump())
    task = task_manager.create_task(config)
    task_manager.update_task(task.task_id, status="RUNNING", started_at=int(time.time()))
    t = threading.Thread(target=_run_task_background, args=(task.task_id,), daemon=True)
    t.start()
    return task_manager.get_task(task.task_id)


@router.get("")
def list_tasks():
    return task_manager.list_tasks()


@router.get("/{task_id}")
def get_task(task_id: str):
    task = task_manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.delete("/{task_id}")
def cancel_task(task_id: str, purge: bool = False):
    if purge:
        import sqlite3 as _sqlite3
        from database import LOCAL_DB_PATH
        raw = _sqlite3.connect(LOCAL_DB_PATH, timeout=30.0)
        raw.row_factory = _sqlite3.Row
        raw.execute("PRAGMA journal_mode=WAL")
        try:
            raw.execute("DELETE FROM individuals WHERE task_id = ?", (task_id,))
            raw.execute("DELETE FROM task_generations WHERE task_id = ?", (task_id,))
            raw.execute("DELETE FROM pareto_fronts WHERE task_id = ?", (task_id,))
            raw.execute("DELETE FROM evolution_tasks WHERE task_id = ?", (task_id,))
            raw.commit()
        finally:
            raw.close()
        try:
            t = get_turso()
            t.execute("DELETE FROM evolution_task_results WHERE task_id = ?", (task_id,))
        except Exception:
            pass
        return {"detail": "Task purged"}
    ok = task_manager.cancel_task(task_id)
    if not ok:
        raise HTTPException(status_code=400, detail="Cannot cancel task")
    _notify_clients(task_id, {"type": "TASK_CANCELLED", "task_id": task_id})
    return {"detail": "Task cancelled"}


@router.get("/{task_id}/results")
def get_results(task_id: str):
    task = task_manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    generations = task_manager.get_generations(task_id)
    return {
        "task": task,
        "generations": generations,
    }


@router.post("/{task_id}/run")
def run_task(task_id: str):
    task = task_manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.status != TaskStatus.QUEUED:
        raise HTTPException(status_code=400, detail=f"Task status is {task.status}, not QUEUED")
    t = threading.Thread(target=_run_task_background, args=(task_id,), daemon=True)
    t.start()
    return task_manager.get_task(task_id)


@router.post("/run-next")
def run_next_task():
    task = task_manager.dequeue_and_run()
    if not task:
        raise HTTPException(status_code=404, detail="No queued tasks")
    t = threading.Thread(target=_run_task_background, args=(task.task_id,), daemon=True)
    t.start()
    return task_manager.get_task(task.task_id)


@router.websocket("/{task_id}/stream")
async def task_websocket(websocket: WebSocket, task_id: str):
    await websocket.accept()
    # If task already finished, tell the client immediately so it doesn't hang
    task = task_manager.get_task(task_id)
    if task:
        if task.status == TaskStatus.COMPLETED:
            await websocket.send_text(json.dumps({"type": "TASK_COMPLETED", "task_id": task_id}))
            return
        elif task.status == TaskStatus.FAILED:
            await websocket.send_text(json.dumps({"type": "TASK_FAILED", "task_id": task_id, "error": task.error_message or ""}))
            return
        elif task.status == TaskStatus.CANCELLED:
            await websocket.send_text(json.dumps({"type": "TASK_CANCELLED", "task_id": task_id}))
            return
    if task_id not in _active_connections:
        _active_connections[task_id] = []
    _active_connections[task_id].append(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        if websocket in _active_connections.get(task_id, []):
            _active_connections[task_id].remove(websocket)
