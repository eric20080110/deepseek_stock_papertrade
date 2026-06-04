import asyncio
import concurrent.futures
import logging
import time
from paper_trading.engine import PaperTradingEngine
from paper_trading.models import InstanceStatus

logger = logging.getLogger(__name__)

_TICKER_POOL = concurrent.futures.ThreadPoolExecutor(max_workers=4, thread_name_prefix="ticker")


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
        loop = asyncio.get_event_loop()
        next_tick: dict[str, float] = {}
        while self._running:
            try:
                instances = await loop.run_in_executor(_TICKER_POOL, self._engine.list_instances)
                tick_tasks = []
                now = time.time()
                for inst in instances:
                    if inst.status != InstanceStatus.RUNNING or not inst.auto_tick:
                        continue
                    next_ts = next_tick.get(inst.instance_id, 0.0)
                    if now < next_ts:
                        continue
                    next_tick[inst.instance_id] = now + inst.tick_interval_sec
                    tick_tasks.append(
                        loop.run_in_executor(_TICKER_POOL, self._engine.tick, inst.instance_id)
                    )
                if tick_tasks:
                    await asyncio.gather(*tick_tasks, return_exceptions=True)
                sleep_sec = 5
            except Exception as e:
                logger.warning("PaperTicker tick error: %s", e)
                sleep_sec = 60
            await asyncio.sleep(sleep_sec)
