VERSION = 4
DESCRIPTION = "Add last_executed_date column to live_instances for daily scheduler tracking"


def run_local(conn):
    try:
        conn.execute("ALTER TABLE live_instances ADD COLUMN last_executed_date TEXT")
    except Exception:
        pass


def run_turso(turso):
    try:
        turso.execute("ALTER TABLE live_instances ADD COLUMN last_executed_date TEXT")
    except Exception:
        pass
