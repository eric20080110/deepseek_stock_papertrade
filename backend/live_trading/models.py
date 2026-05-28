import json
from enum import Enum
from typing import Optional, List, Any
from pydantic import BaseModel, Field


class LiveStatus(str, Enum):
    INITIALIZING = "INITIALIZING"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    STOPPED = "STOPPED"
    ERROR = "ERROR"


class OrderStatus(str, Enum):
    PENDING = "PENDING"
    SUBMITTED = "SUBMITTED"
    FILLED = "FILLED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    CANCELED = "CANCELED"
    REJECTED = "REJECTED"


class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"


class LiveInstance(BaseModel):
    instance_id: str
    name: str
    strategy_config_id: str
    params_json: str
    symbols: Any
    initial_capital: float
    status: LiveStatus
    started_at: int
    stopped_at: Optional[int] = None
    timeframe: str
    total_equity: Optional[float] = None
    total_return: Optional[float] = None
    unrealized_pnl: Optional[float] = None
    realized_pnl: Optional[float] = None
    trade_count: Optional[int] = None
    win_rate: Optional[float] = None
    max_drawdown: Optional[float] = None
    schedule_time: Optional[str] = None
    max_daily_loss_pct: Optional[float] = None
    max_position_size_pct: Optional[float] = None

    class Config:
        from_attributes = True


class LiveOrder(BaseModel):
    order_id: str
    instance_id: str
    symbol: str
    side: str
    order_type: str
    qty: float
    status: str
    created_at: int
    updated_at: int
    limit_price: Optional[float] = None
    stop_price: Optional[float] = None
    filled_qty: Optional[float] = None
    filled_avg_price: Optional[float] = None
    alpaca_order_id: Optional[str] = None
    reason: Optional[str] = None

    class Config:
        from_attributes = True


class LivePosition(BaseModel):
    instance_id: str
    symbol: str
    side: str
    qty: float
    entry_price: float
    current_price: Optional[float] = None
    unrealized_pnl: Optional[float] = None
    market_value: Optional[float] = None
    cost_basis: Optional[float] = None
    change_pct: Optional[float] = None

    class Config:
        from_attributes = True


class CreateManualOrderRequest(BaseModel):
    symbol: str
    side: OrderSide
    order_type: Optional[OrderType] = OrderType.MARKET
    qty: float = Field(gt=0, description="Order quantity (positive)")


class CreateLiveInstanceRequest(BaseModel):
    name: str
    strategy_config_id: str
    params: dict = {}
    symbols: List[str]
    initial_capital: float
    timeframe: str
    schedule_time: str = "16:30"
    max_daily_loss_pct: Optional[float] = None
    max_position_size_pct: Optional[float] = None
