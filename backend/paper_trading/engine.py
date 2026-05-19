import json
import time
import uuid
import threading
import concurrent.futures
from typing import Optional

_DATA_FETCH_EXECUTOR = concurrent.futures.ThreadPoolExecutor(
    max_workers=3, thread_name_prefix="paper_data"
)

from database import get_turso as _get_turso, get_db as _get_local
from paper_trading.models import (
    PaperInstance, InstanceStatus, SourceType, CreateInstanceRequest,
)


def get_db():
    """Return Turso if available, otherwise local SQLite. Timeout is 6s so fallback is fast."""
    try:
        return _get_turso()
    except Exception:
        return _get_local()


_instance_cache: dict[str, PaperInstance] = {}
_instance_cache_ts: float = 0.0
_instance_cache_lock = threading.Lock()
_INSTANCE_CACHE_TTL = 5.0


def _invalidate_instance_cache():
    global _instance_cache_ts
    with _instance_cache_lock:
        _instance_cache_ts = 0.0


class PaperTradingEngine:
    def __init__(self):
        self._running_instances: dict[str, dict] = {}
        self._tick_callbacks: list = []

    def register_tick_callback(self, cb):
        self._tick_callbacks.append(cb)

    def create_instance(self, req: CreateInstanceRequest) -> PaperInstance:
        _invalidate_instance_cache()
        conn = get_db()
        instance_id = str(uuid.uuid4())
        now = int(time.time())
        conn.execute(
            """INSERT INTO paper_instances
               (instance_id, name, source, source_task_id, source_individual_id,
                strategy_config_id, params_json, symbols, initial_capital,
                status, started_at, timeframe, auto_tick, tick_interval_sec)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'INITIALIZING', ?, ?, ?, ?)""",
            (
                instance_id, req.name, req.source.value,
                req.source_task_id, req.source_individual_id,
                req.strategy_config_id, json.dumps(req.params),
                json.dumps(req.symbols), req.initial_capital,
                now, req.timeframe,
                1 if req.auto_tick else 0, req.tick_interval_sec,
            ),
        )
        conn.commit()
        conn.close()
        return self.get_instance(instance_id)

    def get_instance(self, instance_id: str) -> Optional[PaperInstance]:
        global _instance_cache, _instance_cache_ts
        with _instance_cache_lock:
            if time.time() - _instance_cache_ts < _INSTANCE_CACHE_TTL and instance_id in _instance_cache:
                return _instance_cache[instance_id]
        conn = get_db()
        row = conn.execute(
            "SELECT * FROM paper_instances WHERE instance_id = ?", (instance_id,)
        ).fetchone()
        conn.close()
        if not row:
            return None
        inst = self._row_to_instance(row)
        with _instance_cache_lock:
            _instance_cache[instance_id] = inst
        return inst

    def list_instances(self) -> list[PaperInstance]:
        global _instance_cache, _instance_cache_ts
        with _instance_cache_lock:
            if time.time() - _instance_cache_ts < _INSTANCE_CACHE_TTL and _instance_cache:
                return sorted(_instance_cache.values(), key=lambda i: i.started_at, reverse=True)
        conn = get_db()
        rows = conn.execute(
            "SELECT * FROM paper_instances ORDER BY started_at DESC"
        ).fetchall()
        conn.close()
        instances = [self._row_to_instance(r) for r in rows]
        with _instance_cache_lock:
            _instance_cache = {i.instance_id: i for i in instances}
            _instance_cache_ts = time.time()
        return instances

    def update_instance(self, instance_id: str, **kwargs):
        _invalidate_instance_cache()
        conn = get_db()
        sets = ", ".join(f"{k} = ?" for k in kwargs)
        vals = list(kwargs.values()) + [instance_id]
        conn.execute(
            f"UPDATE paper_instances SET {sets} WHERE instance_id = ?", vals
        )
        conn.commit()
        conn.close()

    def pause_instance(self, instance_id: str) -> bool:
        inst = self.get_instance(instance_id)
        if not inst or inst.status != InstanceStatus.RUNNING:
            return False
        self.update_instance(instance_id, status="PAUSED")
        return True

    def resume_instance(self, instance_id: str) -> bool:
        inst = self.get_instance(instance_id)
        if not inst or inst.status != InstanceStatus.PAUSED:
            return False
        self.update_instance(instance_id, status="RUNNING")
        return True

    def stop_instance(self, instance_id: str) -> bool:
        inst = self.get_instance(instance_id)
        if not inst:
            return False
        now = int(time.time())
        self._close_all_positions(instance_id, None)
        self.update_instance(
            instance_id, status="STOPPED", stopped_at=now
        )
        return True

    def delete_instance(self, instance_id: str):
        _invalidate_instance_cache()
        self._running_instances.pop(instance_id, None)
        conn = get_db()
        conn.execute("DELETE FROM virtual_trades WHERE instance_id = ?", (instance_id,))
        conn.execute("DELETE FROM virtual_positions WHERE instance_id = ?", (instance_id,))
        conn.execute("DELETE FROM paper_equity_history WHERE instance_id = ?", (instance_id,))
        conn.execute("DELETE FROM paper_instances WHERE instance_id = ?", (instance_id,))
        conn.commit()
        conn.close()

    def set_auto_tick(self, instance_id: str, enabled: bool, interval_sec: int = 10) -> bool:
        inst = self.get_instance(instance_id)
        if not inst:
            return False
        self.update_instance(
            instance_id,
            auto_tick=1 if enabled else 0,
            tick_interval_sec=interval_sec,
        )
        return True

    def run_initialization(self, instance_id: str):
        inst = self.get_instance(instance_id)
        if not inst:
            return
        symbols = json.loads(inst.symbols) if isinstance(inst.symbols, str) else inst.symbols
        params = json.loads(inst.params_json) if isinstance(inst.params_json, str) else inst.params_json
        template_id = self._resolve_template_id(inst)

        conn = get_db()
        for sym in symbols:
            conn.execute(
                "INSERT OR IGNORE INTO virtual_positions (instance_id, symbol, side) VALUES (?, ?, 'flat')",
                (instance_id, sym),
            )
        conn.commit()
        conn.close()

        self.update_instance(instance_id, status="RUNNING")
        self._running_instances[instance_id] = {
            "template_id": template_id,
            "params": params,
            "symbols": symbols,
            "timeframe": inst.timeframe or "1d",
        }

    def _resolve_template_id(self, inst) -> str:
        sid = inst.strategy_config_id
        conn = get_db()
        row = conn.execute(
            "SELECT template_id FROM strategy_configs WHERE config_id = ?", (sid,)
        ).fetchone()
        if row:
            conn.close()
            return row["template_id"]
        # Fallback: strategy_config_id might be an individual's strategy_id
        if inst.source_task_id:
            task = conn.execute(
                "SELECT config_json FROM evolution_tasks WHERE task_id = ?", (inst.source_task_id,)
            ).fetchone()
            if task:
                task_cfg = json.loads(task["config_json"])
                cfg_id = task_cfg.get("strategy_config_id", "")
                cfg_row = conn.execute(
                    "SELECT template_id FROM strategy_configs WHERE config_id = ?", (cfg_id,)
                ).fetchone()
                if cfg_row:
                    conn.close()
                    return cfg_row["template_id"]
        conn.close()
        return sid

    def _ensure_context(self, instance_id: str):
        inst = self.get_instance(instance_id)
        if not inst:
            raise ValueError(f"Instance {instance_id} not found")
        symbols = json.loads(inst.symbols) if isinstance(inst.symbols, str) else inst.symbols
        params = json.loads(inst.params_json) if isinstance(inst.params_json, str) else inst.params_json
        template_id = self._resolve_template_id(inst)

        self._running_instances[instance_id] = {
            "template_id": template_id,
            "params": params,
            "symbols": symbols,
            "timeframe": inst.timeframe or "1d",
        }

    _BAR_SEC = {"1d": 86400, "1h": 3600, "30m": 1800, "15m": 900, "5m": 300, "1m": 60}

    def _get_fresh_data(self, sym: str, timeframe: str):
        from backtest.data_cache import DATA_CACHE
        bar_sec = self._BAR_SEC.get(timeframe, 86400)
        now = int(time.time())
        df = DATA_CACHE.ensure(sym, timeframe=timeframe)
        if df is not None and len(df) > 0:
            if now - int(df.index[-1]) <= bar_sec * 5:
                return df
            # Stale — kick off background refresh and return current data immediately.
            # Next tick will pick up the fresh data once the background fetch completes.
            _DATA_FETCH_EXECUTOR.submit(DATA_CACHE.ensure, sym, None, None, timeframe, True)
            return df
        # Nothing cached at all (cold start) — wait up to 10s for first fetch.
        try:
            future = _DATA_FETCH_EXECUTOR.submit(
                DATA_CACHE.ensure, sym, None, None, timeframe, True
            )
            return future.result(timeout=10)
        except Exception:
            return None

    def _save_equity_point(self, instance_id: str, ts: int, equity: float):
        ctx = self._running_instances.get(instance_id)
        timeframe = ctx.get("timeframe", "1d") if ctx else "1d"
        bar_sec = self._BAR_SEC.get(timeframe, 86400)
        min_interval = max(bar_sec // 6, 60)
        last_save = ctx.get("_last_equity_ts", 0) if ctx else 0
        if ts - last_save < min_interval:
            return
        try:
            conn = get_db()
            conn.execute(
                "INSERT INTO paper_equity_history (instance_id, timestamp, equity) VALUES (?, ?, ?)",
                (instance_id, ts, round(equity, 2)),
            )
            conn.commit()
            conn.close()
            if ctx is not None:
                ctx["_last_equity_ts"] = ts
        except Exception:
            pass

    def tick(self, instance_id: str) -> Optional[dict]:
        inst = self.get_instance(instance_id)
        if not inst or inst.status != InstanceStatus.RUNNING:
            return None
        if instance_id not in self._running_instances:
            try:
                self._ensure_context(instance_id)
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning("tick _ensure_context error for %s: %s", instance_id, e)
                return None
        ctx = self._running_instances.get(instance_id)
        if not ctx:
            return None

        # Cooldown: skip duplicate ticks within 30s to prevent double-execution
        # when both internal PaperTicker and external /tick endpoint fire simultaneously
        now = time.time()
        last_tick = ctx.get("_last_tick_ts", 0)
        cooldown = max(30, inst.tick_interval_sec // 2) if inst.tick_interval_sec else 30
        if now - last_tick < cooldown:
            return {"instance_id": instance_id, "events": [], "skipped": True}
        ctx["_last_tick_ts"] = now

        symbols = ctx["symbols"]
        params = ctx["params"]
        template_id = ctx["template_id"]
        timeframe = ctx.get("timeframe", inst.timeframe or "1d")

        # Bug 2 fix: use current total equity for per-symbol capital so realized PnL flows back in
        current_equity = self._compute_total_equity(instance_id)
        per_sym_capital = current_equity / max(len(symbols), 1)

        events = []
        for sym in symbols:
            df = self._get_fresh_data(sym, timeframe)
            if df is None or len(df) < 50:
                continue

            from strategies.base import get_strategy_module
            mod = get_strategy_module(template_id)
            if mod is None:
                continue
            try:
                signals = mod.generate_signals(df, params)
                signal = int(signals.iloc[-1])
            except Exception:
                signal = 0

            latest_price = float(df.iloc[-1]["close"])
            pos = self._get_position(instance_id, sym)
            current_side = pos["side"] if pos else "flat"

            if signal != 0 and signal != (1 if current_side == "long" else -1 if current_side == "short" else 0):
                if current_side != "flat":
                    self._close_position(instance_id, sym, latest_price)
                    events.append({"type": "close", "symbol": sym, "price": latest_price, "reason": "signal"})
                    current_side = "flat"

                self._open_position(instance_id, sym, signal, latest_price, per_sym_capital)
                events.append({"type": "open", "symbol": sym, "side": "long" if signal == 1 else "short", "price": latest_price})

            self._update_position_price(instance_id, sym, latest_price)

            # Bug 4 fix: check stop-loss / take-profit after price update
            pos = self._get_position(instance_id, sym)
            if pos and pos["side"] != "flat":
                sl_pct = float(params.get("stop_loss_pct", 0) or 0)
                tp_pct = float(params.get("take_profit_pct", 0) or 0)
                upnl_pct = float(pos.get("unrealized_pnl_pct", 0) or 0)
                if sl_pct > 0 and upnl_pct <= -sl_pct:
                    self._close_position(instance_id, sym, latest_price, reason="stop_loss")
                    events.append({"type": "close", "symbol": sym, "price": latest_price, "reason": "stop_loss"})
                elif tp_pct > 0 and upnl_pct >= tp_pct:
                    self._close_position(instance_id, sym, latest_price, reason="take_profit")
                    events.append({"type": "close", "symbol": sym, "price": latest_price, "reason": "take_profit"})

        total_equity = self._compute_total_equity(instance_id)
        self._update_instance_metrics(instance_id, total_equity)
        ts = int(time.time())
        self._save_equity_point(instance_id, ts, total_equity)
        result = {"instance_id": instance_id, "total_equity": total_equity, "events": events}
        for cb in self._tick_callbacks:
            try:
                cb(instance_id, result)
            except Exception:
                pass
        return result

    def _get_position(self, instance_id: str, symbol: str) -> Optional[dict]:
        conn = get_db()
        row = conn.execute(
            "SELECT * FROM virtual_positions WHERE instance_id = ? AND symbol = ?",
            (instance_id, symbol),
        ).fetchone()
        conn.close()
        return dict(row) if row else None

    def _open_position(self, instance_id: str, symbol: str, direction: int, price: float, capital: float):
        conn = get_db()
        # Bug 3 fix: charge 0.1% opening fee; qty net of fee
        qty = (capital * 0.999) / price
        fee = qty * price * 0.001
        now = int(time.time())
        conn.execute(
            """UPDATE virtual_positions SET side=?, entry_price=?, entry_time=?,
               quantity=?, current_price=?, unrealized_pnl=0, unrealized_pnl_pct=0
               WHERE instance_id=? AND symbol=?""",
            ("long" if direction == 1 else "short", price, now, qty, price, instance_id, symbol),
        )
        conn.execute(
            """INSERT INTO virtual_trades (trade_id, instance_id, symbol, side, price, quantity, fee, signal_time, executed_time)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (str(uuid.uuid4()), instance_id, symbol, "buy" if direction == 1 else "sell",
             price, qty, round(fee, 6), now, now),
        )
        conn.commit()
        conn.close()

    def _close_position(self, instance_id: str, symbol: str, price: float, reason: str = "signal"):
        pos = self._get_position(instance_id, symbol)
        if not pos or pos["side"] == "flat":
            return
        entry = pos["entry_price"]
        qty = pos["quantity"]
        pnl = qty * (price - entry) if pos["side"] == "long" else qty * (entry - price)
        close_fee = qty * price * 0.001
        pnl -= close_fee
        now = int(time.time())
        conn = get_db()
        conn.execute(
            """UPDATE virtual_positions SET side='flat', entry_price=0, entry_time=0,
               quantity=0, current_price=0, unrealized_pnl=0, unrealized_pnl_pct=0
               WHERE instance_id=? AND symbol=?""",
            (instance_id, symbol),
        )
        conn.execute(
            """INSERT INTO virtual_trades (trade_id, instance_id, symbol, side, price, quantity, fee, realized_pnl, signal_time, executed_time, trigger_reason)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (str(uuid.uuid4()), instance_id, symbol,
             "sell" if pos["side"] == "long" else "buy",
             price, qty, round(close_fee, 6), round(pnl, 2), now, now, reason),
        )
        conn.commit()
        conn.close()

    def _close_all_positions(self, instance_id: str, price: Optional[float]):
        conn = get_db()
        positions = conn.execute(
            "SELECT * FROM virtual_positions WHERE instance_id = ? AND side != 'flat'",
            (instance_id,),
        ).fetchall()
        conn.close()
        for p in positions:
            self._close_position(instance_id, p["symbol"], price or p["current_price"] or 50000)

    def _update_position_price(self, instance_id: str, symbol: str, price: float):
        conn = get_db()
        row = conn.execute(
            "SELECT * FROM virtual_positions WHERE instance_id = ? AND symbol = ?",
            (instance_id, symbol),
        ).fetchone()
        if row and row["side"] != "flat":
            entry = row["entry_price"]
            qty = row["quantity"]
            pnl = qty * (price - entry) if row["side"] == "long" else qty * (entry - price)
            pnl_pct = ((price - entry) / entry) * 100 if row["side"] == "long" else ((entry - price) / entry) * 100
            conn.execute(
                """UPDATE virtual_positions SET current_price=?, unrealized_pnl=?, unrealized_pnl_pct=?
                   WHERE instance_id=? AND symbol=?""",
                (price, round(pnl, 2), round(pnl_pct, 2), instance_id, symbol),
            )
        conn.commit()
        conn.close()

    def _compute_total_equity(self, instance_id: str) -> float:
        inst = self.get_instance(instance_id)
        if not inst:
            return 0.0
        capital = inst.initial_capital
        conn = get_db()
        positions = conn.execute(
            "SELECT * FROM virtual_positions WHERE instance_id = ?", (instance_id,)
        ).fetchall()
        unrealized = sum(p["unrealized_pnl"] or 0 for p in positions)
        trades = conn.execute(
            "SELECT SUM(realized_pnl) as rp FROM virtual_trades WHERE instance_id = ? AND realized_pnl IS NOT NULL",
            (instance_id,),
        ).fetchone()
        realized = trades["rp"] or 0
        conn.close()
        return capital + realized + unrealized

    def _update_instance_metrics(self, instance_id: str, total_equity: float):
        inst = self.get_instance(instance_id)
        if not inst:
            return
        capital = inst.initial_capital
        total_return = ((total_equity - capital) / capital) * 100 if capital > 0 else 0

        # Bug 1 fix: track running equity peak in context so drawdown reflects true historical peak
        ctx = self._running_instances.get(instance_id, {})
        stored_peak = ctx.get("_equity_peak", capital)
        peak = max(stored_peak, total_equity, capital)
        if instance_id in self._running_instances:
            self._running_instances[instance_id]["_equity_peak"] = peak
        drawdown = ((peak - total_equity) / peak * 100) if peak > 0 else 0
        max_dd = max(inst.max_drawdown, drawdown)

        conn = get_db()
        pos_rows = conn.execute(
            "SELECT * FROM virtual_positions WHERE instance_id = ?", (instance_id,)
        ).fetchall()
        upnl = sum(p["unrealized_pnl"] or 0 for p in pos_rows)
        trade_rows = conn.execute(
            "SELECT COUNT(*) as cnt, SUM(realized_pnl) as rp FROM virtual_trades WHERE instance_id = ? AND realized_pnl IS NOT NULL",
            (instance_id,),
        ).fetchone()
        trade_count = trade_rows["cnt"] or 0
        realized = trade_rows["rp"] or 0
        win_rows = conn.execute(
            "SELECT COUNT(*) as cnt FROM virtual_trades WHERE instance_id = ? AND realized_pnl > 0",
            (instance_id,),
        ).fetchone()
        win_count = win_rows["cnt"] or 0
        win_rate = (win_count / trade_count * 100) if trade_count > 0 else 0
        conn.close()

        self.update_instance(
            instance_id,
            total_equity=round(total_equity, 2),
            total_return=round(total_return, 4),
            unrealized_pnl=round(upnl, 2),
            realized_pnl=round(realized, 2),
            trade_count=trade_count,
            win_rate=round(win_rate, 2),
            max_drawdown=round(max_dd, 4),
        )

    def get_positions(self, instance_id: str) -> list[dict]:
        conn = get_db()
        rows = conn.execute(
            "SELECT * FROM virtual_positions WHERE instance_id = ?", (instance_id,)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_equity_history(self, instance_id: str) -> list[dict]:
        try:
            conn = get_db()
            rows = conn.execute(
                "SELECT timestamp, equity FROM paper_equity_history WHERE instance_id = ? ORDER BY timestamp ASC",
                (instance_id,),
            ).fetchall()
            conn.close()
            return [{"time": r["timestamp"], "equity": r["equity"]} for r in rows]
        except Exception:
            return []

    def get_trades(self, instance_id: str, limit: int = 100) -> list[dict]:
        conn = get_db()
        rows = conn.execute(
            "SELECT * FROM virtual_trades WHERE instance_id = ? ORDER BY executed_time DESC LIMIT ?",
            (instance_id, limit),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def _row_to_instance(self, row) -> PaperInstance:
        return PaperInstance(
            instance_id=row["instance_id"],
            name=row["name"],
            source=SourceType(row["source"]),
            source_task_id=row["source_task_id"],
            source_individual_id=row["source_individual_id"],
            strategy_config_id=row["strategy_config_id"],
            params_json=row["params_json"],
            symbols=json.loads(row["symbols"]) if isinstance(row["symbols"], str) else row["symbols"],
            initial_capital=row["initial_capital"],
            status=InstanceStatus(row["status"]),
            started_at=row["started_at"],
            stopped_at=row["stopped_at"],
            timeframe=row["timeframe"],
            total_equity=row["total_equity"] if row["total_equity"] else row["initial_capital"],
            total_return=row["total_return"] or 0,
            unrealized_pnl=row["unrealized_pnl"] or 0,
            realized_pnl=row["realized_pnl"] or 0,
            trade_count=row["trade_count"] or 0,
            win_rate=row["win_rate"] or 0,
            max_drawdown=row["max_drawdown"] or 0,
            auto_tick=bool(row["auto_tick"]),
            tick_interval_sec=row["tick_interval_sec"] or 10,
        )
