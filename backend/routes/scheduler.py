import json
import threading
import time
import os
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from database import get_db, get_turso

router = APIRouter()

_scheduler_thread: threading.Thread | None = None
_scheduler_stop = threading.Event()

SCHEDULE_DB_PATH = os.environ.get("LOCAL_DB_PATH", "")

class ScheduleRule(BaseModel):
    rule_id: str | None = None
    strategy_config_id: str
    symbols: list[str]
    start_date: str
    end_date: str
    timeframe: str = "1d"
    population_size: int = 200
    max_generations: int = 50
    cron_expr: str = "0 0 * * 1"
    enabled: bool = True
    last_run_at: int | None = None
    next_run_at: int | None = None
    name: str = ""

def _init_schedule_table():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS task_schedules (
            rule_id TEXT PRIMARY KEY,
            strategy_config_id TEXT NOT NULL,
            symbols TEXT NOT NULL DEFAULT '[]',
            start_date TEXT NOT NULL,
            end_date TEXT NOT NULL,
            timeframe TEXT DEFAULT '1d',
            population_size INTEGER DEFAULT 200,
            max_generations INTEGER DEFAULT 50,
            cron_expr TEXT NOT NULL,
            enabled INTEGER DEFAULT 1,
            last_run_at INTEGER,
            next_run_at INTEGER,
            name TEXT DEFAULT ''
        )
    """)
    conn.commit()

def _parse_cron_minute(cron_expr: str) -> int:
    parts = cron_expr.strip().split()
    if len(parts) < 2:
        return 0
    try:
        return int(parts[0])
    except ValueError:
        return 0

def _parse_cron_hour(cron_expr: str) -> int:
    parts = cron_expr.strip().split()
    if len(parts) < 2:
        return 0
    try:
        return int(parts[1])
    except ValueError:
        return 0

def _parse_cron_dow(cron_expr: str) -> int | None:
    parts = cron_expr.strip().split()
    if len(parts) < 3:
        return None
    try:
        return int(parts[2])
    except ValueError:
        return None

def _compute_next_run(cron_expr: str) -> int:
    now = time.time()
    minute = _parse_cron_minute(cron_expr)
    hour = _parse_cron_hour(cron_expr)
    dow = _parse_cron_dow(cron_expr)

    from datetime import datetime, timedelta
    dt = datetime.fromtimestamp(now)

    if dow is not None:
        days_ahead = (dow - dt.weekday()) % 7
        if days_ahead == 0 and (dt.hour > hour or (dt.hour == hour and dt.minute >= minute)):
            days_ahead = 7
        next_dt = dt.replace(hour=hour, minute=minute, second=0, microsecond=0) + timedelta(days=days_ahead)
    else:
        next_dt = dt.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if next_dt <= dt:
            next_dt += timedelta(days=1)

    return int(next_dt.timestamp())

def _run_scheduled_tasks():
    conn = get_db()
    rows = conn.execute("SELECT * FROM task_schedules WHERE enabled = 1").fetchall()
    now = int(time.time())
    for row in rows:
        next_run = row["next_run_at"] or _compute_next_run(row["cron_expr"])
        if now >= next_run:
            config = {
                "strategy_config_id": row["strategy_config_id"],
                "symbols": json.loads(row["symbols"]) if isinstance(row["symbols"], str) else row["symbols"],
                "start_date": row["start_date"],
                "end_date": row["end_date"],
                "timeframe": row["timeframe"],
                "population_size": row["population_size"],
                "max_generations": row["max_generations"],
            }
            try:
                import urllib.request
                api_url = os.environ.get("API_URL", "http://localhost:8000")
                body = json.dumps(config).encode("utf-8")
                req = urllib.request.Request(
                    f"{api_url}/tasks",
                    data=body,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                urllib.request.urlopen(req, timeout=30)
                new_next = _compute_next_run(row["cron_expr"])
                conn.execute(
                    "UPDATE task_schedules SET last_run_at = ?, next_run_at = ? WHERE rule_id = ?",
                    (now, new_next, row["rule_id"]),
                )
                conn.commit()
            except Exception as e:
                print(f"[scheduler] task creation failed for {row['rule_id']}: {e}")

def _scheduler_loop():
    _init_schedule_table()
    while not _scheduler_stop.is_set():
        _run_scheduled_tasks()
        _scheduler_stop.wait(300)

@router.on_event("startup")
def start_scheduler():
    global _scheduler_thread
    if _scheduler_thread is None or not _scheduler_thread.is_alive():
        _scheduler_stop.clear()
        _scheduler_thread = threading.Thread(target=_scheduler_loop, daemon=True)
        _scheduler_thread.start()

@router.on_event("shutdown")
def stop_scheduler():
    _scheduler_stop.set()

@router.get("/schedules")
def list_schedules():
    _init_schedule_table()
    conn = get_db()
    rows = conn.execute("SELECT * FROM task_schedules ORDER BY next_run_at ASC").fetchall()
    return [dict(r) for r in rows]

@router.post("/schedules")
def create_schedule(rule: ScheduleRule):
    import uuid
    _init_schedule_table()
    rule_id = rule.rule_id or f"sched_{uuid.uuid4().hex[:12]}"
    next_run = _compute_next_run(rule.cron_expr)
    conn = get_db()
    conn.execute(
        "INSERT INTO task_schedules (rule_id, strategy_config_id, symbols, start_date, end_date, timeframe, population_size, max_generations, cron_expr, enabled, next_run_at, name) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (rule_id, rule.strategy_config_id, json.dumps(rule.symbols), rule.start_date, rule.end_date, rule.timeframe, rule.population_size, rule.max_generations, rule.cron_expr, 1 if rule.enabled else 0, next_run, rule.name),
    )
    conn.commit()
    return {"rule_id": rule_id}

@router.delete("/schedules/{rule_id}")
def delete_schedule(rule_id: str):
    conn = get_db()
    conn.execute("DELETE FROM task_schedules WHERE rule_id = ?", (rule_id,))
    conn.commit()
    return {"detail": "deleted"}

@router.put("/schedules/{rule_id}/toggle")
def toggle_schedule(rule_id: str):
    conn = get_db()
    row = conn.execute("SELECT enabled FROM task_schedules WHERE rule_id = ?", (rule_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Schedule not found")
    new_val = 0 if row["enabled"] else 1
    conn.execute("UPDATE task_schedules SET enabled = ? WHERE rule_id = ?", (new_val, rule_id))
    conn.commit()
    return {"enabled": bool(new_val)}
