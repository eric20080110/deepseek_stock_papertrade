import time
import pandas as pd


def generate_signals(ohlcv: pd.DataFrame, params: dict) -> pd.Series:
    signals = pd.Series(0, index=ohlcv.index, dtype=int)
    # Switch direction every 60s so every tick sees a signal change (for testing)
    window = (int(time.time()) // 60) % 2
    signals.iloc[-1] = 1 if window == 0 else -1
    return signals
