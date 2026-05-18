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

    async def _loop(self):
        while self._running:
            try:
                instances = self._engine.list_instances()
                intervals = []
                for inst in instances:
                    if inst.status != InstanceStatus.RUNNING or not inst.auto_tick:
                        continue
                    self._engine.tick(inst.instance_id)
                    intervals.append(inst.tick_interval_sec)
                sleep_sec = min(intervals) if intervals else 5
            except Exception as e:
                logger.warning("PaperTicker tick error: %s", e)
                sleep_sec = 5
            await asyncio.sleep(sleep_sec)
