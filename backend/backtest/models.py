from pydantic import BaseModel
from typing import Optional


class TradeRecord(BaseModel):
    symbol: str
    entry_time: int
    exit_time: int
    entry_bar: int = 0
    exit_bar: int = 0
    entry_price: float
    exit_price: float
    quantity: float
    pnl: float
    pnl_pct: float
    direction: int


class SymbolResult(BaseModel):
    symbol: str
    total_return: float
    annualized_return: float
    sharpe_ratio: float
    max_drawdown: float
    win_rate: float
    profit_factor: float
    trade_count: int
    equity_curve: list[float]
    trades: list[TradeRecord]
    avg_daily_volume: float = 0.0


class InstanceResult(BaseModel):
    strategy_id: str
    params: dict
    symbol_results: dict[str, SymbolResult]
    weighted_metrics: dict[str, float]
    weights: dict[str, float]
    backtest_duration_sec: float
    timeout: bool = False
    error: Optional[str] = None


class BacktestRequest(BaseModel):
    strategy_id: str
    params: dict
    symbols: list[str]
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    initial_capital: float = 10_000.0
