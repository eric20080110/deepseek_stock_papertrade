from . import ma_crossover, rsi_mean_reversion, bollinger_breakout, macd_momentum

STRATEGY_REGISTRY = {
    "ma_crossover": ma_crossover,
    "rsi_mean_reversion": rsi_mean_reversion,
    "bollinger_breakout": bollinger_breakout,
    "macd_momentum": macd_momentum,
}
