import pandas as pd


def generate_signals(ohlcv: pd.DataFrame, params: dict) -> pd.Series:
    return pd.Series(1, index=ohlcv.index, dtype=int)
