VERSION = 6
DESCRIPTION = "Add live_equity_history table for equity curve tracking"


def run_local(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS live_equity_history (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        instance_id TEXT NOT NULL,
        timestamp   INTEGER NOT NULL,
        equity      REAL NOT NULL
    )""")
    try:
        conn.execute("CREATE INDEX IF NOT EXISTS idx_live_eq_inst ON live_equity_history(instance_id, timestamp)")
    except Exception:
        pass


def run_turso(turso):
    turso.execute("""CREATE TABLE IF NOT EXISTS live_equity_history (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        instance_id TEXT NOT NULL,
        timestamp   INTEGER NOT NULL,
        equity      REAL NOT NULL
    )""")
    try:
        turso.execute("CREATE INDEX IF NOT EXISTS idx_live_eq_inst ON live_equity_history(instance_id, timestamp)")
    except Exception:
        pass
