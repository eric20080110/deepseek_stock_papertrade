import json, csv, io, numpy as np, pandas as pd
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from typing import Optional

from database import get_db
from evolution.task_manager import TaskManager
from backtest.data_cache import DATA_CACHE

router = APIRouter(prefix="/tasks/{task_id}", tags=["analysis"])
tm = TaskManager()


def _task_config(task_id: str):
    task = tm.get_task(task_id)
    if task and task.config:
        return task.config
    return None


def _ohlcv_prices(symbol: str, start_date: str, end_date: str, timeframe: str) -> tuple[list[float], list[str]]:
    df = DATA_CACHE.ensure(symbol, start_date=start_date, end_date=end_date, timeframe=timeframe)
    if df is None or df.empty:
        return [], []
    from datetime import datetime
    dates = [datetime.utcfromtimestamp(t).strftime("%Y-%m-%d %H:%M") for t in df.index.tolist()]
    prices = [round(float(p), 2) for p in df["close"].tolist()]
    return prices, dates


def _dca_curve(symbol: str, start_date: str, end_date: str, timeframe: str, capital: float = 10000.0) -> list[float]:
    df = DATA_CACHE.ensure(symbol, start_date=start_date, end_date=end_date, timeframe=timeframe)
    if df is None or df.empty:
        return []
    prices = df["close"].tolist()
    n = len(prices)
    if n == 0:
        return []
    cash = capital
    shares = 0.0
    curve = []
    investment = capital / n
    for price in prices:
        cash -= investment
        shares += investment / price
        curve.append(round(shares * price + cash, 2))
    return curve





@router.get("/summary")
def task_summary(task_id: str):
    task = tm.get_task(task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    generations = tm.get_generations(task_id)
    front = []
    if task.result_summary:
        front = task.result_summary.get("final_pareto_front", [])
    return {
        "task": task.model_dump(),
        "generation_count": len(generations),
        "final_pareto_front": front,
        "generations": generations,
    }


@router.get("/generations")
def task_generations(task_id: str):
    return tm.get_generations(task_id)


@router.get("/pareto-front")
def pareto_front(task_id: str):
    task = tm.get_task(task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    fronts = tm.get_pareto_fronts(task_id)
    if fronts:
        return fronts[-1]["front_data"]
    if task.result_summary:
        return task.result_summary.get("final_pareto_front", [])
    return []


@router.get("/individuals")
def list_individuals(
    task_id: str,
    generation: Optional[int] = Query(None),
    pareto_rank: Optional[int] = Query(None),
    elite_only: bool = False,
    limit: int = 100,
    offset: int = 0,
):
    return tm.get_individuals(task_id, generation, pareto_rank, elite_only, limit, offset)


@router.get("/individuals/{sid}")
def get_individual(task_id: str, sid: str):
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM individuals WHERE task_id = ? AND strategy_id = ? ORDER BY generation DESC LIMIT 1",
        (task_id, sid),
    ).fetchone()
    conn.close()
    if not row:
        raise HTTPException(404, "Individual not found")
    d = dict(row)
    if d["equity_curve_json"]:
        raw = json.loads(d["equity_curve_json"])
        d["equity_curve"] = raw if isinstance(raw, list) else raw.get("v", [])
    if d["symbol_results_json"]:
        d["symbol_results"] = json.loads(d["symbol_results_json"])
    if d["params_json"]:
        d["params"] = json.loads(d["params_json"])
    return d


@router.get("/individuals/{sid}/equity-curve")
def individual_equity_curve(task_id: str, sid: str):
    from datetime import datetime
    from backtest.engine import run_symbol_backtest
    conn = get_db()
    row = conn.execute(
        "SELECT equity_curve_json, symbol_results_json, params_json FROM individuals"
        " WHERE task_id = ? AND strategy_id = ? ORDER BY generation DESC LIMIT 1",
        (task_id, sid),
    ).fetchone()
    conn.close()
    if not row:
        raise HTTPException(404, "Equity curve not found")

    config = _task_config(task_id)
    params = json.loads(row["params_json"]) if row["params_json"] else None

    result: dict = {}

    # Re-run backtest on full date range so curve covers start_date→end_date (not just IS 70%)
    if config and params:
        conn2 = get_db()
        cfg_row = conn2.execute(
            "SELECT template_id, config_id FROM strategy_configs WHERE config_id = ?",
            (config.strategy_config_id,),
        ).fetchone()
        conn2.close()
        strategy_id = (cfg_row["template_id"] or cfg_row["config_id"]) if cfg_row else config.strategy_config_id

        full_results = []
        for sym in config.symbols:
            df = DATA_CACHE.ensure(sym, start_date=config.start_date, end_date=config.end_date, timeframe=config.timeframe)
            if df is None or df.empty:
                continue
            sr = run_symbol_backtest(symbol=sym, data=df, params=params, strategy_id=strategy_id, initial_capital=10000.0)
            if sr:
                full_results.append(sr)

        if full_results:
            min_len = min(len(sr.equity_curve) for sr in full_results)
            result["equity_curve"] = [round(float(np.mean([sr.equity_curve[i] for sr in full_results])), 2) for i in range(min_len)]
            ts_full = full_results[0].equity_timestamps or []
            result["dates"] = [datetime.utcfromtimestamp(t).strftime("%Y-%m-%d %H:%M") for t in ts_full[:min_len]] if ts_full else []
            result["symbol_curves"] = {sr.symbol: sr.equity_curve for sr in full_results}
            result["symbol_trades"] = {
                sr.symbol: [
                    {"entry_bar": t.entry_bar, "exit_bar": t.exit_bar,
                     "entry_price": t.entry_price, "exit_price": t.exit_price,
                     "direction": t.direction, "pnl": t.pnl}
                    for t in sr.trades
                ]
                for sr in full_results
            }

    # Fallback: use stored IS equity curve
    if "equity_curve" not in result:
        ts = []
        if row["equity_curve_json"]:
            raw = json.loads(row["equity_curve_json"])
            if isinstance(raw, dict):
                result["equity_curve"] = raw.get("v", [])
                ts = raw.get("t", [])
            else:
                result["equity_curve"] = raw
        result["dates"] = [datetime.utcfromtimestamp(t).strftime("%Y-%m-%d %H:%M") for t in ts] if ts else []
        if row["symbol_results_json"]:
            sym_data = json.loads(row["symbol_results_json"])
            result.setdefault("symbol_curves", {sym: info.get("equity_curve", []) for sym, info in sym_data.items()})
            result.setdefault("symbol_trades", {
                sym: [
                    {"entry_bar": t["entry_bar"], "exit_bar": t["exit_bar"],
                     "entry_price": t["entry_price"], "exit_price": t["exit_price"],
                     "direction": t["direction"], "pnl": t["pnl"]}
                    for t in info.get("trades", [])
                ]
                for sym, info in sym_data.items()
            })

    if "equity_curve" not in result:
        raise HTTPException(404, "Equity curve not found")

    # Symbol price overlays (full range) and DCA benchmark
    sd = config.start_date if config else ""
    ed = config.end_date if config else ""
    tf = config.timeframe if config else "1d"
    symbols = list(result.get("symbol_curves", {}).keys()) or (config.symbols if config else [])
    prices_dates = {sym: _ohlcv_prices(sym, sd, ed, tf) for sym in symbols}
    result["symbol_prices"] = {sym: pd[0] for sym, pd in prices_dates.items()}
    if not result.get("dates"):
        result["dates"] = next((pd[1] for pd in prices_dates.values() if pd[1]), [])
    dca_by_sym = {sym: _dca_curve(sym, sd, ed, tf) for sym in symbols}
    result["dca_curves"] = dca_by_sym
    if dca_by_sym:
        min_len = min(len(c) for c in dca_by_sym.values())
        result["dca_combined"] = [round(float(np.mean([dca_by_sym[s][i] for s in symbols])), 2) for i in range(min_len)]
    return result


@router.get("/charts/pareto-scatter")
def pareto_scatter(task_id: str, last_only: bool = False):
    individuals = tm.get_individuals(task_id, limit=10000)
    if last_only and individuals:
        last_gen = max(ind.get("generation", 0) for ind in individuals)
        individuals = [ind for ind in individuals if ind.get("generation") == last_gen]
    points = []
    for ind in individuals:
        params = ind.get("params_json", "{}")
        if isinstance(params, str):
            try:
                params = json.loads(params)
            except Exception:
                params = {}
        points.append({
            "generation": ind.get("generation", 0),
            "id": ind.get("strategy_id", ""),
            "cagr": ind.get("cagr", 0),
            "dd": ind.get("max_drawdown", 0),
            "sharpe": ind.get("sharpe_ratio", 0),
            "oos": ind.get("oos_consistency_score", 0),
            "pareto_rank": ind.get("pareto_rank"),
            "passed_absolute": bool(ind.get("passed_absolute")),
            "passed_dynamic": bool(ind.get("passed_dynamic")),
        })
    return points


@router.get("/charts/evolution-trend")
def evolution_trend(task_id: str):
    gens = tm.get_generations(task_id)
    trend = []
    for g in gens:
        trend.append({
            "generation": g.get("generation", 0),
            "best_cagr": g.get("best_cagr", 0),
            "best_sharpe": g.get("best_sharpe", 0),
            "best_drawdown": g.get("best_drawdown", 0),
            "passed_absolute": g.get("passed_absolute", 0),
            "passed_dynamic": g.get("passed_dynamic", 0),
            "population_size": g.get("population_size", 0),
            "pareto_front_size": g.get("pareto_front_size", 0),
        })
    return trend


@router.get("/export")
def export_task(task_id: str, format: str = "json"):
    task = tm.get_task(task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    gens = tm.get_generations(task_id)
    individuals = tm.get_individuals(task_id, limit=10000)
    fronts = tm.get_pareto_fronts(task_id)

    if format == "csv":
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["strategy_id", "generation", "pareto_rank", "cagr", "max_drawdown",
                         "sharpe_ratio", "profit_factor", "win_rate", "trade_count", "oos_score"])
        for ind in individuals:
            writer.writerow([
                ind.get("strategy_id"), ind.get("generation"), ind.get("pareto_rank"),
                ind.get("cagr"), ind.get("max_drawdown"), ind.get("sharpe_ratio"),
                ind.get("profit_factor"), ind.get("win_rate"), ind.get("trade_count"),
                ind.get("oos_consistency_score"),
            ])
        return Response(content=output.getvalue(), media_type="text/csv",
                        headers={"Content-Disposition": f"attachment; filename=task_{task_id}.csv"})

    data = {
        "task": task.model_dump(),
        "generations": gens,
        "individuals": individuals,
        "pareto_fronts": fronts,
    }
    return data


@router.get("/export/python")
def export_python(task_id: str, sid: str = None):
    if not sid:
        fronts = tm.get_pareto_fronts(task_id)
        if not fronts:
            raise HTTPException(404, "No pareto front found")
        sid = fronts[-1]["front_data"][0]["id"] if fronts[-1]["front_data"] else None
        if not sid:
            raise HTTPException(404, "No individuals in pareto front")
    conn = get_db()
    row = conn.execute(
        "SELECT params_json FROM individuals WHERE task_id = ? AND strategy_id = ? LIMIT 1",
        (task_id, sid),
    ).fetchone()
    conn.close()
    if not row or not row["params_json"]:
        raise HTTPException(404, "Individual not found")
    params = json.loads(row["params_json"])
    code = "# QuantGene - Best Individual Parameters\n"
    code += f"# Strategy ID: {sid}\n"
    code += "params = {\n"
    for k, v in params.items():
        code += f"    \"{k}\": {repr(v)},\n"
    code += "}\n"
    return Response(content=code, media_type="text/plain",
                    headers={"Content-Disposition": f"attachment; filename=params_{sid[:8]}.py"})
