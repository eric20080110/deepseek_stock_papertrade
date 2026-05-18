from pydantic import BaseModel
from typing import Optional
from enum import Enum


class InstanceStatus(str, Enum):
    INITIALIZING = "INITIALIZING"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    STOPPED = "STOPPED"
    FAILED = "FAILED"


class SourceType(str, Enum):
    evolution = "evolution"
    manual = "manual"


class PaperInstance(BaseModel):
    instance_id: str
    name: str
    source: SourceType
    source_task_id: Optional[str] = None
    source_individual_id: Optional[str] = None
    strategy_config_id: str
    params_json: str
    symbols: list[str]
    initial_capital: float = 10_000.0
    status: InstanceStatus = InstanceStatus.INITIALIZING
    started_at: int
    stopped_at: Optional[int] = None
    timeframe: str = "1d"
    total_equity: float = 0.0
    total_return: float = 0.0
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    trade_count: int = 0
    win_rate: float = 0.0
    max_drawdown: float = 0.0
    auto_tick: bool = False
    tick_interval_sec: int = 10


class VirtualPosition(BaseModel):
    instance_id: str
    symbol: str
    side: str = "flat"
    entry_price: float = 0.0
    entry_time: int = 0
    quantity: float = 0.0
    current_price: float = 0.0
    unrealized_pnl: float = 0.0
    unrealized_pnl_pct: float = 0.0


class VirtualTrade(BaseModel):
    trade_id: str
    instance_id: str
    symbol: str
    side: str
    price: float
    quantity: float
    fee: float
    realized_pnl: Optional[float] = None
    signal_time: int
    executed_time: int
    trigger_reason: str = "strategy_signal"


class CreateInstanceRequest(BaseModel):
    name: str
    source: SourceType = SourceType.manual
    source_task_id: Optional[str] = None
    source_individual_id: Optional[str] = None
    strategy_config_id: str
    params: dict
    symbols: list[str]
    initial_capital: float = 10_000.0
    timeframe: str = "1d"
