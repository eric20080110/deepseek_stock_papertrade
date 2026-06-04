import json
from fastapi import APIRouter
from database import get_db, get_live_db

router = APIRouter()

@router.get("/dashboard/stats")
def dashboard_stats():
    conn = get_db()

    total_tasks = conn.execute("SELECT COUNT(*) FROM evolution_tasks").fetchone()[0]
    running_tasks = conn.execute("SELECT COUNT(*) FROM evolution_tasks WHERE status='RUNNING'").fetchone()[0]
    completed_tasks = conn.execute("SELECT COUNT(*) FROM evolution_tasks WHERE status='COMPLETED'").fetchone()[0]
    failed_tasks = conn.execute("SELECT COUNT(*) FROM evolution_tasks WHERE status='FAILED'").fetchone()[0]

    paper_instances = conn.execute("SELECT COUNT(*) FROM paper_instances").fetchone()[0]
    paper_running = conn.execute("SELECT COUNT(*) FROM paper_instances WHERE status='RUNNING'").fetchone()[0]

    paper_equity = conn.execute("SELECT COALESCE(SUM(total_equity), 0) FROM paper_instances WHERE status='RUNNING'").fetchone()[0]
    paper_initial = conn.execute("SELECT COALESCE(SUM(initial_capital), 0) FROM paper_instances WHERE status='RUNNING'").fetchone()[0]
    paper_return_pct = ((paper_equity / paper_initial) - 1) * 100 if paper_initial > 0 else 0

    best = conn.execute("""
        SELECT strategy_id, cagr, sharpe_ratio, max_drawdown FROM individuals
        WHERE pareto_rank = 1 ORDER BY cagr DESC LIMIT 1
    """).fetchone()

    try:
        live_conn = get_live_db()
        live_instances = live_conn.execute("SELECT COUNT(*) FROM live_instances").fetchone()[0]
        live_running = live_conn.execute("SELECT COUNT(*) FROM live_instances WHERE status='RUNNING'").fetchone()[0]
        live_equity = live_conn.execute("SELECT COALESCE(SUM(total_equity), 0) FROM live_instances WHERE status='RUNNING'").fetchone()[0]
    except Exception:
        live_instances = live_running = live_equity = 0

    recent = conn.execute("""
        SELECT task_id, status, created_at, current_generation, total_generations, progress_pct, config_json
        FROM evolution_tasks ORDER BY created_at DESC LIMIT 5
    """).fetchall()

    recent_tasks = []
    for r in recent:
        cfg = json.loads(r["config_json"]) if isinstance(r["config_json"], str) else (r["config_json"] or {})
        recent_tasks.append({
            "task_id": r["task_id"],
            "status": r["status"],
            "created_at": r["created_at"],
            "progress": f"{r['current_generation']}/{r['total_generations']}",
            "progress_pct": r["progress_pct"],
            "symbols": cfg.get("symbols", []),
            "timeframe": cfg.get("timeframe", ""),
        })

    return {
        "tasks": {
            "total": total_tasks,
            "running": running_tasks,
            "completed": completed_tasks,
            "failed": failed_tasks,
        },
        "paper": {
            "instances": paper_instances,
            "running": paper_running,
            "total_equity": round(paper_equity, 2),
            "total_return_pct": round(paper_return_pct, 2),
        },
        "live": {
            "instances": live_instances,
            "running": live_running,
            "total_equity": round(live_equity, 2),
        },
        "best_champion": {
            "strategy_id": best["strategy_id"] if best else None,
            "cagr": round(best["cagr"] * 100, 2) if best else 0,
            "sharpe": round(best["sharpe_ratio"], 2) if best else 0,
            "max_drawdown": round(best["max_drawdown"], 2) if best else 0,
        } if best else None,
        "recent_tasks": recent_tasks,
    }
