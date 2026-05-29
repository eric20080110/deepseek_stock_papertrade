import asyncio
import logging
import time
from datetime import date, datetime

from database import get_live_db as get_db
from live_trading.engine import LiveTradingEngine

logger = logging.getLogger(__name__)

# Major US market holidays (simplified; NYSE calendar)
_US_HOLIDAYS_2025 = {
    date(2025, 1, 1),   # New Year
    date(2025, 1, 20),  # MLK Day
    date(2025, 2, 17),  # Presidents Day
    date(2025, 4, 18),  # Good Friday
    date(2025, 5, 26),  # Memorial Day
    date(2025, 6, 19),  # Juneteenth
    date(2025, 7, 4),   # Independence Day
    date(2025, 9, 1),   # Labor Day
    date(2025, 11, 27), # Thanksgiving
    date(2025, 12, 25), # Christmas
}
_US_HOLIDAYS_2026 = {
    date(2026, 1, 1),
    date(2026, 1, 19),
    date(2026, 2, 16),
    date(2026, 4, 3),
    date(2026, 5, 25),
    date(2026, 6, 19),
    date(2026, 7, 3),
    date(2026, 9, 7),
    date(2026, 11, 26),
    date(2026, 12, 25),
}
_US_HOLIDAYS = _US_HOLIDAYS_2025 | _US_HOLIDAYS_2026


def _is_market_open(today: date) -> bool:
    if today.weekday() >= 5:
        return False
    if today in _US_HOLIDAYS:
        return False
    return True


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
        if not _is_market_open(today):
            return

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
