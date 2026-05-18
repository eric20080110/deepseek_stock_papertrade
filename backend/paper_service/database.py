import json
import os
import sqlite3
import urllib.request
import urllib.error

TURSO_URL = os.environ.get("TURSO_URL", "")
TURSO_TOKEN = os.environ.get("TURSO_TOKEN", "")

LOCAL_DB_PATH = os.environ.get("LOCAL_DB_PATH", "/tmp/ohlcv_cache.db")

_local_conn: sqlite3.Connection | None = None
_turso_instance = None


class _Row(dict):
    def __init__(self, columns, values):
        super().__init__(zip(columns, values))
        self._values = values
    def __getitem__(self, key):
        if isinstance(key, (int,)): return self._values[key]
        return super().__getitem__(key)
    def get(self, key, default=None):
        if isinstance(key, (int,)):
            try: return self._values[key]
            except IndexError: return default
        return super().get(key, default)


class _TursoResult:
    def __init__(self, raw: dict):
        result = raw.get("response", {}).get("result", {})
        cols = [c["name"] for c in result.get("cols", [])]
        self._rows = []
        for row in result.get("rows", []):
            self._rows.append(_Row(cols, [_turso_cast(cell) for cell in row]))
    def fetchone(self): return self._rows[0] if self._rows else None
    def fetchall(self): return self._rows
    def __iter__(self): return iter(self._rows)


def _turso_cast(cell: dict):
    t, v = cell.get("type"), cell.get("value")
    if v is None: return None
    if t == "integer": return int(v)
    if t == "float": return float(v)
    return v


def _sql_quote(val) -> str:
    if val is None: return "NULL"
    if isinstance(val, bool): return "1" if val else "0"
    if isinstance(val, int): return str(val)
    if isinstance(val, float): return repr(val)
    return f"'{str(val).replace(chr(39), chr(39)+chr(39))}'"


def _interpolate(sql: str, params) -> str:
    if params is None: return sql
    if isinstance(params, list): params = tuple(params)
    parts = sql.split("?")
    if len(parts) - 1 != len(params):
        raise ValueError(f"Parameter count mismatch")
    out = parts[0]
    for i, p in enumerate(params):
        out += _sql_quote(p) + parts[i + 1]
    return out


class _TursoConnection:
    def __init__(self, url, token):
        self._url, self._token = url, token
        self.row_factory = None
    def _request(self, stmts: list[dict], label: str = "query"):
        data = json.dumps({"requests": stmts}).encode("utf-8")
        req = urllib.request.Request(
            f"{self._url}/v2/pipeline", data=data,
            headers={"Authorization": f"Bearer {self._token}", "Content-Type": "application/json"},
            method="POST",
        )
        last_err = None
        for attempt in range(3):
            try:
                with urllib.request.urlopen(req, timeout=120) as resp:
                    resp_data = json.loads(resp.read().decode("utf-8"))
                for r in resp_data.get("results", []):
                    if r.get("type") == "error":
                        raise RuntimeError(f"Turso {label} error: {r.get('error', {}).get('message', str(r))}")
                return resp_data
            except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError) as e:
                last_err = e
                if attempt < 2:
                    import time as _time
                    _time.sleep(2 ** attempt)
        raise RuntimeError(f"Turso {label} failed after 3 retries: {last_err}")
    def execute(self, sql, params=None):
        return _TursoResult(self._request([{"type": "execute", "stmt": {"sql": _interpolate(sql, params)}}])["results"][0])
    def executemany(self, sql, params_list):
        self._request([{"type": "execute", "stmt": {"sql": _interpolate(sql, p)}} for p in params_list])
    def executescript(self, sql):
        stmts = [s.strip() for s in sql.split(";") if s.strip()]
        if stmts: self._request([{"type": "execute", "stmt": {"sql": s}} for s in stmts])
    def commit(self): pass
    def close(self): pass


_TURSO_SCHEMA = """
CREATE TABLE IF NOT EXISTS strategy_configs (
    config_id       TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    description     TEXT DEFAULT '',
    template_id     TEXT,
    is_template     INTEGER DEFAULT 0,
    is_locked       INTEGER DEFAULT 0,
    locked_by_task_id TEXT,
    parameters_json TEXT NOT NULL DEFAULT '[]',
    constraints_json TEXT NOT NULL DEFAULT '[]',
    created_at      INTEGER NOT NULL,
    updated_at      INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS paper_instances (
    instance_id         TEXT PRIMARY KEY,
    name                TEXT NOT NULL,
    source              TEXT NOT NULL DEFAULT 'manual',
    source_task_id      TEXT,
    source_individual_id TEXT,
    strategy_config_id  TEXT NOT NULL,
    params_json         TEXT NOT NULL DEFAULT '{}',
    symbols             TEXT NOT NULL DEFAULT '[]',
    initial_capital     REAL DEFAULT 10000,
    status              TEXT NOT NULL DEFAULT 'INITIALIZING',
    started_at          INTEGER NOT NULL,
    stopped_at          INTEGER,
    timeframe           TEXT DEFAULT '1d',
    total_equity        REAL DEFAULT 0,
    total_return        REAL DEFAULT 0,
    unrealized_pnl      REAL DEFAULT 0,
    realized_pnl        REAL DEFAULT 0,
    trade_count         INTEGER DEFAULT 0,
    win_rate            REAL DEFAULT 0,
    max_drawdown        REAL DEFAULT 0,
    auto_tick           INTEGER DEFAULT 0,
    tick_interval_sec   INTEGER DEFAULT 10
);
CREATE TABLE IF NOT EXISTS virtual_positions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    instance_id     TEXT NOT NULL,
    symbol          TEXT NOT NULL,
    side            TEXT DEFAULT 'flat',
    entry_price     REAL DEFAULT 0,
    entry_time      INTEGER DEFAULT 0,
    quantity        REAL DEFAULT 0,
    current_price   REAL DEFAULT 0,
    unrealized_pnl  REAL DEFAULT 0,
    unrealized_pnl_pct REAL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_positions_inst ON virtual_positions(instance_id, symbol);
CREATE TABLE IF NOT EXISTS virtual_trades (
    trade_id        TEXT PRIMARY KEY,
    instance_id     TEXT NOT NULL,
    symbol          TEXT NOT NULL,
    side            TEXT NOT NULL,
    price           REAL DEFAULT 0,
    quantity        REAL DEFAULT 0,
    fee             REAL DEFAULT 0,
    realized_pnl    REAL,
    signal_time     INTEGER NOT NULL,
    executed_time   INTEGER NOT NULL,
    trigger_reason  TEXT DEFAULT 'strategy_signal'
);
CREATE INDEX IF NOT EXISTS idx_trades_inst ON virtual_trades(instance_id, signal_time);
CREATE TABLE IF NOT EXISTS ohlcv_data (
    symbol      TEXT NOT NULL,
    timeframe   TEXT NOT NULL,
    timestamp   INTEGER NOT NULL,
    open        REAL NOT NULL DEFAULT 0,
    high        REAL NOT NULL DEFAULT 0,
    low         REAL NOT NULL DEFAULT 0,
    close       REAL NOT NULL DEFAULT 0,
    volume      REAL NOT NULL DEFAULT 0,
    created_at  INTEGER NOT NULL,
    PRIMARY KEY (symbol, timeframe, timestamp)
);
"""


class _EmptyResult:
    def fetchone(self): return None
    def fetchall(self): return []
    def __iter__(self): return iter([])

class _EmptyConnection:
    row_factory = None
    def execute(self, sql, params=None): return _EmptyResult()
    def executemany(self, sql, params_list): pass
    def executescript(self, sql): pass
    def commit(self): pass
    def close(self): pass

def get_turso() -> _TursoConnection | _EmptyConnection:
    global _turso_instance
    if not TURSO_URL or not TURSO_TOKEN:
        return _EmptyConnection()
    if _turso_instance is None:
        _turso_instance = _TursoConnection(TURSO_URL, TURSO_TOKEN)
    return _turso_instance


def get_db() -> sqlite3.Connection:
    global _local_conn
    if _local_conn is None:
        os.makedirs(os.path.dirname(LOCAL_DB_PATH) or ".", exist_ok=True)
        _local_conn = sqlite3.connect(LOCAL_DB_PATH)
        _local_conn.row_factory = sqlite3.Row
        _local_conn.execute("PRAGMA journal_mode=WAL")
        _local_conn.execute("PRAGMA busy_timeout=5000")
        _local_conn.execute("""
            CREATE TABLE IF NOT EXISTS ohlcv_data (
                symbol TEXT NOT NULL, timeframe TEXT NOT NULL,
                timestamp INTEGER NOT NULL, open REAL, high REAL,
                low REAL, close REAL, volume REAL,
                created_at INTEGER NOT NULL DEFAULT (strftime('%s','now')),
                PRIMARY KEY (symbol, timeframe, timestamp)
            )
        """)
    return _local_conn


def init_db():
    t = get_turso()
    for stmt in _TURSO_SCHEMA.split(";"):
        stmt = stmt.strip()
        if stmt:
            try: t.execute(stmt).fetchall()
            except: pass
