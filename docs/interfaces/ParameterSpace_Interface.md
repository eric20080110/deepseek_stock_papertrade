# Module 2: Parameter Space Interface

## Overview
Defines the search space for genetic algorithm optimization. Manages parameter definitions, constraints, sampling, validation, repair, and encode/decode between param dicts and numeric vectors.

## Core Class: `ParameterSpace(parameters, constraints)`

### Constructor
- `parameters: list[ParamDef]` — parameter definitions (mixed types)
- `constraints: list[ConstraintDef]` — constraint definitions (mixed types)

### Operations

| Method | Input | Output | Description |
|--------|-------|--------|-------------|
| `sample()` | — | `Individual` | Random legal parameter combination |
| `validate(params)` | `dict[str, Any]` | `{is_valid, violations}` | Check legality |
| `repair(params)` | `dict[str, Any]` | `{repaired, repair_failed, params}` | Fix violations or resample |
| `encode(params)` | `dict[str, Any]` | `np.ndarray` | Convert to numeric vector |
| `decode(vector)` | `np.ndarray` | `dict[str, Any]` | Convert numeric vector to params |
| `summary()` | — | `dict` | Space statistics |

## Parameter Types

### Continuous
```json
{"name": "sl", "type": "continuous", "min": 0.005, "max": 0.1, "scale": "linear", "default": 0.03}
```
- `scale`: "linear" (uniform) or "logarithmic" (log-uniform, for cross-order-of-magnitude params)

### Integer
```json
{"name": "period", "type": "integer", "min": 5, "max": 200, "step": 1, "default": 10}
```

### Categorical
```json
{"name": "ma_type", "type": "categorical", "options": ["SMA", "EMA"], "default": "SMA"}
```
- Mutation: random switch to another option (no interpolation)

### Boolean
```json
{"name": "flag", "type": "boolean", "default": false, "controls": ["sub_param_a", "sub_param_b"]}
```
- `controls`: sub-params frozen when value is False

## Constraint Types

| Type | Fields | Description |
|------|--------|-------------|
| `ordering` | params[], relation (less_than/less_equal), repair (clamp_upper/clamp_lower/swap) | Numeric ordering constraints |
| `conditional` | controller (boolean), active_when, controlled_params[] | Boolean-controlled param freezing |
| `categorical_group` | controller (categorical), groups (dict), common_params[] | Category-dependent param groups |

## Sample Order
1. Sample categorical group controller → determine active group
2. Sample boolean params → check conditional freezing
3. Sample remaining params by type
4. Repair ordering constraints

## Encode/Decode Rules
- Continuous: direct value (log value if log scale)
- Integer: direct float
- Categorical: one-hot (n bits for n options)
- Boolean: 0/1
- Frozen sub-params: encoded as 0 (placeholder, excluded from evolution operators)

## Individual
```python
{
    "params": dict[str, Any],        # parameter values
    "frozen_params": set[str],       # frozen param names
    "active_group": str | None       # active categorical group
}
```

## Collaboration Flow (Crossover)
1. Select parents → 2. Encode both → 3. Crossover operators → 4. Decode → 5. Repair ordering/conditional → 6. Validate → 7. Resample if still invalid (max 10 tries)

## API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/param-space/sample` | POST | Sample random individual |
| `/param-space/validate` | POST | Validate parameter dict |
| `/param-space/repair` | POST | Repair invalid params |
| `/param-space/encode` | POST | Encode params to vector |
| `/param-space/decode` | POST | Decode vector to params |
| `/param-space/strategies/{id}/summary` | GET | Strategy space summary |
| `/param-space/strategies/{id}/sample` | POST | Sample from DB strategy |
