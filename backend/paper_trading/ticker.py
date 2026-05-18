import asyncio
import logging
from paper_trading.engine import PaperTradingEngine
from paper_trading.models import InstanceStatus

logger = logging.getLogger(__name__)


class PaperTicker:
    def __init__(self, engine: PaperTradingEngine):
        self._engine = engine
        self._task: asyncio.Task | None = None
        self._running = False

    def start(self):
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("PaperTicker started")

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("PaperTicker stopped")

    _BAR_SEC = {"1d": 86400, "1h": 3600, "30m": 1800, "15m": 900, "5m": 300, "1m": 60}

    async def _loop(self):
        while self._running:
            try:
                instances = self._engine.list_instances()
                intervals = []
                for inst in instances:
                    if inst.status != InstanceStatus.RUNNING or not inst.auto_tick:
                        continue
                    self._engine.tick(inst.instance_id)
                    bar_sec = self._BAR_SEC.get(inst.timeframe or "1d", 86400)
                    intervals.append(min(inst.tick_interval_sec, bar_sec))
                sleep_sec = min(intervals) if intervals else 60
            except Exception as e:
                logger.warning("PaperTicker tick error: %s", e)
                sleep_sec = 60
            await asyncio.sleep(sleep_sec)
