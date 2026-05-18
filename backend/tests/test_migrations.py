import os
import tempfile
import sqlite3

from migrations import run_migrations, _discover_migrations


class TestMigrationDiscovery:
    def test_discovers_migrations_in_order(self):
        migrations = _discover_migrations()
        assert len(migrations) >= 2
        assert migrations[0]["version"] == 1
        assert migrations[1]["version"] == 2
        for i in range(len(migrations) - 1):
            assert migrations[i]["version"] < migrations[i + 1]["version"]

    def test_each_migration_has_run_local(self):
        for m in _discover_migrations():
            assert m["run_local"] is not None


class TestMigrationRunner:
    def setup_method(self):
        self.tmp = tempfile.mktemp(suffix=".db")

    def teardown_method(self):
        if os.path.exists(self.tmp):
            os.remove(self.tmp)

    def test_runs_all_migrations_on_fresh_db(self):
        conn = sqlite3.connect(self.tmp)
        run_migrations(conn)
        migs = conn.execute("SELECT version, description FROM _migrations ORDER BY version").fetchall()
        assert len(migs) >= 2
        conn.close()

    def test_idempotent_second_run(self):
        conn = sqlite3.connect(self.tmp)
        run_migrations(conn)
        run_migrations(conn)
        migs = conn.execute("SELECT version FROM _migrations").fetchall()
        assert len(migs) >= 2
        conn.close()

    def test_evolution_tasks_has_name_column_after_migration(self):
        conn = sqlite3.connect(self.tmp)
        conn.execute("CREATE TABLE IF NOT EXISTS evolution_tasks (task_id TEXT PRIMARY KEY)")
        conn.commit()
        run_migrations(conn)
        cols = [c[1] for c in conn.execute("PRAGMA table_info(evolution_tasks)").fetchall()]
        assert "name" in cols
        conn.close()
