import asyncio
import logging
import time
from datetime import date, datetime

from database import get_db
from live_trading.engine import LiveTradingEngine

logger = logging.getLogger(__name__)


class LiveScheduler:
    def __init__(self, engine: LiveTradingEngine):
        self._engine = engine
        self._task: asyncio.Task | None = None
        self._running = False

    def start(self):
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("LiveScheduler started")

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("LiveScheduler stopped")

    async def _loop(self):
        loop = asyncio.get_event_loop()
        while self._running:
            try:
                await loop.run_in_executor(None, self._check_and_execute)
            except Exception as e:
                logger.warning("LiveScheduler error: %s", e)
            await asyncio.sleep(60)

    def _check_and_execute(self):
        today = date.today()
        today_str = today.isoformat()
        now = datetime.now()
        now_minutes = now.hour * 60 + now.minute

        db = get_db()
        rows = db.execute(
            "SELECT * FROM live_instances WHERE status = ?", ("RUNNING",)
        ).fetchall()
        db.close()

        for inst in rows:
            schedule_str = inst["schedule_time"] or "16:30"
            try:
                parts = schedule_str.split(":")
                sched_minutes = int(parts[0]) * 60 + int(parts[1])
            except (ValueError, IndexError):
                sched_minutes = 16 * 60 + 30

            if now_minutes < sched_minutes:
                continue

            if inst.get("last_executed_date") == today_str:
                continue

            logger.info("LiveScheduler executing instance %s (%s)", inst["instance_id"], inst["name"])
            try:
                result = self._engine.execute(inst["instance_id"])
                logger.info("LiveScheduler result for %s: %s", inst["instance_id"], result)
            except Exception as e:
                logger.error("LiveScheduler execute failed for %s: %s", inst["instance_id"], e)

            db2 = get_db()
            db2.execute(
                "UPDATE live_instances SET last_executed_date = ? WHERE instance_id = ?",
                (today_str, inst["instance_id"]),
            )
            db2.commit()
            db2.close()
