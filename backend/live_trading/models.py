from enum import Enum
from typing import Optional
from pydantic import BaseModel


class LiveStatus(str, Enum):
    INITIALIZING = "INITIALIZING"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    STOPPED = "STOPPED"
    FAILED = "FAILED"


class OrderStatus(str, Enum):
    PENDING = "PENDING"
    FILLED = "FILLED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"


class LiveInstance(BaseModel):
    instance_id: str
    name: str
    strategy_config_id: str
    params_json: str
    symbols: str
    initial_capital: float = 10000.0
    status: LiveStatus = LiveStatus.INITIALIZING
    started_at: int = 0
    stopped_at: Optional[int] = None
    timeframe: str = "1d"
    total_equity: float = 0.0
    total_return: float = 0.0
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    trade_count: int = 0
    win_rate: float = 0.0
    max_drawdown: float = 0.0
    schedule_time: str = "16:30"
    max_daily_loss_pct: Optional[float] = None
    max_position_size_pct: Optional[float] = None


class LiveOrder(BaseModel):
    order_id: str
    instance_id: str
    symbol: str
    side: str
    order_type: str = "market"
    qty: float
    status: OrderStatus
    filled_qty: float = 0.0
    filled_avg_price: float = 0.0
    alpaca_order_id: Optional[str] = None
    created_at: int = 0
    updated_at: int = 0
    reason: Optional[str] = None


class LivePosition(BaseModel):
    symbol: str
    side: str = "flat"
    qty: float = 0.0
    entry_price: float = 0.0
    current_price: float = 0.0
    unrealized_pnl: float = 0.0


class CreateLiveInstanceRequest(BaseModel):
    name: str
    strategy_config_id: str
    params: dict = {}
    symbols: list[str] = []
    initial_capital: float = 10000.0
    timeframe: str = "1d"
    schedule_time: str = "16:30"
    max_daily_loss_pct: Optional[float] = None
    max_position_size_pct: Optional[float] = None
