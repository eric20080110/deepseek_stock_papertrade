# Module 1: Backtest Engine Interface

## Overview
Bar-by-bar backtesting engine with multi-symbol support, fee/slippage models, and volume-weighted metric merging.

## Core Functions

### `run_backtest(strategy_id, params, symbols, data_map, initial_capital, parallel) -> InstanceResult`
Multi-symbol backtest with parallel execution and volume-weighted merging.

### `run_symbol_backtest(symbol, data, params, strategy_id, initial_capital) -> SymbolResult | None`
Single symbol backtest. Called internally by `run_backtest`.

## Data Schemas

### Input: BacktestRequest
```json
{
  "strategy_id": "ma_crossover",
  "params": {"fast_period": 10, ...},
  "symbols": ["BTC/USDT", "ETH/USDT"],
  "start_date": "2023-01-01",
  "end_date": "2025-12-31",
  "initial_capital": 10000.0
}
```

### Output: InstanceResult
| Field | Type | Description |
|-------|------|-------------|
| strategy_id | str | Strategy identifier |
| params | dict | Original params (echoed back) |
| symbol_results | dict[str, SymbolResult] | Per-symbol results |
| weighted_metrics | dict[str, float] | Volume-weighted merged metrics |
| weights | dict[str, float] | Per-symbol weight for audit |
| backtest_duration_sec | float | Duration in seconds |
| timeout | bool | Whether backtest timed out |
| error | str | null | Error message if any |

### SymbolResult
| Field | Type | Description |
|-------|------|-------------|
| symbol | str | Trading pair |
| total_return | float | Total return % |
| annualized_return | float | CAGR % |
| sharpe_ratio | float | Sharpe ratio (365d) |
| max_drawdown | float | Max drawdown % |
| win_rate | float | Win rate % |
| profit_factor | float | Gross profit / gross loss |
| trade_count | int | Total trades |
| equity_curve | list[float] | Per-bar equity |
| trades | list[TradeRecord] | All trades |
| avg_daily_volume | float | Avg daily volume (USD) |

### TradeRecord
| Field | Type | Description |
|-------|------|-------------|
| symbol | str | Trading pair |
| entry_time/exit_time | int | Unix ms timestamps |
| entry_price/exit_price | float | Prices |
| quantity | float | Position size |
| pnl | float | PnL in currency |
| pnl_pct | float | PnL % |
| direction | int | 1=long, -1=short |

## Configuration (BacktestSettings)
| Field | Default | Description |
|-------|---------|-------------|
| taker_fee_rate | 0.001 | Taker fee (0.1%) |
| maker_fee_rate | 0.0008 | Maker fee (0.08%) |
| slippage_model | "linear" | linear or sqrt |
| max_slippage_rate | 0.005 | Max slippage (0.5%) |
| slippage_volume_ratio | 0.01 | Volume ratio threshold |
| min_bars | 50 | Minimum bars required |
| instance_timeout_sec | 60.0 | Per-instance timeout |

## Performance
- Vectorized pandas/numpy operations
- Multiprocessing for symbol-level parallelism
- Data caching (LRU eviction at 2GB)
- Target: <100ms for 3yr daily data per symbol
- Achieved: ~10ms for 500 bars

## Error Handling
- Insufficient data (<min_bars): skip symbol, log warning
- Zero volume bar: defer signal to next bar
- Param validation: return error result (not exception)
- Timeout: force terminate, return partial result with timeout flag

## API Endpoints

### POST /backtest/run
Run backtest with inline params.

### GET /backtest/strategies/{config_id}/run
Run backtest using a stored strategy configuration from DB.
