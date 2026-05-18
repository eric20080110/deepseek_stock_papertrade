import json, time, uuid
from typing import Optional
from database import get_turso as get_db
from paper_trading.models import PaperInstance, VirtualPosition, VirtualTrade, InstanceStatus, SourceType, CreateInstanceRequest


class PaperTradingEngine:
    def __init__(self):
        self.MAX_INSTANCES = 5
        self._running_instances: dict[str, dict] = {}

    def create_instance(self, req: CreateInstanceRequest) -> PaperInstance:
        conn = get_db()
        running = conn.execute("SELECT COUNT(*) FROM paper_instances WHERE status IN ('INITIALIZING','RUNNING','PAUSED')").fetchone()[0]
        if running >= self.MAX_INSTANCES: raise ValueError(f"Max {self.MAX_INSTANCES} instances allowed")
        instance_id = str(uuid.uuid4())
        now = int(time.time())
        conn.execute("INSERT INTO paper_instances (instance_id,name,source,source_task_id,source_individual_id,strategy_config_id,params_json,symbols,initial_capital,status,started_at,timeframe) VALUES (?,?,?,?,?,?,?,?,?,'INITIALIZING',?,?)", (instance_id, req.name, req.source.value, req.source_task_id, req.source_individual_id, req.strategy_config_id, json.dumps(req.params), json.dumps(req.symbols), req.initial_capital, now, req.timeframe))
        conn.commit(); conn.close()
        return self.get_instance(instance_id)

    def get_instance(self, instance_id: str) -> Optional[PaperInstance]:
        conn = get_db()
        row = conn.execute("SELECT * FROM paper_instances WHERE instance_id = ?", (instance_id,)).fetchone()
        conn.close()
        return self._row_to_instance(row) if row else None

    def list_instances(self) -> list[PaperInstance]:
        conn = get_db()
        rows = conn.execute("SELECT * FROM paper_instances ORDER BY started_at DESC").fetchall()
        conn.close()
        return [self._row_to_instance(r) for r in rows]

    def update_instance(self, instance_id: str, **kwargs):
        conn = get_db()
        sets = ", ".join(f"{k} = ?" for k in kwargs)
        conn.execute(f"UPDATE paper_instances SET {sets} WHERE instance_id = ?", list(kwargs.values()) + [instance_id])
        conn.commit(); conn.close()

    def pause_instance(self, instance_id: str) -> bool:
        inst = self.get_instance(instance_id)
        if not inst or inst.status != InstanceStatus.RUNNING: return False
        self.update_instance(instance_id, status="PAUSED"); return True

    def resume_instance(self, instance_id: str) -> bool:
        inst = self.get_instance(instance_id)
        if not inst or inst.status != InstanceStatus.PAUSED: return False
        self.update_instance(instance_id, status="RUNNING"); return True

    def stop_instance(self, instance_id: str) -> bool:
        inst = self.get_instance(instance_id)
        if not inst: return False
        self._close_all_positions(instance_id, None)
        self.update_instance(instance_id, status="STOPPED", stopped_at=int(time.time()))
        return True

    def delete_instance(self, instance_id: str):
        conn = get_db()
        conn.execute("DELETE FROM virtual_trades WHERE instance_id = ?", (instance_id,))
        conn.execute("DELETE FROM virtual_positions WHERE instance_id = ?", (instance_id,))
        conn.execute("DELETE FROM paper_instances WHERE instance_id = ?", (instance_id,))
        conn.commit(); conn.close()

    def set_auto_tick(self, instance_id: str, enabled: bool, interval_sec: int = 10) -> bool:
        inst = self.get_instance(instance_id)
        if not inst: return False
        self.update_instance(instance_id, auto_tick=1 if enabled else 0, tick_interval_sec=interval_sec)
        return True

    def run_initialization(self, instance_id: str):
        inst = self.get_instance(instance_id)
        if not inst: return
        symbols = json.loads(inst.symbols) if isinstance(inst.symbols, str) else inst.symbols
        params = json.loads(inst.params_json) if isinstance(inst.params_json, str) else inst.params_json
        sid = inst.strategy_config_id
        from database import get_turso as db2
        conn = db2()
        row = conn.execute("SELECT template_id FROM strategy_configs WHERE config_id = ?", (sid,)).fetchone()
        conn.close()
        template_id = row["template_id"] if row else sid
        timeframe = inst.timeframe or "1d"
        data_map = {}
        for sym in symbols:
            from backtest.data_cache import DATA_CACHE
            df = DATA_CACHE.ensure(sym, timeframe=timeframe)
            if df is not None: data_map[sym] = df
        for sym in symbols:
            conn = get_db()
            conn.execute("INSERT INTO virtual_positions (instance_id, symbol, side) VALUES (?, ?, 'flat')", (instance_id, sym))
            conn.commit(); conn.close()
        max_bars = len(list(data_map.values())[0]) if data_map else 500
        self.update_instance(instance_id, status="RUNNING")
        self._running_instances[instance_id] = {"template_id": template_id, "params": params, "symbols": symbols, "data_map": data_map, "bar_idx": 0, "max_bars": max_bars}

    def tick(self, instance_id: str) -> Optional[dict]:
        inst = self.get_instance(instance_id)
        if not inst or inst.status != InstanceStatus.RUNNING: return None
        ctx = self._running_instances.get(instance_id)
        if not ctx: return None
        symbols, params, template_id, data_map = ctx["symbols"], ctx["params"], ctx["template_id"], ctx["data_map"]
        idx = ctx["bar_idx"]
        events = []
        for sym in symbols:
            df = data_map.get(sym)
            if df is None or idx >= len(df): continue
            bar = df.iloc[:idx]
            if len(bar) < 50: continue
            from strategies.base import get_strategy_module
            mod = get_strategy_module(template_id)
            if mod is None: continue
            try: signal = int(mod.generate_signals(bar, params).iloc[-1])
            except Exception: signal = 0
            latest_price = float(df.iloc[idx]["open"])
            pos = self._get_position(instance_id, sym)
            current_side = pos["side"] if pos else "flat"
            if signal != 0 and signal != (1 if current_side == "long" else -1 if current_side == "short" else 0):
                if current_side != "flat":
                    self._close_position(instance_id, sym, latest_price)
                    events.append({"type": "close", "symbol": sym, "price": latest_price, "reason": "signal"})
                    current_side = "flat"
                entry = latest_price * (1.001 if signal == 1 else 0.999)
                self._open_position(instance_id, sym, signal, entry, params.get("initial_capital", 10000))
                events.append({"type": "open", "symbol": sym, "side": "long" if signal == 1 else "short", "price": entry})
            self._update_position_price(instance_id, sym, latest_price)
        ctx["bar_idx"] = idx + 1
        total_equity = self._compute_total_equity(instance_id)
        self._update_instance_metrics(instance_id, total_equity)
        return {"instance_id": instance_id, "total_equity": total_equity, "events": events}

    def _get_position(self, instance_id: str, symbol: str) -> Optional[dict]:
        conn = get_db()
        row = conn.execute("SELECT * FROM virtual_positions WHERE instance_id = ? AND symbol = ?", (instance_id, symbol)).fetchone()
        conn.close(); return dict(row) if row else None

    def _open_position(self, instance_id: str, symbol: str, direction: int, price: float, capital: float):
        conn = get_db(); qty = (capital * 0.99) / price; now = int(time.time())
        conn.execute("UPDATE virtual_positions SET side=?,entry_price=?,entry_time=?,quantity=?,current_price=?,unrealized_pnl=0,unrealized_pnl_pct=0 WHERE instance_id=? AND symbol=?", ("long" if direction == 1 else "short", price, now, qty, price, instance_id, symbol))
        conn.execute("INSERT INTO virtual_trades (trade_id,instance_id,symbol,side,price,quantity,fee,signal_time,executed_time) VALUES (?,?,?,?,?,?,?,?,?)", (str(uuid.uuid4()), instance_id, symbol, "buy" if direction == 1 else "sell", price, qty, 0, now, now))
        conn.commit(); conn.close()

    def _close_position(self, instance_id: str, symbol: str, price: float):
        pos = self._get_position(instance_id, symbol)
        if not pos or pos["side"] == "flat": return
        entry, qty = pos["entry_price"], pos["quantity"]
        pnl = qty * (price - entry) if pos["side"] == "long" else qty * (entry - price)
        pnl -= qty * price * 0.001
        now = int(time.time())
        conn = get_db()
        conn.execute("UPDATE virtual_positions SET side='flat',entry_price=0,entry_time=0,quantity=0,current_price=0,unrealized_pnl=0,unrealized_pnl_pct=0 WHERE instance_id=? AND symbol=?", (instance_id, symbol))
        conn.execute("INSERT INTO virtual_trades (trade_id,instance_id,symbol,side,price,quantity,fee,realized_pnl,signal_time,executed_time,trigger_reason) VALUES (?,?,?,?,?,?,?,?,?,?,?)", (str(uuid.uuid4()), instance_id, symbol, "sell" if pos["side"] == "long" else "buy", price, qty, qty * price * 0.001, round(pnl, 2), now, now, "signal"))
        conn.commit(); conn.close()

    def _close_all_positions(self, instance_id: str, price: Optional[float]):
        conn = get_db()
        positions = conn.execute("SELECT * FROM virtual_positions WHERE instance_id = ? AND side != 'flat'", (instance_id,)).fetchall()
        conn.close()
        for p in positions: self._close_position(instance_id, p["symbol"], price or p["current_price"] or 50000)

    def _update_position_price(self, instance_id: str, symbol: str, price: float):
        conn = get_db()
        row = conn.execute("SELECT * FROM virtual_positions WHERE instance_id = ? AND symbol = ?", (instance_id, symbol)).fetchone()
        if row and row["side"] != "flat":
            entry, qty = row["entry_price"], row["quantity"]
            pnl = qty * (price - entry) if row["side"] == "long" else qty * (entry - price)
            pnl_pct = ((price - entry) / entry) * 100
            conn.execute("UPDATE virtual_positions SET current_price=?,unrealized_pnl=?,unrealized_pnl_pct=? WHERE instance_id=? AND symbol=?", (price, round(pnl, 2), round(pnl_pct, 2), instance_id, symbol))
        conn.commit(); conn.close()

    def _compute_total_equity(self, instance_id: str) -> float:
        inst = self.get_instance(instance_id)
        if not inst: return 0.0
        capital = inst.initial_capital * len(json.loads(inst.symbols) if isinstance(inst.symbols, str) else inst.symbols)
        conn = get_db()
        upnl = sum(p["unrealized_pnl"] or 0 for p in conn.execute("SELECT * FROM virtual_positions WHERE instance_id = ?", (instance_id,)).fetchall())
        rp = conn.execute("SELECT SUM(realized_pnl) as rp FROM virtual_trades WHERE instance_id = ? AND realized_pnl IS NOT NULL", (instance_id,)).fetchone()["rp"] or 0
        conn.close()
        return capital + rp + upnl

    def _update_instance_metrics(self, instance_id: str, total_equity: float):
        inst = self.get_instance(instance_id)
        if not inst: return
        capital = inst.initial_capital * len(json.loads(inst.symbols) if isinstance(inst.symbols, str) else inst.symbols)
        total_return = ((total_equity - capital) / capital) * 100 if capital > 0 else 0
        conn = get_db()
        upnl = sum(p["unrealized_pnl"] or 0 for p in conn.execute("SELECT * FROM virtual_positions WHERE instance_id = ?", (instance_id,)).fetchall())
        tr = conn.execute("SELECT COUNT(*) as cnt, SUM(realized_pnl) as rp FROM virtual_trades WHERE instance_id = ? AND realized_pnl IS NOT NULL", (instance_id,)).fetchone()
        trade_count = tr["cnt"] or 0; realized = tr["rp"] or 0
        win = conn.execute("SELECT COUNT(*) as cnt FROM virtual_trades WHERE instance_id = ? AND realized_pnl > 0", (instance_id,)).fetchone()["cnt"] or 0
        conn.close()
        win_rate = (win / trade_count * 100) if trade_count > 0 else 0
        self.update_instance(instance_id, total_equity=round(total_equity,2), total_return=round(total_return,4), unrealized_pnl=round(upnl,2), realized_pnl=round(realized,2), trade_count=trade_count, win_rate=round(win_rate,2))

    def get_positions(self, instance_id: str) -> list[dict]:
        conn = get_db()
        rows = conn.execute("SELECT * FROM virtual_positions WHERE instance_id = ?", (instance_id,)).fetchall()
        conn.close(); return [dict(r) for r in rows]

    def get_trades(self, instance_id: str, limit: int = 100) -> list[dict]:
        conn = get_db()
        rows = conn.execute("SELECT * FROM virtual_trades WHERE instance_id = ? ORDER BY executed_time DESC LIMIT ?", (instance_id, limit)).fetchall()
        conn.close(); return [dict(r) for r in rows]

    def _row_to_instance(self, row) -> PaperInstance:
        return PaperInstance(instance_id=row["instance_id"], name=row["name"], source=SourceType(row["source"]), source_task_id=row["source_task_id"], source_individual_id=row["source_individual_id"], strategy_config_id=row["strategy_config_id"], params_json=row["params_json"], symbols=json.loads(row["symbols"]) if isinstance(row["symbols"],str) else row["symbols"], initial_capital=row["initial_capital"], status=InstanceStatus(row["status"]), started_at=row["started_at"], stopped_at=row["stopped_at"], timeframe=row["timeframe"], total_equity=row["total_equity"] or 0, total_return=row["total_return"] or 0, unrealized_pnl=row["unrealized_pnl"] or 0, realized_pnl=row["realized_pnl"] or 0, trade_count=row["trade_count"] or 0, win_rate=row["win_rate"] or 0, max_drawdown=row["max_drawdown"] or 0, auto_tick=bool(row["auto_tick"]), tick_interval_sec=row["tick_interval_sec"] or 10)
