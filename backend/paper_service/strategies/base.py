import numpy as np
import pandas as pd
from typing import Optional


class StrategyBase:
    def __init__(self, params: dict):
        self.params = params

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        raise NotImplementedError


def get_strategy_module(template_id: str):
    from .registry import STRATEGY_REGISTRY
    return STRATEGY_REGISTRY.get(template_id)
