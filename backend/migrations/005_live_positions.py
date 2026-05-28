VERSION = 5
DESCRIPTION = "Add live_positions table for Alpaca position tracking"


def run_local(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS live_positions (
        symbol          TEXT NOT NULL,
        side            TEXT DEFAULT 'flat',
        qty             REAL DEFAULT 0,
        entry_price     REAL DEFAULT 0,
        current_price   REAL DEFAULT 0,
        unrealized_pnl  REAL DEFAULT 0,
        PRIMARY KEY (symbol)
    )""")


def run_turso(turso):
    turso.execute("""CREATE TABLE IF NOT EXISTS live_positions (
        symbol          TEXT NOT NULL,
        side            TEXT DEFAULT 'flat',
        qty             REAL DEFAULT 0,
        entry_price     REAL DEFAULT 0,
        current_price   REAL DEFAULT 0,
        unrealized_pnl  REAL DEFAULT 0,
        PRIMARY KEY (symbol)
    )""")
