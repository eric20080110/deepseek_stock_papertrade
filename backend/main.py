import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from database import init_db, sync_strategies_to_local, checkpoint_db
from seed import seed_templates
from routes.strategies import router as strategies_router
from routes.backtest import router as backtest_router
from routes.param_space import router as param_space_router
from routes.fitness import router as fitness_router
from routes.evolution import router as evolution_router
from routes.evolution import set_event_loop
from routes.analysis import router as analysis_router
from routes.paper_trading import router as paper_trading_router
from routes.paper_trading import engine as paper_engine
from routes.paper_trading import set_event_loop as set_pt_event_loop
from routes.gene_pool import router as gene_pool_router
from routes.symbols import router as symbols_router
from routes.live_trading import router as live_trading_router
from live_trading.engine import LiveTradingEngine
from live_trading.scheduler import LiveScheduler
from live_trading.order_processor import LiveOrderProcessor
from paper_trading.ticker import PaperTicker

ticker = PaperTicker(paper_engine)
live_engine = LiveTradingEngine()
live_scheduler = LiveScheduler(live_engine)
live_order_processor = LiveOrderProcessor()


@asynccontextmanager
async def lifespan(app: FastAPI):
    loop = asyncio.get_running_loop()
    set_event_loop(loop)
    set_pt_event_loop(loop)
    init_db()
    checkpoint_db()
    seed_templates()
    ticker.start()
    live_scheduler.start()
    live_order_processor.start()
    yield
    await ticker.stop()
    await live_scheduler.stop()
    await live_order_processor.stop()


app = FastAPI(title="QuantGene Platform", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(strategies_router)
app.include_router(backtest_router)
app.include_router(param_space_router)
app.include_router(fitness_router)
app.include_router(evolution_router)
app.include_router(analysis_router)
app.include_router(paper_trading_router)
app.include_router(gene_pool_router)
app.include_router(symbols_router)
app.include_router(live_trading_router)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/system/vacuum")
def vacuum_db():
    """Reclaim free space after deleting tasks. Requires no other connections on the DB."""
    import sqlite3 as _sq
    from database import LOCAL_DB_PATH
    try:
        c = _sq.connect(LOCAL_DB_PATH, timeout=5)
        c.execute("VACUUM")
        c.close()
        return {"detail": "VACUUM completed"}
    except Exception as e:
        from fastapi import HTTPException
        raise HTTPException(503, f"VACUUM failed (close DBeaver first): {e}")


@app.get("/system/db-status")
def db_status():
    import os, time
    from database import LOCAL_DB_PATH, TURSO_URL, TURSO_TOKEN, get_db, get_turso

    # --- Local SQLite ---
    local_ok = False
    local_size_bytes = 0
    local_rows: dict[str, int] = {}
    try:
        conn = get_db()
        local_ok = True
        local_size_bytes = os.path.getsize(LOCAL_DB_PATH) if os.path.exists(LOCAL_DB_PATH) else 0
        for tbl in ("evolution_tasks", "individuals", "strategy_configs", "paper_instances",
                    "virtual_trades", "paper_equity_history", "ohlcv_data"):
            try:
                r = conn.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()
                local_rows[tbl] = r[0] if r else 0
            except Exception:
                local_rows[tbl] = 0
        conn.close()
    except Exception as e:
        local_ok = False

    def _fmt(b: int) -> str:
        if b >= 1 << 30:
            return f"{b / (1 << 30):.1f} GB"
        if b >= 1 << 20:
            return f"{b / (1 << 20):.1f} MB"
        if b >= 1 << 10:
            return f"{b / (1 << 10):.1f} KB"
        return f"{b} B"

    # --- Turso ---
    turso_configured = bool(TURSO_URL and TURSO_TOKEN)
    turso_ok = False
    turso_rows: dict[str, int] = {}
    turso_latency_ms: float | None = None
    if turso_configured:
        try:
            t = get_turso()
            t0 = time.monotonic()
            for tbl in ("strategy_configs", "paper_instances", "virtual_trades", "paper_equity_history"):
                try:
                    r = t.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()
                    turso_rows[tbl] = r[0] if r else 0
                except Exception:
                    turso_rows[tbl] = 0
            turso_latency_ms = round((time.monotonic() - t0) * 1000)
            turso_ok = True
        except Exception:
            turso_ok = False

    return {
        "local": {
            "connected": local_ok,
            "size": _fmt(local_size_bytes),
            "size_bytes": local_size_bytes,
            "rows": local_rows,
        },
        "turso": {
            "configured": turso_configured,
            "connected": turso_ok,
            "latency_ms": turso_latency_ms,
            "rows": turso_rows,
        },
    }
