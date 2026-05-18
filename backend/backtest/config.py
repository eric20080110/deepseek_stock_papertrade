from dataclasses import dataclass, field


@dataclass
class BacktestSettings:
    taker_fee_rate: float = 0.001
    maker_fee_rate: float = 0.0008
    slippage_model: str = "linear"
    max_slippage_rate: float = 0.005
    slippage_volume_ratio: float = 0.01
    data_cache_max_gb: float = 2.0
    min_bars: int = 50
    instance_timeout_sec: float = 60.0

    @classmethod
    def default(cls) -> "BacktestSettings":
        return cls()


SETTINGS = BacktestSettings.default()
