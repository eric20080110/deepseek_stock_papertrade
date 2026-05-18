VERSION = 2
DESCRIPTION = "Add name column to evolution_tasks"


def run_local(conn):
    try:
        conn.execute("ALTER TABLE evolution_tasks ADD COLUMN name TEXT")
    except Exception:
        pass


def run_turso(turso):
    try:
        turso.execute("ALTER TABLE evolution_tasks ADD COLUMN name TEXT")
    except Exception:
        pass
