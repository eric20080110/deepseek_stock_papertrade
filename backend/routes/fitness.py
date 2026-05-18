from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Any

from fitness.scoring import FitnessScorer, score_individuals, GenerationSummary
from fitness.models import IndividualScore
from database import get_db

router = APIRouter(prefix="/fitness", tags=["fitness"])


class FitnessRequest(BaseModel):
    is_metrics: list[dict[str, Any]]
    oos_metrics: list[dict[str, Any]]
    generation: int = 0


class FitnessResponse(BaseModel):
    scores: list[IndividualScore]
    summary: GenerationSummary


@router.post("/score", response_model=FitnessResponse)
def score_endpoint(req: FitnessRequest):
    if len(req.is_metrics) != len(req.oos_metrics):
        raise HTTPException(
            status_code=400,
            detail="is_metrics and oos_metrics must have same length",
        )
    scores, summary = score_individuals(
        req.is_metrics, req.oos_metrics, generation=req.generation
    )
    return FitnessResponse(scores=scores, summary=summary)


@router.get("/settings")
def get_settings():
    from fitness.config import SETTINGS
    return SETTINGS.__dict__


@router.post("/simulate")
def simulate_scoring():
    import numpy as np
    n = 50
    np.random.seed(42)
    is_metrics = []
    oos_metrics = []
    for i in range(n):
        cagr = np.random.uniform(-0.1, 0.4)
        sharpe = np.random.uniform(-0.5, 2.0)
        dd = np.random.uniform(5, 40)
        pf = np.random.uniform(0.5, 3.0)
        wr = np.random.uniform(20, 80)
        tc = int(np.random.randint(5, 100))

        oos_cagr = cagr * np.random.uniform(0.2, 1.2)
        oos_sharpe = sharpe * np.random.uniform(0.2, 1.2)
        oos_dd = dd * np.random.uniform(0.5, 1.8)

        is_metrics.append({
            "strategy_id": f"ind_{i:04d}",
            "annualized_return": round(cagr, 6),
            "sharpe_ratio": round(sharpe, 4),
            "max_drawdown": round(dd, 2),
            "profit_factor": round(pf, 4),
            "win_rate": round(wr, 2),
            "trade_count": tc,
            "equity_curve": list(10000 * np.cumprod(1 + np.random.normal(0.0005, 0.02, 500))),
        })
        oos_metrics.append({
            "strategy_id": f"ind_{i:04d}",
            "annualized_return": round(oos_cagr, 6),
            "sharpe_ratio": round(oos_sharpe, 4),
            "max_drawdown": round(oos_dd, 2),
        })

    scores, summary = score_individuals(is_metrics, oos_metrics, generation=1)
    return {
        "summary": summary.model_dump(),
        "front": [
            {
                "id": s.strategy_id,
                "cagr": s.objective_vector.cagr,
                "dd": s.objective_vector.max_drawdown,
                "sharpe": s.objective_vector.sharpe,
                "rank": s.pareto_rank,
                "distance": s.crowding_distance,
            }
            for s in scores if s.pareto_rank == 1
        ],
        "survived": sum(1 for s in scores if s.passed_dynamic_threshold),
        "total": len(scores),
    }
