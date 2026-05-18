from models import (
    ContinuousParam, IntegerParam, CategoricalParam, BooleanParam,
    OrderingConstraint, ConditionalConstraint, CategoricalGroupConstraint,
)
from param_space.space import ParameterSpace


def _make_simple_space() -> ParameterSpace:
    params = [
        ContinuousParam(name="fast_p", type="continuous", min=2, max=100, default=10),
        ContinuousParam(name="slow_p", type="continuous", min=10, max=200, default=50),
    ]
    constraints = [
        OrderingConstraint(type="ordering", params=["fast_p", "slow_p"], relation="less_than", repair="swap"),
    ]
    return ParameterSpace(params, constraints)


class TestParameterSpace:
    def test_sample_returns_valid_params(self):
        space = _make_simple_space()
        for _ in range(20):
            ind = space.sample()
            assert ind.params["fast_p"] < ind.params["slow_p"]
            assert 2 <= ind.params["fast_p"] <= 100
            assert 10 <= ind.params["slow_p"] <= 200

    def test_validate_passes_for_valid(self):
        space = _make_simple_space()
        result = space.validate({"fast_p": 10, "slow_p": 50})
        assert result["is_valid"]

    def test_validate_fails_ordering(self):
        space = _make_simple_space()
        result = space.validate({"fast_p": 50, "slow_p": 10})
        assert not result["is_valid"]
        assert len(result["violations"]) > 0

    def test_validate_fails_out_of_range(self):
        space = _make_simple_space()
        result = space.validate({"fast_p": 500, "slow_p": 50})
        assert not result["is_valid"]

    def test_repair_swaps_violated_ordering(self):
        space = _make_simple_space()
        repaired = space.repair({"fast_p": 50, "slow_p": 10})
        p = repaired["params"]
        assert p["fast_p"] < p["slow_p"]

    def test_repair_clamps_out_of_range(self):
        space = _make_simple_space()
        repaired = space.repair({"fast_p": -5, "slow_p": 50})
        p = repaired["params"]
        assert p["fast_p"] >= 2

    def test_encode_decode_roundtrip(self):
        space = _make_simple_space()
        original = {"fast_p": 25.5, "slow_p": 75.3}
        vec = space.encode(original)
        decoded = space.decode(vec)
        assert abs(decoded["fast_p"] - original["fast_p"]) < 0.1
        assert abs(decoded["slow_p"] - original["slow_p"]) < 0.1

    def test_encode_length(self):
        space = _make_simple_space()
        vec = space.encode({"fast_p": 10, "slow_p": 50})
        assert len(vec) == 2


class TestParameterSpaceWithConstraints:
    def test_categorical_constraint(self):
        params = [
            CategoricalParam(name="ma_type", type="categorical", options=["SMA", "EMA"], default="SMA"),
            IntegerParam(name="fast_p", type="integer", min=2, max=100, default=10),
        ]
        space = ParameterSpace(params, [])
        ind = space.sample()
        assert ind.params["ma_type"] in ["SMA", "EMA"]
        assert 2 <= ind.params["fast_p"] <= 100

    def test_boolean_conditional(self):
        params = [
            BooleanParam(name="use_filter", type="boolean", default=False),
            ContinuousParam(name="filter_val", type="continuous", min=0, max=10, default=5),
        ]
        constraints = [
            ConditionalConstraint(
                type="conditional",
                controller="use_filter",
                active_when=True,
                controlled_params=["filter_val"],
            ),
        ]
        space = ParameterSpace(params, constraints)
        ind = space.sample()
        if ind.params["use_filter"] is True:
            assert 0 <= ind.params["filter_val"] <= 10

    def test_categorical_group(self):
        params = [
            CategoricalParam(name="method", type="categorical", options=["a", "b"], default="a"),
            ContinuousParam(name="param_a", type="continuous", min=0, max=1, default=0.5),
            ContinuousParam(name="param_b", type="continuous", min=0, max=10, default=5),
        ]
        constraints = [
            CategoricalGroupConstraint(
                type="categorical_group",
                controller="method",
                groups={"a": ["param_a"], "b": ["param_b"]},
            ),
        ]
        space = ParameterSpace(params, constraints)
        ind_a = space.repair({"method": "a", "param_a": 0.5, "param_b": 5})
        ind_b = space.repair({"method": "b", "param_a": 0.5, "param_b": 5})
        assert ind_a["params"]["method"] == "a"
        assert ind_b["params"]["method"] == "b"

    def test_integer_param_roundtrip(self):
        space = ParameterSpace(
            [IntegerParam(name="n", type="integer", min=1, max=100, default=50)],
            [],
        )
        vec = space.encode({"n": 42})
        decoded = space.decode(vec)
        assert decoded["n"] == 42
        assert isinstance(decoded["n"], int)
