import json
import time
import uuid
import threading
import concurrent.futures
from typing import Optional

import numpy as np
import pandas as pd

_DATA_FETCH_EXECUTOR = concurrent.futures.ThreadPoolExecutor(
    max_workers=3, thread_name_prefix="paper_data"
)

from database import get_db as _get_local
from paper_trading.models import (
    PaperInstance, InstanceStatus, SourceType, CreateInstanceRequest,
)


def get_db():
    """Use local SQLite for reads/writes. Turso may be rate-limited."""
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

        from strategies.base import get_strategy_module
        mod = get_strategy_module(template_id)
        is_rotation = bool(mod and getattr(mod, "IS_ROTATION", False))
        rotation_symbols = list(getattr(mod, "ROTATION_SYMBOLS", [])) if is_rotation else []
        safe_symbol = getattr(mod, "SAFE_SYMBOL", "BIL") if is_rotation else ""
        spy_symbol = getattr(mod, "SPY_SYMBOL", "SPY") if is_rotation else ""

        conn = get_db()
        if is_rotation:
            # Include safe_symbol so we can park there; deduplicate with set
            init_syms = list(dict.fromkeys(rotation_symbols + ([safe_symbol] if safe_symbol else [])))
        else:
            init_syms = symbols
        for sym in init_syms:
            # Use SELECT-then-INSERT to avoid duplicates (no UNIQUE constraint on table)
            exists = conn.execute(
                "SELECT 1 FROM virtual_positions WHERE instance_id = ? AND symbol = ?",
                (instance_id, sym),
            ).fetchone()
            if not exists:
                conn.execute(
                    "INSERT INTO virtual_positions (instance_id, symbol, side) VALUES (?, ?, 'flat')",
                    (instance_id, sym),
                )
        conn.commit()
        conn.close()

        self.update_instance(instance_id, status="RUNNING")
        ctx: dict = {
            "template_id": template_id,
            "params": params,
            "symbols": symbols,
            "timeframe": inst.timeframe or "1d",
            "is_rotation": is_rotation,
        }
        if is_rotation:
            ctx["rotation_symbols"] = rotation_symbols
            ctx["safe_symbol"] = safe_symbol
            ctx["spy_symbol"] = spy_symbol
        self._running_instances[instance_id] = ctx

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

        from strategies.base import get_strategy_module
        mod = get_strategy_module(template_id)
        is_rotation = bool(mod and getattr(mod, "IS_ROTATION", False))

        # Load positions and realized PnL into memory to avoid Turso reads on every tick
        conn = get_db()
        pos_rows = conn.execute(
            "SELECT * FROM virtual_positions WHERE instance_id = ?", (instance_id,)
        ).fetchall()
        realized_row = conn.execute(
            "SELECT SUM(realized_pnl) as rp FROM virtual_trades WHERE instance_id = ? AND realized_pnl IS NOT NULL",
            (instance_id,),
        ).fetchone()
        conn.close()

        positions = {r["symbol"]: dict(r) for r in pos_rows}
        realized_pnl = float(realized_row["rp"] or 0) if realized_row else 0.0

        ctx: dict = {
            "template_id": template_id,
            "params": params,
            "symbols": symbols,
            "timeframe": inst.timeframe or "1d",
            "positions": positions,
            "realized_pnl": realized_pnl,
            "is_rotation": is_rotation,
        }
        if is_rotation:
            ctx["rotation_symbols"] = list(getattr(mod, "ROTATION_SYMBOLS", []))
            ctx["safe_symbol"] = getattr(mod, "SAFE_SYMBOL", "BIL")
            ctx["spy_symbol"] = getattr(mod, "SPY_SYMBOL", "SPY")
        self._running_instances[instance_id] = ctx

    _BAR_SEC = {"1d": 86400, "1h": 3600, "30m": 1800, "15m": 900, "5m": 300, "1m": 60}

    def _get_fresh_data(self, sym: str, timeframe: str):
        from backtest.data_cache import DATA_CACHE
        bar_sec = self._BAR_SEC.get(timeframe, 86400)
        now = int(time.time())
        # Only check in-memory — never block the main thread with a network call.
        df = DATA_CACHE.load(sym, timeframe)
        if df is not None and len(df) > 0:
            if now - int(df.index[-1]) <= bar_sec * 5:
                return df
            # Stale — background refresh, return stale data immediately.
            _DATA_FETCH_EXECUTOR.submit(DATA_CACHE.ensure, sym, None, None, timeframe, True)
            return df
        # Nothing in memory — fetch in executor with timeout so we never block.
        try:
            future = _DATA_FETCH_EXECUTOR.submit(
                DATA_CACHE.ensure, sym, None, None, timeframe, True
            )
            return future.result(timeout=15)
        except Exception:
            return None

    def prewarm_cache(self):
        """Background-fetch OHLCV for all running instances so first tick is fast."""
        from backtest.data_cache import DATA_CACHE
        for ctx in self._running_instances.values():
            timeframe = ctx.get("timeframe", "1m")
            if ctx.get("is_rotation"):
                rot_syms = ctx.get("rotation_symbols", [])
                spy = ctx.get("spy_symbol", "SPY")
                safe = ctx.get("safe_symbol", "BIL")
                for sym in set(rot_syms + [spy, safe]):
                    _DATA_FETCH_EXECUTOR.submit(DATA_CACHE.ensure, sym, None, None, "1d", True)
            else:
                for sym in ctx.get("symbols", []):
                    _DATA_FETCH_EXECUTOR.submit(DATA_CACHE.ensure, sym, None, None, timeframe, True)

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
        _t = {"start": time.time()}
        inst = self.get_instance(instance_id)
        _t["get_inst"] = time.time()
        if not inst or inst.status != InstanceStatus.RUNNING:
            return None
        ensure_called = False
        if instance_id not in self._running_instances:
            ensure_called = True
            try:
                self._ensure_context(instance_id)
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning("tick _ensure_context error for %s: %s", instance_id, e)
                return None
        _t["ensure"] = time.time()
        ctx = self._running_instances.get(instance_id)
        if not ctx:
            return None

        if ctx.get("is_rotation"):
            return self._tick_rotation(instance_id, ctx, inst)

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
        _t["equity"] = time.time()
        per_sym_capital = current_equity / max(len(symbols), 1)

        events = []
        processed_syms = 0
        _sym_ms: list = []
        for sym in symbols:
            _ts0 = time.time()
            df = self._get_fresh_data(sym, timeframe)
            _t[f"data_{sym}"] = time.time()
            if df is None or len(df) < 50:
                _sym_ms.append({"sym": sym, "ms": int((time.time()-_ts0)*1000), "skip": "no_data"})
                continue
            processed_syms += 1

            from strategies.base import get_strategy_module
            mod = get_strategy_module(template_id)
            if mod is None:
                _sym_ms.append({"sym": sym, "ms": int((time.time()-_ts0)*1000), "skip": "no_mod"})
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
            _sym_ms.append({"sym": sym, "ms": int((time.time()-_ts0)*1000)})

        # Skip DB writes if no symbols had usable data (Binance unreachable)
        if processed_syms == 0:
            return {"instance_id": instance_id, "total_equity": current_equity, "events": [],
                    "_dbg": {"ensure": ensure_called, "sym_ms": _sym_ms,
                             "get_inst_ms": int((_t["get_inst"]-_t["start"])*1000),
                             "ensure_ms": int((_t["ensure"]-_t["get_inst"])*1000)}}
        total_equity = self._compute_total_equity(instance_id)
        self._update_instance_metrics(instance_id, total_equity)
        _t["metrics"] = time.time()
        ts = int(time.time())
        self._save_equity_point(instance_id, ts, total_equity)
        _t["equity_save"] = time.time()
        result = {
            "instance_id": instance_id, "total_equity": total_equity, "events": events,
            "_dbg": {
                "ensure": ensure_called,
                "get_inst_ms": int((_t["get_inst"]-_t["start"])*1000),
                "ensure_ms": int((_t["ensure"]-_t["get_inst"])*1000),
                "equity_ms": int((_t["equity"]-_t["ensure"])*1000),
                "sym_ms": _sym_ms,
                "metrics_ms": int((_t["metrics"]-_t.get("equity",_t["ensure"]))*1000) if "metrics" in _t else 0,
                "save_equity_ms": int((_t["equity_save"]-_t["metrics"])*1000) if "metrics" in _t else 0,
            }
        }
        for cb in self._tick_callbacks:
            try:
                cb(instance_id, result)
            except Exception:
                pass
        return result

    def _tick_rotation(self, instance_id: str, ctx: dict, inst) -> Optional[dict]:
        from strategies.base import get_strategy_module
        from backtest.rotation_engine import _align_data
        _mod = get_strategy_module(ctx["template_id"])
        compute_indicators = _mod.compute_indicators
        score_asset = _mod.score_asset

        rotation_symbols: list[str] = ctx["rotation_symbols"]
        safe_symbol: str = ctx["safe_symbol"]
        spy_symbol: str = ctx["spy_symbol"]
        params: dict = ctx["params"]

        # Cooldown: daily strategy — skip ticks within 1h
        now = time.time()
        last_tick = ctx.get("_last_tick_ts", 0)
        if now - last_tick < 3600:
            return {"instance_id": instance_id, "events": [], "skipped": True}
        ctx["_last_tick_ts"] = now

        # Fetch 1d data for all symbols
        all_syms = list({*rotation_symbols, spy_symbol, safe_symbol})
        data_map: dict = {}
        for sym in all_syms:
            df = self._get_fresh_data(sym, "1d")
            if df is not None and len(df) >= 70:
                data_map[sym] = df

        idx, close_arrays = _align_data(data_map)
        if len(idx) < 70:
            return {"instance_id": instance_id, "events": [], "skipped": True, "reason": "not_enough_data"}

        risk_symbols = [s for s in rotation_symbols if s != safe_symbol and s in close_arrays]
        if not risk_symbols:
            return {"instance_id": instance_id, "events": [], "skipped": True, "reason": "no_risk_symbols"}

        has_spy = spy_symbol in close_arrays
        has_safe = safe_symbol in close_arrays

        indicators = {sym: compute_indicators(close_arrays[sym], sym, params) for sym in risk_symbols}

        spy_sma_period = int(params.get("spy_sma_period", 200))
        if has_spy:
            spy_close = close_arrays[spy_symbol]
            spy_sma = pd.Series(spy_close).rolling(spy_sma_period).mean().values
        else:
            spy_sma = np.full(len(idx), np.nan)
            spy_close = np.ones(len(idx))

        i = len(idx) - 1

        scores: dict[str, float] = {}
        for sym in risk_symbols:
            px = float(close_arrays[sym][i]) if not np.isnan(close_arrays[sym][i]) else 0.0
            if px <= 0:
                continue
            sc = score_asset(indicators[sym], sym, px, i, params)
            if not np.isnan(sc):
                scores[sym] = sc

        if not scores:
            return {"instance_id": instance_id, "events": [], "skipped": True, "reason": "no_scores"}

        spy_trend = True
        if has_spy and not np.isnan(spy_sma[i]):
            spy_trend = bool(spy_close[i] > spy_sma[i])

        # Find current holding
        conn = get_db()
        pos_rows = conn.execute(
            "SELECT * FROM virtual_positions WHERE instance_id = ? AND side != 'flat'",
            (instance_id,),
        ).fetchall()
        conn.close()
        current_asset = pos_rows[0]["symbol"] if pos_rows else None

        confidence_threshold = float(params.get("confidence_threshold", 0.10))
        best_sym = max(scores, key=lambda s: scores[s])
        best_score = scores[best_sym]

        # Determine target (mirrors rotation_engine logic)
        if current_asset is None:
            target_asset = best_sym if best_score > 0 else safe_symbol
        elif current_asset == safe_symbol:
            target_asset = best_sym if best_score > 0.02 else safe_symbol
        else:
            current_score = scores.get(current_asset, -999.0)
            if best_score > current_score * (1 + confidence_threshold):
                target_asset = best_sym
            elif current_score < -0.02:
                target_asset = safe_symbol
            else:
                target_asset = current_asset

        if not spy_trend and target_asset != safe_symbol:
            uup_score = scores.get("UUP", -999.0)
            target_score = scores.get(target_asset, -999.0)
            if uup_score > 0 and uup_score > target_score and "UUP" in close_arrays:
                target_asset = "UUP"
            elif target_score < 0:
                target_asset = safe_symbol

        events = []

        if target_asset != current_asset:
            # Close current
            if current_asset is not None:
                if current_asset in close_arrays and not np.isnan(close_arrays[current_asset][i]):
                    close_px = float(close_arrays[current_asset][i])
                else:
                    close_px = float((pos_rows[0].get("current_price") or 0) if pos_rows else 0)
                if close_px > 0:
                    self._close_position(instance_id, current_asset, close_px, reason="rotation")
                    events.append({"type": "close", "symbol": current_asset, "price": close_px, "reason": "rotation"})

            # Open target
            if target_asset and target_asset in close_arrays and not np.isnan(close_arrays[target_asset][i]):
                entry_px = float(close_arrays[target_asset][i])
                if entry_px > 0:
                    # Volatility-targeted position size
                    if target_asset != safe_symbol:
                        target_vol = float(params.get("target_vol", 0.80))
                        lookback_vol = int(params.get("lookback_vol", 20))
                        arr = close_arrays.get(target_asset, np.array([]))
                        start = max(0, i - lookback_vol)
                        segment = arr[start:i]
                        if len(segment) >= 2:
                            rets = np.diff(segment) / np.maximum(segment[:-1], 1e-8)
                            curr_vol = float(np.std(rets) * np.sqrt(252))
                            weight = min(1.0, target_vol / curr_vol) if curr_vol > 1e-8 else 1.0
                        else:
                            weight = 1.0
                    else:
                        weight = 1.0

                    alloc = self._compute_total_equity(instance_id) * weight
                    self._open_position(instance_id, target_asset, 1, entry_px, alloc)
                    events.append({"type": "open", "symbol": target_asset, "side": "long", "price": entry_px})
        else:
            # Update price for current holding
            if current_asset and current_asset in close_arrays and not np.isnan(close_arrays[current_asset][i]):
                self._update_position_price(instance_id, current_asset, float(close_arrays[current_asset][i]))

        total_equity = self._compute_total_equity(instance_id)
        self._update_instance_metrics(instance_id, total_equity)
        self._save_equity_point(instance_id, int(time.time()), total_equity)

        result = {
            "instance_id": instance_id,
            "total_equity": total_equity,
            "events": events,
            "rotation": {
                "current": current_asset,
                "target": target_asset,
                "scores": {k: round(v, 4) for k, v in scores.items()},
                "spy_trend": spy_trend,
            },
        }
        for cb in self._tick_callbacks:
            try:
                cb(instance_id, result)
            except Exception:
                pass
        return result

    def _get_position(self, instance_id: str, symbol: str) -> Optional[dict]:
        ctx = self._running_instances.get(instance_id)
        if ctx and "positions" in ctx:
            return ctx["positions"].get(symbol)
        # Fallback: read from DB (only when context not yet loaded)
        conn = get_db()
        row = conn.execute(
            "SELECT * FROM virtual_positions WHERE instance_id = ? AND symbol = ?",
            (instance_id, symbol),
        ).fetchone()
        conn.close()
        return dict(row) if row else None

    def _open_position(self, instance_id: str, symbol: str, direction: int, price: float, capital: float):
        qty = (capital * 0.999) / price
        fee = qty * price * 0.001
        side = "long" if direction == 1 else "short"
        now = int(time.time())
        conn = get_db()
        conn.execute_batch([
            (
                """UPDATE virtual_positions SET side=?, entry_price=?, entry_time=?,
                   quantity=?, current_price=?, unrealized_pnl=0, unrealized_pnl_pct=0
                   WHERE instance_id=? AND symbol=?""",
                (side, price, now, qty, price, instance_id, symbol),
            ),
            (
                """INSERT INTO virtual_trades (trade_id, instance_id, symbol, side, price, quantity, fee, signal_time, executed_time)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (str(uuid.uuid4()), instance_id, symbol, "buy" if direction == 1 else "sell",
                 price, qty, round(fee, 6), now, now),
            ),
        ])
        conn.close()
        # Update in-memory cache
        ctx = self._running_instances.get(instance_id)
        if ctx is not None:
            ctx.setdefault("positions", {})[symbol] = {
                "instance_id": instance_id, "symbol": symbol, "side": side,
                "entry_price": price, "entry_time": now, "quantity": qty,
                "current_price": price, "unrealized_pnl": 0.0, "unrealized_pnl_pct": 0.0,
            }

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
        conn.execute_batch([
            (
                """UPDATE virtual_positions SET side='flat', entry_price=0, entry_time=0,
                   quantity=0, current_price=0, unrealized_pnl=0, unrealized_pnl_pct=0
                   WHERE instance_id=? AND symbol=?""",
                (instance_id, symbol),
            ),
            (
                """INSERT INTO virtual_trades (trade_id, instance_id, symbol, side, price, quantity, fee, realized_pnl, signal_time, executed_time, trigger_reason)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (str(uuid.uuid4()), instance_id, symbol,
                 "sell" if pos["side"] == "long" else "buy",
                 price, qty, round(close_fee, 6), round(pnl, 2), now, now, reason),
            ),
        ])
        conn.close()
        # Update in-memory cache
        ctx = self._running_instances.get(instance_id)
        if ctx is not None:
            ctx.setdefault("positions", {})[symbol] = {
                "instance_id": instance_id, "symbol": symbol, "side": "flat",
                "entry_price": 0.0, "entry_time": 0, "quantity": 0.0,
                "current_price": 0.0, "unrealized_pnl": 0.0, "unrealized_pnl_pct": 0.0,
            }
            ctx["realized_pnl"] = ctx.get("realized_pnl", 0.0) + pnl

    def _close_all_positions(self, instance_id: str, price: Optional[float]):
        ctx = self._running_instances.get(instance_id)
        if ctx and "positions" in ctx:
            symbols = [sym for sym, p in ctx["positions"].items() if p.get("side") != "flat"]
        else:
            conn = get_db()
            rows = conn.execute(
                "SELECT symbol, current_price FROM virtual_positions WHERE instance_id = ? AND side != 'flat'",
                (instance_id,),
            ).fetchall()
            conn.close()
            symbols = [r["symbol"] for r in rows]
            if not price:
                price_map = {r["symbol"]: r["current_price"] for r in rows}
        for sym in symbols:
            fallback = price or (price_map.get(sym, 50000) if "price_map" in dir() else 50000)
            self._close_position(instance_id, sym, fallback)

    def _update_position_price(self, instance_id: str, symbol: str, price: float):
        ctx = self._running_instances.get(instance_id)
        if ctx and "positions" in ctx:
            pos = ctx["positions"].get(symbol)
            if pos and pos.get("side") != "flat":
                entry = pos["entry_price"]
                qty = pos["quantity"]
                pnl = qty * (price - entry) if pos["side"] == "long" else qty * (entry - price)
                pnl_pct = ((price - entry) / entry) * 100 if pos["side"] == "long" else ((entry - price) / entry) * 100
                pos["current_price"] = price
                pos["unrealized_pnl"] = round(pnl, 2)
                pos["unrealized_pnl_pct"] = round(pnl_pct, 2)
            return
        # Fallback: write to DB (only when context not yet loaded)
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
        ctx = self._running_instances.get(instance_id)
        if ctx and "positions" in ctx:
            unrealized = sum(p.get("unrealized_pnl") or 0 for p in ctx["positions"].values())
            realized = ctx.get("realized_pnl", 0.0)
            return capital + realized + unrealized
        # Fallback: read from DB
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

        ctx = self._running_instances.get(instance_id, {})
        stored_peak = ctx.get("_equity_peak", capital)
        peak = max(stored_peak, total_equity, capital)
        if instance_id in self._running_instances:
            self._running_instances[instance_id]["_equity_peak"] = peak
        drawdown = ((peak - total_equity) / peak * 100) if peak > 0 else 0
        max_dd = max(inst.max_drawdown, drawdown)

        # Use in-memory position/trade data when available (avoids 4 Turso reads)
        if ctx and "positions" in ctx:
            upnl = sum(p.get("unrealized_pnl") or 0 for p in ctx["positions"].values())
            realized = ctx.get("realized_pnl", 0.0)
            # Batch both COUNT queries into a single HTTP request
            conn = get_db()
            results = conn.fetch_batch([
                ("SELECT COUNT(*) as cnt FROM virtual_trades WHERE instance_id = ? AND realized_pnl IS NOT NULL", (instance_id,)),
                ("SELECT COUNT(*) as cnt FROM virtual_trades WHERE instance_id = ? AND realized_pnl > 0", (instance_id,)),
            ])
            conn.close()
            r0 = results[0].fetchone()
            r1 = results[1].fetchone()
            trade_count = r0["cnt"] if r0 else 0
            win_count = r1["cnt"] if r1 else 0
        else:
            conn = get_db()
            pos_rows = conn.execute(
                "SELECT unrealized_pnl FROM virtual_positions WHERE instance_id = ?", (instance_id,)
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
            conn.close()

        win_rate = (win_count / trade_count * 100) if trade_count > 0 else 0
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
        # Sync in-memory position prices back to DB so frontend sees current prices
        if ctx and "positions" in ctx:
            conn = get_db()
            for sym, p in ctx["positions"].items():
                if p.get("side") != "flat":
                    conn.execute(
                        """UPDATE virtual_positions SET current_price=?, unrealized_pnl=?, unrealized_pnl_pct=?
                           WHERE instance_id=? AND symbol=?""",
                        (p["current_price"], p["unrealized_pnl"], p["unrealized_pnl_pct"], instance_id, sym),
                    )
            conn.commit()
            conn.close()

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
