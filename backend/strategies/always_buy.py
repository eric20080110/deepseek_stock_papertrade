import time
import pandas as pd


def generate_signals(ohlcv: pd.DataFrame, params: dict) -> pd.Series:
    signals = pd.Series(0, index=ohlcv.index, dtype=int)
    # Switch direction every 3-minute window so auto-tick every 180s always sees a signal change
    window = (int(time.time()) // 180) % 2
    signals.iloc[-1] = 1 if window == 0 else -1
    return signals
