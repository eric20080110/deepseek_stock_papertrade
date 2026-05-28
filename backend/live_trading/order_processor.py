import asyncio
import json
import logging
import time

from database import get_db
from live_trading.alpaca import CONFIGURED as ALPACA_CONFIGURED, submit_order, get_order

logger = logging.getLogger(__name__)


class LiveOrderProcessor:
    def __init__(self):
        self._task: asyncio.Task | None = None
        self._running = False

    def start(self):
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("LiveOrderProcessor started (Alpaca configured: %s)", ALPACA_CONFIGURED)

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("LiveOrderProcessor stopped")

    async def _loop(self):
        loop = asyncio.get_event_loop()
        while self._running:
            try:
                await loop.run_in_executor(None, self._process_orders)
            except Exception as e:
                logger.warning("LiveOrderProcessor error: %s", e)
            await asyncio.sleep(30)

    def _process_orders(self):
        if not ALPACA_CONFIGURED:
            return

        db = get_db()

        pending = db.execute(
            "SELECT * FROM live_orders WHERE status = ? ORDER BY created_at ASC LIMIT 20",
            ("PENDING",),
        ).fetchall()

        for order in pending:
            self._submit_to_alpaca(db, order)

        db.commit()

        submitted = db.execute(
            "SELECT * FROM live_orders WHERE status = ? AND alpaca_order_id IS NOT NULL ORDER BY created_at ASC LIMIT 50",
            ("SUBMITTED",),
        ).fetchall()

        for order in submitted:
            self._poll_order_status(db, order)

        db.commit()
        db.close()

    def _submit_to_alpaca(self, db, order):
        side = "buy" if order["side"] in ("buy", "long") else "sell"
        qty = order["qty"]
        if qty <= 0:
            db.execute(
                "UPDATE live_orders SET status = ?, reason = ?, updated_at = ? WHERE order_id = ?",
                ("FAILED", json.dumps({"error": "invalid qty"}), int(time.time()), order["order_id"]),
            )
            return

        result = submit_order(order["symbol"], side, qty)
        if result is None:
            db.execute(
                "UPDATE live_orders SET status = ?, reason = ?, updated_at = ? WHERE order_id = ?",
                ("REJECTED", json.dumps({"error": "alpaca_submit_failed"}), int(time.time()), order["order_id"]),
            )
            return

        alpaca_id = result.get("id")
        alpaca_status = result.get("status", "unknown")
        filled_qty = float(result.get("filled_qty", 0))
        filled_avg_price = float(result.get("filled_avg_price", 0)) if result.get("filled_avg_price") else 0
        now = int(time.time())

        status_map = {
            "filled": "FILLED", "partially_filled": "PARTIALLY_FILLED",
            "accepted": "SUBMITTED", "new": "SUBMITTED",
            "done_for_day": "FILLED", "canceled": "CANCELLED",
            "expired": "CANCELLED", "rejected": "REJECTED", "suspended": "SUBMITTED",
        }
        new_status = status_map.get(alpaca_status, "SUBMITTED")

        db.execute(
            "UPDATE live_orders SET status = ?, filled_qty = ?, filled_avg_price = ?, alpaca_order_id = ?, updated_at = ?, reason = ? WHERE order_id = ?",
            (new_status, filled_qty, filled_avg_price, alpaca_id, now,
             json.dumps({"alpaca_status": alpaca_status, "alpaca_id": alpaca_id}),
             order["order_id"]),
        )

        logger.info("Order %s -> %s (alpaca: %s, filled: %s @ %.2f)",
                     order["order_id"][:8], new_status, alpaca_status, filled_qty, filled_avg_price)

    def _poll_order_status(self, db, order):
        alpaca_id = order["alpaca_order_id"]
        result = get_order(alpaca_id)
        if result is None:
            return

        alpaca_status = result.get("status", "unknown")
        filled_qty = float(result.get("filled_qty", 0))
        filled_avg_price = float(result.get("filled_avg_price", 0)) if result.get("filled_avg_price") else 0
        now = int(time.time())

        status_map = {
            "filled": "FILLED", "partially_filled": "PARTIALLY_FILLED",
            "canceled": "CANCELLED", "expired": "CANCELLED", "rejected": "REJECTED",
        }
        new_status = status_map.get(alpaca_status)
        if new_status is None:
            return

        db.execute(
            "UPDATE live_orders SET status = ?, filled_qty = ?, filled_avg_price = ?, updated_at = ?, reason = ? WHERE order_id = ?",
            (new_status, filled_qty, filled_avg_price, now,
             json.dumps({"alpaca_status": alpaca_status, "alpaca_id": alpaca_id}),
             order["order_id"]),
        )

        logger.info("Order %s polled -> %s (alpaca: %s, filled: %s @ %.2f)",
                     order["order_id"][:8], new_status, alpaca_status, filled_qty, filled_avg_price)
