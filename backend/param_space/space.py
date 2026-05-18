import math
import random
import numpy as np
from typing import Any, Optional

from models import (
    ParamDef, ContinuousParam, IntegerParam, CategoricalParam, BooleanParam,
    ConstraintDef, OrderingConstraint, ConditionalConstraint, CategoricalGroupConstraint,
)


class Individual:
    def __init__(self, params: dict[str, Any]):
        self.params = params
        self.frozen_params: set[str] = set()
        self.active_group: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return self.params


class ParameterSpace:
    def __init__(self, parameters: list[ParamDef], constraints: list[ConstraintDef]):
        self.parameters = parameters
        self.constraints = constraints
        self._param_map: dict[str, ParamDef] = {p.name: p for p in parameters}
        self._ordering_constraints = [
            c for c in constraints if c.type == "ordering"
        ]
        self._conditional_constraints = [
            c for c in constraints if c.type == "conditional"
        ]
        self._categorical_group_constraints = [
            c for c in constraints if c.type == "categorical_group"
        ]

    def sample(self) -> Individual:
        ind = Individual({})
        active_group = None
        category_controller = None

        for c in self._categorical_group_constraints:
            cat_name = c.controller
            cat_def = self._param_map.get(cat_name)
            if cat_def and cat_def.type == "categorical":
                chosen = random.choice(cat_def.options)
                active_group = chosen
                category_controller = cat_name
                ind.params[cat_name] = chosen

        for p in self.parameters:
            if p.name in ind.params:
                continue
            if self._is_frozen_by_conditional(p.name, ind.params):
                ind.params[p.name] = p.default if hasattr(p, "default") else 0
                ind.frozen_params.add(p.name)
                continue
            if not self._is_in_active_group(p.name, active_group):
                ind.params[p.name] = p.default if hasattr(p, "default") else 0
                ind.frozen_params.add(p.name)
                continue
            ind.params[p.name] = self._sample_param(p)

        ind = self._repair_ordering(ind)
        return ind

    def validate(self, params: dict[str, Any]) -> dict:
        violations = []
        for name, val in params.items():
            pdef = self._param_map.get(name)
            if pdef is None:
                violations.append(f"Unknown param: {name}")
                continue
            if not self._validate_value(pdef, val):
                violations.append(f"Value out of range: {name}={val}")

        for c in self._ordering_constraints:
            vals = [params.get(n) for n in c.params]
            if any(v is None for v in vals):
                violations.append(f"Ordering constraint missing params: {c.params}")
                continue
            if c.relation == "less_than" and not (vals[0] < vals[1]):
                violations.append(f"Ordering violation: {c.params[0]} >= {c.params[1]}")
            elif c.relation == "less_equal" and not (vals[0] <= vals[1]):
                violations.append(f"Ordering violation: {c.params[0]} > {c.params[1]}")

        for c in self._conditional_constraints:
            bv = params.get(c.controller)
            if bv is not None and bv != c.active_when:
                for cp in c.controlled_params:
                    pdef = self._param_map.get(cp)
                    if pdef and params.get(cp) != pdef.default:
                        violations.append(
                            f"Conditional violation: {cp} should be default when {c.controller}={bv}"
                        )

        for c in self._categorical_group_constraints:
            cat_val = params.get(c.controller)
            if cat_val is not None:
                active_params = c.groups.get(cat_val, [])
                for pdef in self.parameters:
                    if pdef.name == c.controller:
                        continue
                    if pdef.name not in active_params and pdef.name not in c.common_params:
                        pass

        return {"is_valid": len(violations) == 0, "violations": violations}

    def repair(self, params: dict[str, Any]) -> dict:
        ind = Individual(dict(params))
        ind = self._repair_ordering(ind)
        ind = self._repair_conditional(ind)
        info = {"repaired": False, "repair_failed": False, "params": ind.params}
        val = self.validate(ind.params)
        if not val["is_valid"]:
            has_cat_violation = any(
                "categorical" in v.lower() or "group" in v.lower()
                for v in val["violations"]
            )
            if has_cat_violation:
                info["repair_failed"] = True
                fresh = self.sample()
                info["params"] = fresh.params
                info["resampled"] = True
                return info
            fresh = self.sample()
            info["params"] = fresh.params
            info["resampled"] = True
            return info
        info["repaired"] = True
        return info

    def encode(self, params: dict[str, Any]) -> np.ndarray:
        vec: list[float] = []
        for p in self.parameters:
            val = params.get(p.name, p.default if hasattr(p, "default") else 0)
            if p.type == "continuous":
                if p.scale == "logarithmic":
                    vec.append(math.log(max(val, 1e-10)))
                else:
                    vec.append(val)
            elif p.type == "integer":
                vec.append(float(val))
            elif p.type == "categorical":
                one_hot = [0.0] * len(p.options)
                try:
                    idx = p.options.index(val)
                    one_hot[idx] = 1.0
                except ValueError:
                    one_hot[0] = 1.0
                vec.extend(one_hot)
            elif p.type == "boolean":
                vec.append(1.0 if val else 0.0)
        return np.array(vec, dtype=np.float64)

    def decode(self, vector: np.ndarray) -> dict[str, Any]:
        params = {}
        idx = 0
        for p in self.parameters:
            if p.type in ("continuous", "integer"):
                val = float(vector[idx])
                if p.type == "continuous":
                    if p.scale == "logarithmic":
                        val = math.exp(max(val, -10))
                    val = max(p.min, min(p.max, val))
                else:
                    step = p.step if hasattr(p, "step") and p.step else 1
                    val = round(val / step) * step
                    val = max(p.min, min(p.max, int(val)))
                params[p.name] = val
                idx += 1
            elif p.type == "categorical":
                options = p.options
                segment = vector[idx: idx + len(options)]
                best_idx = int(np.argmax(segment))
                if best_idx >= len(options):
                    best_idx = 0
                params[p.name] = options[best_idx]
                idx += len(options)
            elif p.type == "boolean":
                params[p.name] = float(vector[idx]) > 0.5
                idx += 1
        return params

    def summary(self) -> dict:
        counts = {"continuous": 0, "integer": 0, "categorical": 0, "boolean": 0}
        for p in self.parameters:
            counts[p.type] += 1
        return {
            "total_params": len(self.parameters),
            "continuous_count": counts["continuous"],
            "integer_count": counts["integer"],
            "categorical_count": counts["categorical"],
            "boolean_count": counts["boolean"],
            "constraint_count": len(self.constraints),
        }

    def _sample_param(self, pdef: ParamDef) -> Any:
        if pdef.type == "continuous":
            if pdef.scale == "logarithmic":
                log_min = math.log(max(pdef.min, 1e-10))
                log_max = math.log(max(pdef.max, 1e-10))
                return round(math.exp(random.uniform(log_min, log_max)), 6)
            return round(random.uniform(pdef.min, pdef.max), 6)
        elif pdef.type == "integer":
            values = range(pdef.min, pdef.max + 1, pdef.step)
            return int(random.choice(list(values)))
        elif pdef.type == "categorical":
            return random.choice(pdef.options)
        elif pdef.type == "boolean":
            return random.choice([True, False])
        return None

    def _validate_value(self, pdef: ParamDef, val: Any) -> bool:
        try:
            if pdef.type == "continuous":
                v = float(val)
                return pdef.min <= v <= pdef.max
            elif pdef.type == "integer":
                v = int(val)
                return pdef.min <= v <= pdef.max
            elif pdef.type == "categorical":
                return val in pdef.options
            elif pdef.type == "boolean":
                return isinstance(val, bool)
        except (ValueError, TypeError):
            return False
        return False

    def _is_frozen_by_conditional(self, param_name: str, current_params: dict) -> bool:
        for c in self._conditional_constraints:
            if param_name in c.controlled_params:
                bv = current_params.get(c.controller)
                if bv is not None and bv != c.active_when:
                    return True
        return False

    def _is_in_active_group(self, param_name: str, active_group: Optional[str]) -> bool:
        for c in self._categorical_group_constraints:
            if param_name in c.common_params:
                return True
            if active_group and param_name in c.groups.get(active_group, []):
                return True
            for grp_params in c.groups.values():
                if param_name in grp_params:
                    return False
        return True

    def _repair_ordering(self, ind: Individual) -> Individual:
        for c in self._ordering_constraints:
            if len(c.params) < 2:
                continue
            vals = [ind.params.get(n, 0) for n in c.params]
            pdefs = [self._param_map.get(n) for n in c.params]
            violates = (c.relation == "less_than" and vals[0] >= vals[1]) or (
                c.relation == "less_equal" and vals[0] > vals[1]
            )
            if not violates:
                continue
            if c.repair == "swap":
                ind.params[c.params[0]], ind.params[c.params[1]] = (
                    ind.params[c.params[1]],
                    ind.params[c.params[0]],
                )
            elif c.repair == "clamp_upper":
                p1 = pdefs[1]
                step = p1.step if isinstance(p1, IntegerParam) else 0.001
                ind.params[c.params[0]] = min(vals[1] - step, ind.params[c.params[0]])
                p0 = pdefs[0]
                if p0:
                    ind.params[c.params[0]] = max(p0.min, ind.params[c.params[0]])
            elif c.repair == "clamp_lower":
                p0 = pdefs[0]
                step = p0.step if isinstance(p0, IntegerParam) else 0.001
                ind.params[c.params[1]] = max(vals[0] + step, ind.params[c.params[1]])
                p1 = pdefs[1]
                if p1:
                    ind.params[c.params[1]] = min(p1.max, ind.params[c.params[1]])
        return ind

    def _repair_conditional(self, ind: Individual) -> Individual:
        for c in self._conditional_constraints:
            bv = ind.params.get(c.controller)
            if bv is not None and bv != c.active_when:
                for cp in c.controlled_params:
                    pdef = self._param_map.get(cp)
                    if pdef:
                        ind.params[cp] = pdef.default if hasattr(pdef, "default") else 0
                        ind.frozen_params.add(cp)
        return ind
