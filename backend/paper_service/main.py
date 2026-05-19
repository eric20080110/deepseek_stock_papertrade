import os, sys
# Add both this dir and the parent backend dir for imports
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_BACKEND_DIR = os.path.join(_THIS_DIR, "..")
sys.path.insert(0, _BACKEND_DIR)
sys.path.insert(0, _THIS_DIR)

import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from database import init_db, get_turso
from engine_state import engine
from paper_trading.ticker import PaperTicker  # uses backend's engine
from paper_trading.models import InstanceStatus
from routes.paper_trading import router as pt_router

logger = logging.getLogger(__name__)
ticker = PaperTicker(engine)
_startup_time: float = 0.0
_keepalive_task: asyncio.Task | None = None


async def _keepalive_loop():
    """Ping own /health every 10 min to prevent Render free-tier spin-down."""
    import urllib.request
    self_url = os.environ.get("RENDER_EXTERNAL_URL", "").rstrip("/")
    if not self_url:
        logger.info("RENDER_EXTERNAL_URL not set — keepalive disabled")
        return
    while True:
        await asyncio.sleep(240)
        try:
            urllib.request.urlopen(f"{self_url}/health", timeout=10)
            logger.debug("keepalive ping sent to %s", self_url)
        except Exception as e:
            logger.warning("keepalive ping failed: %s", e)


@asynccontextmanager
async def lifespan(app):
    global _keepalive_task, _startup_time
    import time as _time
    _startup_time = _time.time()
    configured = bool(os.environ.get("TURSO_URL") and os.environ.get("TURSO_TOKEN"))
    if configured:
        init_db()
        ticker.start()
        _keepalive_task = asyncio.create_task(_keepalive_loop())
        # Immediately tick all running instances on startup (covers gap when service was asleep)
        try:
            instances = engine.list_instances()
            for inst in instances:
                if inst.status == InstanceStatus.RUNNING:
                    try:
                        engine.tick(inst.instance_id)
                    except Exception:
                        pass
            logger.info("Startup tick complete for %d running instances", sum(1 for i in instances if i.status == InstanceStatus.RUNNING))
        except Exception as e:
            logger.warning("Startup tick failed: %s", e)
    yield
    if _keepalive_task:
        _keepalive_task.cancel()
        try:
            await _keepalive_task
        except asyncio.CancelledError:
            pass
    if configured:
        await ticker.stop()


app = FastAPI(lifespan=lifespan, title="QuantGene Paper Trading")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.include_router(pt_router)


@app.get("/ping")
@app.post("/ping")
def ping():
    """Lightweight keep-alive endpoint — responds immediately, no DB calls.
    Use this for cron-job.org to avoid cold-start timeouts."""
    import time as _time
    from datetime import datetime, timezone
    uptime = int(_time.time() - _startup_time) if _startup_time else 0
    return {
        "ok": True,
        "uptime_sec": uptime,
        "cold_start": uptime < 90,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


@app.get("/health")
def health():
    import os, sys
    configured = bool(os.environ.get("TURSO_URL") and os.environ.get("TURSO_TOKEN"))
    count = len(engine.list_instances()) if configured else 0
    return {
        "status": "ok",
        "instances": count,
        "turso_configured": configured,
        "debug": {
            "engine_type": type(engine).__name__,
            "engine_module": type(engine).__module__,
            "running_keys": list(engine._running_instances.keys()) if hasattr(engine, '_running_instances') else [],
            "python": sys.version,
            "routes": [r.path for r in app.routes],
        },
    }


@app.post("/tick")
def tick_all():
    import time as _time
    from datetime import datetime, timezone
    now = _time.time()
    uptime = int(now - _startup_time) if _startup_time else 0
    cold_start = uptime < 90  # service just woke up from Render spin-down

    instances = engine.list_instances()
    count = 0
    skipped = 0
    errors = []
    timings = []
    for inst in instances:
        if inst.status == InstanceStatus.RUNNING:
            t0 = _time.time()
            try:
                result = engine.tick(inst.instance_id)
                elapsed = round(_time.time() - t0, 2)
                timings.append({"id": inst.instance_id[:8], "ms": int(elapsed * 1000)})
                if result and result.get("skipped"):
                    skipped += 1
                else:
                    count += 1
            except Exception as e:
                elapsed = round(_time.time() - t0, 2)
                logger.warning("tick %s error (%.1fs): %s", inst.instance_id, elapsed, e)
                errors.append({"instance_id": inst.instance_id, "error": str(e), "ms": int(elapsed * 1000)})

    return {
        "ok": True,
        "ticked": count,
        "skipped": skipped,
        "total_instances": len(instances),
        "errors": errors,
        "timings": timings,
        "cold_start": cold_start,
        "uptime_sec": uptime,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


@app.post("/tick-debug")
def tick_debug(instance_id: str = ""):
    import traceback, sys
    info = {
        "engine": type(engine).__name__,
        "engine_module": type(engine).__module__,
        "running_keys": list(engine._running_instances.keys()) if hasattr(engine, '_running_instances') else [],
        "python": sys.version,
        "app_routes": [r.path for r in app.routes],
    }
    if instance_id:
        try:
            from paper_trading.engine import PaperTradingEngine
            info["engine_class_file"] = sys.modules.get("paper_trading.engine").__file__
        except:
            pass
        try:
            from paper_trading.models import CreateInstanceRequest
            from paper_trading.models import SourceType
            info["engine_methods"] = {
                "has_get_instance": hasattr(engine, "get_instance"),
                "has_ensure_context": hasattr(engine, "_ensure_context"),
                "instance_found": engine.get_instance(instance_id) is not None,
            }
            if hasattr(engine, "_ensure_context"):
                engine._ensure_context(instance_id)
                info["after_ensure"] = instance_id in engine._running_instances
                info["running_keys"] = list(engine._running_instances.keys())
        except Exception as e:
            info["initialization_error"] = str(e)
            info["traceback"] = traceback.format_exc()
        try:
            result = engine.tick(instance_id)
            info["tick_result"] = result
            info["in_running"] = instance_id in engine._running_instances
        except Exception as e:
            info["tick_error"] = str(e)
            info["tick_traceback"] = traceback.format_exc()
    return info
