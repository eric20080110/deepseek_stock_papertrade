VERSION = 3
DESCRIPTION = "Add speed_records table for historical estimation calibration"


def run_local(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS speed_records (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        template_id     TEXT NOT NULL,
        task_id         TEXT NOT NULL,
        total_bars      REAL NOT NULL,
        total_seconds   REAL NOT NULL,
        bars_per_second REAL NOT NULL,
        recorded_at     INTEGER NOT NULL
    )""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_speed_template ON speed_records(template_id, recorded_at)")


def run_turso(turso):
    turso.execute("""CREATE TABLE IF NOT EXISTS speed_records (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        template_id     TEXT NOT NULL,
        task_id         TEXT NOT NULL,
        total_bars      REAL NOT NULL,
        total_seconds   REAL NOT NULL,
        bars_per_second REAL NOT NULL,
        recorded_at     INTEGER NOT NULL
    )""")
    turso.execute("CREATE INDEX IF NOT EXISTS idx_speed_template ON speed_records(template_id, recorded_at)")
