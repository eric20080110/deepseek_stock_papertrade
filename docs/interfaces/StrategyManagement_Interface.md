# Module 7: Strategy Management Interface

## Overview
Manages strategy parameter space definitions (StrategyConfig), including template-based creation, parameter/constraint editing, duplication, and deletion.

## Database Table: `strategy_configs`

| Column | Type | Description |
|--------|------|-------------|
| config_id | TEXT PK | UUID |
| name | TEXT | User-defined name (max 50 chars) |
| description | TEXT | Optional description (max 200 chars) |
| template_id | TEXT | Source template ID |
| is_template | INTEGER | 1 = system template (read-only) |
| is_locked | INTEGER | 1 = locked by running task |
| locked_by_task_id | TEXT | Task ID that holds the lock |
| parameters_json | TEXT | JSON array of parameter definitions |
| constraints_json | TEXT | JSON array of constraint definitions |
| created_at | INTEGER | Unix timestamp |
| updated_at | INTEGER | Last modified timestamp |

## API Endpoints

### GET /strategies
List all strategies (templates first, then user-defined).

### GET /strategies/templates
List only system templates.

### GET /strategies/{config_id}
Get single strategy with full parameter/constraint definitions.

### POST /strategies
Create a new strategy from a template.
- Body: `{ template_id, name, description?, parameters?, constraints? }`
- If parameters/constraints omitted, copies from template.

### PUT /strategies/{config_id}
Update strategy. Returns 423 if locked, 403 if template.

### DELETE /strategies/{config_id}
Delete strategy. Returns 423 if locked, 403 if template.

### POST /strategies/{config_id}/duplicate
Duplicate strategy. New name = original + "（複製）". Cannot duplicate templates.

## Data Schemas

### ParamDef (union)
- `continuous`: name, type="continuous", min, max, default, scale (linear|logarithmic)
- `integer`: name, type="integer", min, max, step, default
- `categorical`: name, type="categorical", options[], default
- `boolean`: name, type="boolean", default, controls[]

### ConstraintDef (union)
- `ordering`: type="ordering", params[], relation (less_than|less_equal), repair (clamp_upper|clamp_lower|swap)
- `conditional`: type="conditional", controller, active_when (bool), controlled_params[]
- `categorical_group`: type="categorical_group", controller, groups (dict: option→params[]), common_params[]

## Locking Mechanism
- Locked when a task referencing this config_id is QUEUED or RUNNING.
- Unlocked when all referencing tasks reach COMPLETED/FAILED/CANCELLED.
- Lock disables edit/delete; duplicate is always allowed.

## Strategy Logic Modules

| Template | Module | Signature |
|----------|--------|-----------|
| ma_crossover | strategies/ma_crossover.py | generate_signals(ohlcv, params) → Series |
| rsi_mean_reversion | strategies/rsi_mean_reversion.py | generate_signals(ohlcv, params) → Series |
| bollinger_breakout | strategies/bollinger_breakout.py | generate_signals(ohlcv, params) → Series |
| macd_momentum | strategies/macd_momentum.py | generate_signals(ohlcv, params) → Series |

All output Series values: +1 (long), -1 (short), 0 (flat).
