SPEED_FACTORS: dict[str, float] = {
    "ma_crossover": 1.0,
    "rsi_mean_reversion": 0.8,
    "bollinger_breakout": 0.8,
    "macd_momentum": 0.8,
    "always_buy": 1.2,
    "omniscient_paradox": 0.5,
    "tech_momentum_rotation": 0.3,
    "mandelbrot_vol_clustering": 0.05,
    "mega_cap_rotation": 0.15,
}

DEFAULT_SPEED = 0.5


def get_speed_factor(template_id: str) -> float:
    return SPEED_FACTORS.get(template_id, DEFAULT_SPEED)
