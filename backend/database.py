import json
import os
import sqlite3
import urllib.request
import urllib.error

# Load .env from backend dir or repo root (dev convenience)
def _load_dotenv():
    for _p in (
        os.path.join(os.path.dirname(__file__), ".env"),
        os.path.join(os.path.dirname(__file__), "..", ".env"),
    ):
        if os.path.exists(_p):
            with open(_p) as _f:
                for _line in _f:
                    _line = _line.strip()
                    if _line and not _line.startswith("#") and "=" in _line:
                        _k, _, _v = _line.partition("=")
                        os.environ.setdefault(_k.strip(), _v.strip())
            break

_load_dotenv()

LOCAL_DB_PATH = os.environ.get(
    "LOCAL_DB_PATH",
    os.path.join(os.path.dirname(__file__), "quantgene_local.db"),
)

TURSO_URL = os.environ.get("TURSO_URL")
TURSO_TOKEN = os.environ.get("TURSO_TOKEN")

if not TURSO_URL or not TURSO_TOKEN:
    import warnings
    warnings.warn(
        "TURSO_URL and TURSO_TOKEN env vars not set. Turso remote DB unavailable."
    )

_turso_instance = None


class _Row(dict):
    def __init__(self, columns, values):
        super().__init__(zip(columns, values))
        self._values = values

    def __getitem__(self, key):
        if isinstance(key, (int,)):
            return self._values[key]
        return super().__getitem__(key)

    def get(self, key, default=None):
        if isinstance(key, (int,)):
            try:
                return self._values[key]
            except IndexError:
                return default
        return super().get(key, default)


class _TursoResult:
    def __init__(self, raw: dict):
        result = raw.get("response", {}).get("result", {})
        cols = [c["name"] for c in result.get("cols", [])]
        self._rows = []
        for row in result.get("rows", []):
            vals = [_turso_cast(cell) for cell in row]
            self._rows.append(_Row(cols, vals))

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return self._rows

    def __iter__(self):
        return iter(self._rows)


def _turso_cast(cell: dict):
    t = cell.get("type")
    v = cell.get("value")
    if v is None:
        return None
    if t == "integer":
        return int(v)
    if t == "float":
        return float(v)
    return v


def _sql_quote(val) -> str:
    if val is None:
        return "NULL"
    if isinstance(val, bool):
        return "1" if val else "0"
    if isinstance(val, int):
        return str(val)
    if isinstance(val, float):
        return repr(val)
    escaped = str(val).replace("'", "''")
    return f"'{escaped}'"


def _interpolate(sql: str, params) -> str:
    if params is None:
        return sql
    if isinstance(params, list):
        params = tuple(params)
    parts = sql.split("?")
    if len(parts) - 1 != len(params):
        raise ValueError(f"Parameter count mismatch: {len(parts)-1} placeholders vs {len(params)} params")
    out = parts[0]
    for i, p in enumerate(params):
        out += _sql_quote(p) + parts[i + 1]
    return out


class _TursoConnection:
    def __init__(self, url, token):
        if url.startswith("libsql://"):
            url = url.replace("libsql://", "https://")
        self._url = url
        self._token = token
        self.row_factory = None

    def _request(self, stmts: list[dict], label: str = "query"):
        data = json.dumps({"requests": stmts}).encode("utf-8")
        req = urllib.request.Request(
            f"{self._url}/v2/pipeline",
            data=data,
            headers={
                "Authorization": f"Bearer {self._token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        import concurrent.futures as _cf
        def _do_request():
            with urllib.request.urlopen(req, timeout=3) as resp:
                return json.loads(resp.read().decode("utf-8"))
        try:
            with _cf.ThreadPoolExecutor(max_workers=1) as ex:
                future = ex.submit(_do_request)
                resp_data = future.result(timeout=4)
            for r in resp_data.get("results", []):
                if r.get("type") == "error":
                    raise RuntimeError(f"Turso {label} error: {r.get('error', {}).get('message', str(r))}")
            return resp_data
        except _cf.TimeoutError:
            raise RuntimeError(f"Turso {label} timed out") from None
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError) as e:
            raise RuntimeError(f"Turso {label} failed: {e}") from e

    def execute(self, sql, params=None):
        resp = self._request(
            [{"type": "execute", "stmt": {"sql": _interpolate(sql, params)}}],
            label="execute",
        )
        return _TursoResult(resp["results"][0])

    def executemany(self, sql, params_list):
        stmts = [
            {"type": "execute", "stmt": {"sql": _interpolate(sql, p)}}
            for p in params_list
        ]
        self._request(stmts, label="executemany")

    def execute_batch(self, sql_params: list[tuple]):
        """Send multiple different SQL statements in a single HTTP request."""
        stmts = [
            {"type": "execute", "stmt": {"sql": _interpolate(sql, params)}}
            for sql, params in sql_params
        ]
        self._request(stmts, label="execute_batch")

    def fetch_batch(self, sql_params: list[tuple]) -> list:
        """Send multiple SELECTs in one HTTP request; returns list of _TursoResult."""
        stmts = [
            {"type": "execute", "stmt": {"sql": _interpolate(sql, params)}}
            for sql, params in sql_params
        ]
        resp = self._request(stmts, label="fetch_batch")
        return [_TursoResult(r) for r in resp.get("results", [])]

    def executescript(self, sql):
        stmts = [s.strip() for s in sql.split(";") if s.strip()]
        if not stmts:
            return
        reqs = [{"type": "execute", "stmt": {"sql": s}} for s in stmts]
        self._request(reqs, label="executescript")

    def commit(self):
        pass

    def close(self):
        pass


import threading as _threading

_db_local = _threading.local()


class _PooledConn:
    """Wraps a thread-local SQLite connection; close() is a no-op so the connection is reused."""
    def __init__(self, raw: sqlite3.Connection):
        self._c = raw

    def execute(self, sql, params=None):
        if params is not None:
            return self._c.execute(sql, params)
        return self._c.execute(sql)

    def executemany(self, sql, params_list):
        return self._c.executemany(sql, params_list)

    def execute_batch(self, sql_params: list[tuple]):
        for sql, params in sql_params:
            self._c.execute(sql, params)
        self._c.commit()

    def fetch_batch(self, sql_params: list[tuple]) -> list:
        return [self._c.execute(sql, params) for sql, params in sql_params]

    def executescript(self, sql):
        return self._c.executescript(sql)

    def commit(self):
        return self._c.commit()

    def close(self):
        pass  # reuse across calls on the same thread


def get_db() -> "_PooledConn":
    conn = getattr(_db_local, "conn", None)
    if conn is None:
        raw = sqlite3.connect(LOCAL_DB_PATH, check_same_thread=False)
        raw.row_factory = sqlite3.Row
        raw.execute("PRAGMA journal_mode=WAL")
        raw.execute("PRAGMA synchronous=NORMAL")
        raw.execute("PRAGMA busy_timeout=30000")
        raw.execute("PRAGMA foreign_keys=ON")
        raw.execute("PRAGMA wal_autocheckpoint=200")
        raw.commit()
        conn = _PooledConn(raw)
        _db_local.conn = conn
    return conn


def release_db():
    """Close and remove the thread-local DB connection. Call after long-running background work."""
    conn = getattr(_db_local, "conn", None)
    if conn is not None:
        try:
            conn._c.close()
        except Exception:
            pass
        _db_local.conn = None


def checkpoint_db():
    """Force WAL checkpoint using a fresh connection after a task completes."""
    try:
        import sqlite3 as _sq
        c = _sq.connect(LOCAL_DB_PATH, timeout=15)
        c.execute("PRAGMA wal_checkpoint(PASSIVE)")
        c.close()
    except Exception:
        pass


def get_turso() -> _TursoConnection:
    global _turso_instance
    if _turso_instance is None:
        if not TURSO_URL or not TURSO_TOKEN:
            raise RuntimeError(
                "Turso not configured. Set TURSO_URL and TURSO_TOKEN environment variables."
            )
        _turso_instance = _TursoConnection(TURSO_URL, TURSO_TOKEN)
    return _turso_instance


_EVOLUTION_SCHEMA = """
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
CREATE TABLE IF NOT EXISTS evolution_tasks (
    task_id         TEXT PRIMARY KEY,
    status          TEXT NOT NULL DEFAULT 'QUEUED',
    created_at      INTEGER NOT NULL,
    started_at      INTEGER,
    completed_at    INTEGER,
    config_json     TEXT NOT NULL DEFAULT '{}',
    current_generation INTEGER DEFAULT 0,
    total_generations  INTEGER DEFAULT 0,
    progress_pct    REAL DEFAULT 0.0,
    error_message   TEXT,
    result_summary_json TEXT
);
CREATE TABLE IF NOT EXISTS task_generations (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id         TEXT NOT NULL,
    generation      INTEGER NOT NULL,
    result_json     TEXT NOT NULL,
    created_at      INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS individuals (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id         TEXT NOT NULL,
    generation      INTEGER NOT NULL,
    strategy_id     TEXT NOT NULL,
    params_json     TEXT NOT NULL DEFAULT '{}',
    pareto_rank     INTEGER,
    crowding_distance REAL,
    is_elite        INTEGER DEFAULT 0,
    cagr            REAL DEFAULT 0,
    max_drawdown    REAL DEFAULT 0,
    sharpe_ratio    REAL DEFAULT 0,
    profit_factor   REAL DEFAULT 0,
    win_rate        REAL DEFAULT 0,
    r2              REAL DEFAULT 0,
    trade_count     INTEGER DEFAULT 0,
    oos_consistency_score REAL DEFAULT 0,
    passed_absolute INTEGER DEFAULT 0,
    passed_dynamic  INTEGER DEFAULT 0,
    elimination_reason TEXT,
    equity_curve_json TEXT,
    symbol_results_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_individuals_task_gen ON individuals(task_id, generation);
CREATE INDEX IF NOT EXISTS idx_individuals_rank ON individuals(task_id, pareto_rank);
CREATE TABLE IF NOT EXISTS pareto_fronts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id         TEXT NOT NULL,
    generation      INTEGER NOT NULL,
    front_json      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_fronts_task_gen ON pareto_fronts(task_id, generation);
CREATE TABLE IF NOT EXISTS ohlcv_data (
    symbol      TEXT NOT NULL,
    timeframe   TEXT NOT NULL,
    timestamp   INTEGER NOT NULL,
    open        REAL NOT NULL DEFAULT 0,
    high        REAL NOT NULL DEFAULT 0,
    low         REAL NOT NULL DEFAULT 0,
    close       REAL NOT NULL DEFAULT 0,
    volume      REAL NOT NULL DEFAULT 0,
    created_at  INTEGER NOT NULL DEFAULT (strftime('%s','now')),
    PRIMARY KEY (symbol, timeframe, timestamp)
);
CREATE TABLE IF NOT EXISTS gene_favorites (
    strategy_id TEXT PRIMARY KEY,
    task_id     TEXT NOT NULL DEFAULT '',
    custom_name TEXT DEFAULT '',
    is_favorite INTEGER DEFAULT 0,
    notes       TEXT DEFAULT '',
    updated_at  INTEGER NOT NULL DEFAULT 0
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
CREATE TABLE IF NOT EXISTS paper_equity_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    instance_id TEXT NOT NULL,
    timestamp   INTEGER NOT NULL,
    equity      REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_equity_hist ON paper_equity_history(instance_id, timestamp);
CREATE TABLE IF NOT EXISTS speed_records (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    template_id     TEXT NOT NULL,
    task_id         TEXT NOT NULL,
    total_bars      REAL NOT NULL,
    total_seconds   REAL NOT NULL,
    bars_per_second REAL NOT NULL,
    recorded_at     INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_speed_template ON speed_records(template_id, recorded_at);
"""

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
CREATE TABLE IF NOT EXISTS paper_equity_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    instance_id TEXT NOT NULL,
    timestamp   INTEGER NOT NULL,
    equity      REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_equity_hist ON paper_equity_history(instance_id, timestamp);
CREATE TABLE IF NOT EXISTS gene_favorites (
    strategy_id     TEXT PRIMARY KEY,
    task_id         TEXT NOT NULL,
    custom_name     TEXT DEFAULT '',
    is_favorite     INTEGER DEFAULT 0,
    notes           TEXT DEFAULT '',
    updated_at      INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS evolution_task_results (
    task_id         TEXT PRIMARY KEY,
    result_summary_json TEXT NOT NULL DEFAULT '{}',
    champions_json  TEXT NOT NULL DEFAULT '[]',
    created_at      INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS speed_records (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    template_id     TEXT NOT NULL,
    task_id         TEXT NOT NULL,
    total_bars      REAL NOT NULL,
    total_seconds   REAL NOT NULL,
    bars_per_second REAL NOT NULL,
    recorded_at     INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_speed_template ON speed_records(template_id, recorded_at);
"""


def init_db():
    conn = get_db()
    conn.executescript(_EVOLUTION_SCHEMA)
    conn.commit()

    from migrations import run_migrations
    turso = None
    if TURSO_URL and TURSO_TOKEN:
        try:
            turso = get_turso()
            turso.executescript(_TURSO_SCHEMA)
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning("Turso init failed (remote DB will be unavailable): %s", e)

    run_migrations(conn, turso)
    conn.close()


def sync_strategies_to_local():
    if not TURSO_URL or not TURSO_TOKEN:
        return
    try:
        t = get_turso()
    except RuntimeError:
        return
    rows = t.execute(
        "SELECT * FROM strategy_configs ORDER BY created_at ASC"
    ).fetchall()
    if not rows:
        return
    local = get_db()
    local.executemany(
        """INSERT OR REPLACE INTO strategy_configs
           (config_id, name, description, template_id, is_template,
            is_locked, locked_by_task_id, parameters_json, constraints_json,
            created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [tuple(r[c] for c in (
            "config_id", "name", "description", "template_id", "is_template",
            "is_locked", "locked_by_task_id", "parameters_json", "constraints_json",
            "created_at", "updated_at"
        )) for r in rows],
    )
    local.commit()
    local.close()


def sync_task_to_turso(task_id: str):
    if not TURSO_URL or not TURSO_TOKEN:
        return
    try:
        t = get_turso()
    except RuntimeError:
        return
    local = get_db()
    row = local.execute(
        "SELECT * FROM evolution_tasks WHERE task_id = ?", (task_id,)
    ).fetchone()
    if not row:
        local.close()
        return
    if not row["result_summary_json"]:
        local.close()
        return

    champions = local.execute(
        "SELECT * FROM individuals WHERE task_id = ? AND pareto_rank = 1 ORDER BY cagr DESC",
        (task_id,),
    ).fetchall()

    t.execute(
        """INSERT OR REPLACE INTO evolution_task_results
           (task_id, result_summary_json, champions_json, created_at)
           VALUES (?, ?, ?, ?)""",
        (
            task_id,
            row["result_summary_json"],
            json.dumps([dict(c) for c in champions]),
            int(__import__("time").time()),
        ),
    )
    local.close()


def save_speed_record(template_id: str, task_id: str, total_bars: float, total_seconds: float):
    if total_seconds <= 0:
        return
    bars_per_second = total_bars / total_seconds
    now = int(__import__("time").time())
    conn = get_db()
    conn.execute(
        """INSERT INTO speed_records (template_id, task_id, total_bars, total_seconds, bars_per_second, recorded_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (template_id, task_id, total_bars, total_seconds, bars_per_second, now),
    )
    conn.commit()
    conn.close()
    try:
        turso = get_turso()
        turso.execute(
            """INSERT INTO speed_records (template_id, task_id, total_bars, total_seconds, bars_per_second, recorded_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (template_id, task_id, total_bars, total_seconds, bars_per_second, now),
        )
    except Exception:
        pass


def get_avg_speed(template_id: str, default_bps: float = 95000.0) -> float:
    try:
        turso = get_turso()
        row = turso.execute(
            "SELECT AVG(bars_per_second) as avg_bps FROM speed_records WHERE template_id = ?",
            (template_id,),
        ).fetchone()
        if row and row["avg_bps"] is not None and row["avg_bps"] > 0:
            return float(row["avg_bps"])
    except Exception:
        pass
    conn = get_db()
    row = conn.execute(
        "SELECT AVG(bars_per_second) as avg_bps FROM speed_records WHERE template_id = ?",
        (template_id,),
    ).fetchone()
    conn.close()
    if row and row["avg_bps"] is not None and row["avg_bps"] > 0:
        return float(row["avg_bps"])
    return default_bps
