# Module 5: Storage & Analysis Interface

## Overview
Persists evolution data to SQLite and provides analysis/export APIs for frontend visualization.

## Database Tables

### `evolution_tasks`
Task lifecycle: task_id, status, created_at, started_at, completed_at, config_json, current_generation, total_generations, error_message, result_summary_json

### `task_generations`
Per-generation summary: id, task_id, generation, result_json (GenerationResult), created_at

### `individuals`
Per-individual per-generation records: id, task_id, generation, strategy_id, params_json, pareto_rank, crowding_distance, is_elite, cagr, max_drawdown, sharpe_ratio, profit_factor, win_rate, r2, trade_count, oos_consistency_score, passed_absolute, passed_dynamic, elimination_reason, equity_curve_json, symbol_results_json

### `pareto_fronts`
Per-generation Pareto front snapshots: id, task_id, generation, front_json

## Analysis API Endpoints

### Task Level
| Endpoint | Description |
|----------|-------------|
| `GET /tasks/{id}/summary` | Task overview + generations |
| `GET /tasks/{id}/generations` | All generation summaries |
| `GET /tasks/{id}/pareto-front` | Final Pareto front individuals |
| `GET /tasks/{id}/export?format=json` | Export full task data (JSON/CSV) |
| `GET /tasks/{id}/export/python?sid=...` | Export Python dict for deployment |

### Individual Level
| Endpoint | Description |
|----------|-------------|
| `GET /tasks/{id}/individuals` | Query individuals (filter: generation, pareto_rank, elite_only) |
| `GET /tasks/{id}/individuals/{sid}` | Single individual details |
| `GET /tasks/{id}/individuals/{sid}/equity-curve` | Individual equity curve |

### Chart Data
| Endpoint | Description |
|----------|-------------|
| `GET /tasks/{id}/charts/pareto-scatter` | Pareto front 3D scatter data (all generations) |
| `GET /tasks/{id}/charts/evolution-trend` | Evolution trend line data |

## Data Writing Timeline

| Phase | Operation |
|-------|-----------|
| Task created | INSERT evolution_tasks (QUEUED) |
| Task started | UPDATE status=RUNNING |
| Each generation | INSERT generations + individuals + pareto_fronts |
| Task complete | UPDATE status=COMPLETED, result_summary |
| Task failed | UPDATE status=FAILED, error_message |
| Task cancelled | UPDATE status=CANCELLED |

## Export Formats

| Format | Content | Use Case |
|--------|---------|----------|
| JSON | Full task + all generations + all individuals | Backup, external analysis |
| CSV | Pareto front individuals metrics table | Spreadsheet, manual review |
| Python dict | Selected individual params as Python code | Copy-paste to live strategy |

## Indexes
- `individuals`: (task_id, generation), (task_id, pareto_rank)
- `pareto_fronts`: (task_id, generation)
