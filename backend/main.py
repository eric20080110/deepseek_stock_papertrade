import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from database import init_db, sync_strategies_to_local
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
from paper_trading.ticker import PaperTicker

ticker = PaperTicker(paper_engine)


@asynccontextmanager
async def lifespan(app: FastAPI):
    loop = asyncio.get_running_loop()
    set_event_loop(loop)
    set_pt_event_loop(loop)
    init_db()
    seed_templates()
    ticker.start()
    yield
    await ticker.stop()


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


@app.get("/health")
def health():
    return {"status": "ok"}
