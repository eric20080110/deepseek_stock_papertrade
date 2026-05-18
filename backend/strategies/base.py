import importlib
from typing import Optional

from .registry import STRATEGY_REGISTRY


def get_strategy_module(strategy_id: str) -> Optional[object]:
    module_path = STRATEGY_REGISTRY.get(strategy_id)
    if module_path is None:
        return None
    try:
        mod = importlib.import_module(module_path)
        return mod
    except ImportError:
        return None
