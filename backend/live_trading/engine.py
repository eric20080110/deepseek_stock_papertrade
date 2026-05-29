import json
import time
import uuid
import logging
import concurrent.futures
from typing import Optional

import numpy as np
import pandas as pd

from database import get_live_db as get_db
from backtest.data_cache import DATA_CACHE
from strategies.base import get_strategy_module

logger = logging.getLogger(__name__)

_BAR_SEC = {"1d": 86400, "1h": 3600, "30m": 1800, "15m": 900, "5m": 300, "1m": 60}
_DATA_POOL = concurrent.futures.ThreadPoolExecutor(max_workers=4, thread_name_prefix="live_data")


def _ensure_data(sym: str, timeframe: str) -> Optional[pd.DataFrame]:
    df = DATA_CACHE.load(sym, timeframe)
    if df is not None and len(df) > 0:
        bar_sec = _BAR_SEC.get(timeframe, 86400)
        if int(time.time()) - int(df.index[-1]) <= bar_sec * 5:
            return df
        _DATA_POOL.submit(DATA_CACHE.ensure, sym, None, None, timeframe, True)
        return df
    try:
        f = _DATA_POOL.submit(DATA_CACHE.ensure, sym, None, None, timeframe, True)
        return f.result(timeout=15)
    except Exception:
        return None


def _get_alpaca_positions() -> dict[str, dict]:
    from live_trading.alpaca import configured, list_positions
    if not configured():
        return {}
    try:
        raw = list_positions()
        return {p["symbol"]: p for p in raw if abs(float(p.get("qty", 0))) > 0}
    except Exception as e:
        logger.warning("Failed to fetch Alpaca positions: %s", e)
        return {}


def _record_equity(db, instance_id: str):
    from live_trading.alpaca import configured, get_account
    if not configured():
        return
    try:
        acct = get_account()
        if acct:
            equity = float(acct.get("equity", 0))
            now = int(time.time())
            db.execute(
                "INSERT INTO live_equity_history (instance_id, timestamp, equity) VALUES (?, ?, ?)",
                (instance_id, now, equity),
            )
    except Exception as e:
        logger.warning("Failed to record equity: %s", e)


class LiveTradingEngine:

    def execute(self, instance_id: str) -> dict:
        db = get_db()
        inst = db.execute(
            "SELECT * FROM live_instances WHERE instance_id = ?", (instance_id,)
        ).fetchone()
        if not inst:
            db.close()
            return {"error": "instance not found"}
        if inst["status"] not in ("RUNNING", "INITIALIZING"):
            db.close()
            return {"error": f"instance status is {inst['status']}"}

        # Risk control: check max_daily_loss_pct
        max_loss_pct = inst.get("max_daily_loss_pct")
        if max_loss_pct is not None and max_loss_pct > 0:
            from live_trading.alpaca import configured as alpaca_configured, get_account
            if alpaca_configured():
                try:
                    acct = get_account()
                    if acct:
                        equity = float(acct.get("equity", 0))
                        last_equity_row = db.execute(
                            "SELECT equity FROM live_equity_history WHERE instance_id = ? ORDER BY timestamp DESC LIMIT 1",
                            (instance_id,),
                        ).fetchone()
                        if last_equity_row and last_equity_row["equity"] > 0:
                            prev_equity = float(last_equity_row["equity"])
                            pnl_pct = (equity - prev_equity) / prev_equity * 100
                            if pnl_pct < -max_loss_pct:
                                logger.warning("Instance %s: daily loss %.2f%% exceeds max %.2f%%, skipping", instance_id, pnl_pct, max_loss_pct)
                                db.close()
                                return {"error": f"daily loss {pnl_pct:.2f}% exceeds max {max_loss_pct}%"}
                except Exception as e:
                    logger.warning("Failed to check daily loss: %s", e)

        strat = db.execute(
            "SELECT * FROM strategy_configs WHERE config_id = ?",
            (inst["strategy_config_id"],),
        ).fetchone()
        if not strat or not strat["template_id"]:
            db.close()
            return {"error": "strategy config not found"}

        mod = get_strategy_module(strat["template_id"])
        if mod is None:
            db.close()
            return {"error": f"strategy module not found: {strat['template_id']}"}

        params = json.loads(inst["params_json"])
        symbols = json.loads(inst["symbols"])
        is_rotation = getattr(mod, "IS_ROTATION", False)
        timeframe = inst["timeframe"]
        capital = inst["initial_capital"]
        capital_per = capital / max(len(symbols), 1)

        # Fetch current Alpaca positions for position-aware qty calculation
        alpaca_positions = _get_alpaca_positions()

        events = []
        order_ids = []

        if is_rotation:
            events, order_ids = self._execute_rotation(
                db, instance_id, mod, params, symbols, capital, events, order_ids, alpaca_positions
            )
        else:
            events, order_ids = self._execute_standard(
                db, instance_id, mod, params, symbols, timeframe, capital_per, events, order_ids, alpaca_positions, capital
            )

        now = int(time.time())
        db.execute(
            "UPDATE live_instances SET status = ?, total_equity = ?, trade_count = trade_count + ? WHERE instance_id = ?",
            ("RUNNING", capital, len(order_ids), instance_id),
        )
        db.commit()
        _record_equity(db, instance_id)
        db.close()

        return {"instance_id": instance_id, "orders_created": len(order_ids), "events": events}

    def _execute_standard(self, db, instance_id, mod, params, symbols, timeframe, capital_per, events, order_ids, alpaca_positions, capital):
        now = int(time.time())
        max_pos_pct = db.execute(
            "SELECT max_position_size_pct FROM live_instances WHERE instance_id = ?", (instance_id,)
        ).fetchone()
        max_pos_pct = float(max_pos_pct["max_position_size_pct"]) if max_pos_pct and max_pos_pct["max_position_size_pct"] else None

        for sym in symbols:
            df = _ensure_data(sym, timeframe)
            if df is None or len(df) < 20:
                logger.warning("LiveTrading: insufficient data for %s", sym)
                continue
            signals = mod.generate_signals(df, params)
            signal = int(signals.iloc[-1])

            # Get actual position from Alpaca instead of relying on DB order history
            actual_pos = alpaca_positions.get(sym)
            actual_qty = abs(float(actual_pos.get("qty", 0))) if actual_pos else 0
            actual_side = "long" if actual_pos and float(actual_pos.get("qty", 0)) > 0 else "short" if actual_pos and float(actual_pos.get("qty", 0)) < 0 else None

            target_side = "flat"
            if signal == 1:
                target_side = "buy"
            elif signal == -1:
                target_side = "sell"

            if target_side == "flat" and not actual_side:
                continue
            if target_side == "flat" and actual_side:
                pass
            elif (target_side == "buy" and actual_side == "long") or (target_side == "sell" and actual_side == "short"):
                continue

            current_price = float(df["close"].iloc[-1])
            if current_price <= 0:
                continue

            if actual_side:
                oid = str(uuid.uuid4())
                db.execute(
                    "INSERT INTO live_orders (order_id, instance_id, symbol, side, order_type, qty, status, created_at, updated_at, reason) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (oid, instance_id, sym, "sell" if actual_side == "long" else "buy", "market", round(actual_qty, 4), "PENDING", now, now, json.dumps({"action": "close_signal"})),
                )
                order_ids.append(oid)
                events.append({"symbol": sym, "action": "close", "reason": "signal"})

            if target_side != "flat":
                max_qty = capital_per / current_price
                if max_pos_pct is not None and max_pos_pct > 0:
                    max_allowed = capital * (max_pos_pct / 100) / current_price
                    if max_qty > max_allowed:
                        logger.info("Position size capped: %.2f -> %.2f by max_position_size_pct=%.1f%%", max_qty, max_allowed, max_pos_pct)
                        max_qty = max_allowed
                if max_qty > 0:
                    oid = str(uuid.uuid4())
                    db.execute(
                        "INSERT INTO live_orders (order_id, instance_id, symbol, side, order_type, qty, status, created_at, updated_at, reason) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (oid, instance_id, sym, target_side, "market", round(max_qty, 4), "PENDING", now, now, json.dumps({"action": "open_signal"})),
                    )
                    order_ids.append(oid)
                    events.append({"symbol": sym, "action": "open", "side": target_side, "price": round(current_price, 2)})

        return events, order_ids

    def _execute_rotation(self, db, instance_id, mod, params, symbols, capital, events, order_ids, alpaca_positions):
        now = int(time.time())
        rot_symbols = symbols if symbols else getattr(mod, "ROTATION_SYMBOLS", [])
        safe_asset = params.get("safe_asset", "SHY")
        spy_asset = params.get("spy_asset", "SPY")
        all_syms = list(dict.fromkeys(rot_symbols + [spy_asset, safe_asset]))

        data_map = {}
        for sym in all_syms:
            df = _ensure_data(sym, "1d")
            if df is not None and len(df) > 50:
                data_map[sym] = df

        if not data_map:
            logger.warning("LiveTrading rotation: no data available")
            return events, order_ids

        scores = {}
        for sym in rot_symbols:
            df = data_map.get(sym)
            if df is None:
                continue
            close_arr = df["close"].values
            if len(close_arr) < 50:
                continue
            try:
                indicators = mod.compute_indicators(close_arr, sym, params)
                last_close = float(close_arr[-1])
                scores[sym] = mod.score_asset(indicators, sym, last_close, -1, params)
            except Exception as e:
                logger.warning("Rotation scoring failed for %s: %s", sym, e)

        if not scores:
            return events, order_ids

        spy_df = data_map.get(spy_asset)
        if spy_df is not None and len(spy_df) > 50:
            spy_closes = spy_df["close"].values
            sma20 = np.mean(spy_closes[-20:])
            sma50 = np.mean(spy_closes[-100:]) if len(spy_closes) >= 100 else np.mean(spy_closes)
            spy_trend = "bull" if sma20 > sma50 else "bear"
        else:
            spy_trend = "neutral"

        if spy_trend == "bull":
            target = max(scores, key=scores.get)
        else:
            target = safe_asset

        if target == safe_asset and safe_asset not in data_map:
            target = max(scores, key=scores.get)

        # Use Alpaca actual position to determine current target
        current_target = None
        for sym in all_syms:
            if sym in alpaca_positions and abs(float(alpaca_positions[sym].get("qty", 0))) > 0:
                current_target = sym
                break

        if not current_target:
            last_order = db.execute(
                "SELECT * FROM live_orders WHERE instance_id = ? ORDER BY created_at DESC LIMIT 1",
                (instance_id,),
            ).fetchone()
            if last_order and last_order.get("reason"):
                try:
                    reason = json.loads(last_order["reason"])
                    current_target = reason.get("target")
                except Exception:
                    pass

        if target == current_target:
            return events, order_ids

        target_price = float(data_map[target]["close"].iloc[-1]) if target in data_map else 0
        if target_price <= 0:
            return events, order_ids

        if current_target and current_target in data_map:
            actual_qty = abs(float(alpaca_positions[current_target].get("qty", 0))) if current_target in alpaca_positions else 0
            oid = str(uuid.uuid4())
            db.execute(
                "INSERT INTO live_orders (order_id, instance_id, symbol, side, order_type, qty, status, created_at, updated_at, reason) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (oid, instance_id, current_target, "sell", "market", round(actual_qty, 4) if actual_qty > 0 else 0, "PENDING", now, now, json.dumps({"action": "close", "reason": "rotation", "target": target})),
            )
            order_ids.append(oid)
            events.append({"action": "close", "symbol": current_target, "rotate_to": target})

        qty = capital / target_price
        oid = str(uuid.uuid4())
        db.execute(
            "INSERT INTO live_orders (order_id, instance_id, symbol, side, order_type, qty, status, created_at, updated_at, reason) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (oid, instance_id, target, "buy", "market", round(qty, 4), "PENDING", now, now, json.dumps({"action": "open", "reason": "rotation", "target": target})),
        )
        order_ids.append(oid)
        events.append({"action": "open", "symbol": target, "price": round(target_price, 2)})

        return events, order_ids
