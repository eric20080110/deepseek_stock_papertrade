import json
import math
import time
import threading
import asyncio
from fastapi import APIRouter, BackgroundTasks, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from typing import Any, Optional

import pandas as pd

from database import sync_task_to_turso, get_db, get_turso, release_db, checkpoint_db
from evolution.task_manager import TaskManager
from evolution.engine import EvolutionEngine
from evolution.models import TaskConfig, TaskStatus
from evolution.config import SETTINGS as EVO_SETTINGS
from data_fetcher import _BAR_SECONDS

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


def _run_task_background(task_id: str):
    task_manager.update_task(task_id, status="RUNNING", started_at=int(time.time()))
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
        sync_task_to_turso(task_id)
        completed_msg = {"type": "TASK_COMPLETED", "task_id": task_id}
    except Exception as e:
        task_manager.fail_task(task_id, str(e))
        completed_msg = {"type": "TASK_FAILED", "task_id": task_id, "error": str(e)}
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
    symbols: list[str]
    start_date: str
    end_date: str
    timeframe: str = "1d"
    population_size: int = 200
    max_generations: int = 50


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

    bars_per_second = 95000.0
    backtests_per_ind = n_sym
    batches = math.ceil(pop / workers)
    time_per_gen = batches * backtests_per_ind * bars_per_symbol / bars_per_second
    total_secs = gens * time_per_gen * 1.25

    return {
        "estimated_seconds": round(total_secs),
        "bars_per_symbol": bars_per_symbol,
        "total_bars_per_backtest": bars_per_symbol * n_sym,
        "time_per_gen_sec": round(time_per_gen, 1),
        "num_workers": workers,
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


def _vacuum_after_purge():
    import sqlite3 as _sqlite3
    from database import LOCAL_DB_PATH
    try:
        c = _sqlite3.connect(LOCAL_DB_PATH, timeout=60)
        c.execute("VACUUM")
        c.close()
    except Exception:
        pass


@router.delete("/{task_id}")
def cancel_task(task_id: str, background_tasks: BackgroundTasks, purge: bool = False):
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
        background_tasks.add_task(_vacuum_after_purge)
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
