import os, sys
# Add both this dir and the parent backend dir for imports
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_BACKEND_DIR = os.path.join(_THIS_DIR, "..")
sys.path.insert(0, _BACKEND_DIR)
sys.path.insert(0, _THIS_DIR)

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from database import init_db, get_turso
from engine_state import engine
from paper_trading.ticker import PaperTicker  # uses backend's engine
from paper_trading.models import InstanceStatus
from routes.paper_trading import router as pt_router

ticker = PaperTicker(engine)


@asynccontextmanager
async def lifespan(app):
    import os
    configured = bool(os.environ.get("TURSO_URL") and os.environ.get("TURSO_TOKEN"))
    if configured:
        init_db()
        ticker.start()
    yield
    if configured:
        await ticker.stop()


app = FastAPI(lifespan=lifespan, title="QuantGene Paper Trading")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.include_router(pt_router)


@app.get("/health")
def health():
    import os
    configured = bool(os.environ.get("TURSO_URL") and os.environ.get("TURSO_TOKEN"))
    count = len(engine.list_instances()) if configured else 0
    return {"status": "ok", "instances": count, "turso_configured": configured}


@app.post("/tick")
def tick_all():
    instances = engine.list_instances()
    count = 0
    errors = []
    for inst in instances:
        if inst.status == InstanceStatus.RUNNING:
            try:
                engine.tick(inst.instance_id)
                count += 1
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning("tick %s error: %s", inst.instance_id, e)
                errors.append({"instance_id": inst.instance_id, "error": str(e)})
    return {"ticked": count, "total_instances": len(instances), "errors": errors}


@app.get("/debug/engine")
def debug_engine():
    import sys
    instances = engine.list_instances()
    result = {
        "engine_type": type(engine).__name__,
        "engine_module": type(engine).__module__,
        "running_instances": list(engine._running_instances.keys()) if hasattr(engine, '_running_instances') else [],
        "instances": len(instances),
        "python": sys.version,
    }
    return result

@app.get("/debug/tick-test/{instance_id}")
def debug_tick(instance_id: str):
    import traceback
    try:
        result = engine.tick(instance_id)
        return {"result": result, "running": instance_id in engine._running_instances}
    except Exception as e:
        return {"error": str(e), "traceback": traceback.format_exc()}
