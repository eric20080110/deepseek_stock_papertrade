import numpy as np
import pandas as pd


def compute_sharpe(equity_curve: list[float], periods_per_year: int = 365) -> float:
    if len(equity_curve) < 2:
        return 0.0
    series = pd.Series(equity_curve)
    returns = series.pct_change().dropna()
    if len(returns) < 2 or returns.std() == 0:
        return 0.0
    return float((returns.mean() / returns.std()) * np.sqrt(periods_per_year))


def compute_sortino(equity_curve: list[float], periods_per_year: int = 365) -> float:
    if len(equity_curve) < 2:
        return 0.0
    series = pd.Series(equity_curve)
    returns = series.pct_change().dropna()
    downside = returns[returns < 0]
    if len(downside) < 2 or downside.std() == 0:
        return 0.0
    return float((returns.mean() / downside.std()) * np.sqrt(periods_per_year))


def compute_calmar(equity_curve: list[float], total_bars: int, bars_per_year: int = 365) -> float:
    dd = compute_max_drawdown(equity_curve)
    if dd == 0:
        return 0.0
    ann_ret = compute_annualized_return(equity_curve, total_bars, bars_per_year)
    return float(ann_ret / (dd / 100))


def compute_max_drawdown(equity_curve: list[float]) -> float:
    if len(equity_curve) < 2:
        return 0.0
    series = pd.Series(equity_curve)
    peak = series.expanding().max()
    dd = (peak - series) / peak
    return float(dd.max() * 100)


def compute_annualized_return(
    equity_curve: list[float], total_bars: int, bars_per_year: int = 365
) -> float:
    if len(equity_curve) < 2 or equity_curve[0] == 0:
        return 0.0
    total_ret = equity_curve[-1] / equity_curve[0] - 1
    years = total_bars / bars_per_year
    if years <= 0:
        return 0.0
    if total_ret <= -1:
        return -1.0
    return float((1 + total_ret) ** (1 / years) - 1)


def compute_win_rate(trades: list) -> float:
    if not trades:
        return 0.0
    wins = sum(1 for t in trades if getattr(t, "pnl", None) is not None and t.pnl > 0)
    return round(wins / len(trades) * 100, 2)


def compute_profit_factor(trades: list) -> float:
    gross_profit = sum(
        t.pnl for t in trades if getattr(t, "pnl", None) is not None and t.pnl > 0
    )
    gross_loss = abs(
        sum(
            t.pnl for t in trades if getattr(t, "pnl", None) is not None and t.pnl < 0
        )
    )
    if gross_loss == 0:
        return 999.0 if gross_profit > 0 else 0.0
    return round(gross_profit / gross_loss, 4)


def compute_var(equity_curve: list[float], confidence: float = 0.95) -> float:
    if len(equity_curve) < 2: return 0.0
    series = pd.Series(equity_curve)
    returns = series.pct_change().dropna()
    if len(returns) < 2: return 0.0
    return float(np.percentile(returns, (1 - confidence) * 100))


def compute_cvar(equity_curve: list[float], confidence: float = 0.95) -> float:
    if len(equity_curve) < 2: return 0.0
    series = pd.Series(equity_curve)
    returns = series.pct_change().dropna()
    if len(returns) < 2: return 0.0
    var = compute_var(equity_curve, confidence)
    return float(returns[returns <= var].mean())


import random as _random


def run_monte_carlo(
    equity_curve: list[float],
    n_simulations: int = 1000,
    confidence: float = 0.95,
    seed: int = 42,
) -> dict:
    if len(equity_curve) < 10:
        return {"error": "equity curve too short"}
    rng = _random.Random(seed)
    series = pd.Series(equity_curve)
    returns = series.pct_change().dropna().values
    if len(returns) < 5:
        return {"error": "not enough returns"}

    final_equities = []
    for _ in range(n_simulations):
        sim_returns = rng.choices(list(returns), k=len(returns))
        sim_equity = equity_curve[0]
        for r in sim_returns:
            sim_equity *= (1 + r)
        final_equities.append(sim_equity)

    final_equities.sort()
    lower_idx = int(n_simulations * (1 - confidence) / 2)
    upper_idx = int(n_simulations * (1 + confidence) / 2)

    initial = equity_curve[0]
    total_returns = [(e / initial - 1) * 100 for e in final_equities]

    return {
        "n_simulations": n_simulations,
        "confidence": confidence,
        "median_final_equity": round(float(np.median(final_equities)), 2),
        "median_return_pct": round(float(np.median(total_returns)), 2),
        "mean_return_pct": round(float(np.mean(total_returns)), 2),
        "std_return_pct": round(float(np.std(total_returns)), 2),
        "ci_lower_return": round(total_returns[lower_idx], 2),
        "ci_upper_return": round(total_returns[upper_idx], 2),
        "prob_positive": round(sum(1 for r in total_returns if r > 0) / n_simulations * 100, 1),
        "prob_double": round(sum(1 for r in total_returns if r > 100) / n_simulations * 100, 1),
        "prob_half_loss": round(sum(1 for r in total_returns if r < -50) / n_simulations * 100, 1),
    }


def compute_metrics(
    equity_curve: list[float], trades: list, total_bars: int, bars_per_year: int = 365
) -> dict[str, float]:
    initial = equity_curve[0] if equity_curve else 1.0
    total_ret = (equity_curve[-1] / initial - 1) * 100 if equity_curve else 0.0
    return {
        "total_return": round(total_ret, 4),
        "annualized_return": round(
            compute_annualized_return(equity_curve, total_bars, bars_per_year), 6
        ),
        "sharpe_ratio": round(compute_sharpe(equity_curve, bars_per_year), 4),
        "sortino_ratio": round(compute_sortino(equity_curve, bars_per_year), 4),
        "calmar_ratio": round(compute_calmar(equity_curve, total_bars, bars_per_year), 6),
        "max_drawdown": round(compute_max_drawdown(equity_curve), 4),
        "win_rate": compute_win_rate(trades),
        "profit_factor": compute_profit_factor(trades),
        "trade_count": len(trades),
        "var_95": round(compute_var(equity_curve, 0.95), 6),
        "cvar_95": round(compute_cvar(equity_curve, 0.95), 6),
    }
