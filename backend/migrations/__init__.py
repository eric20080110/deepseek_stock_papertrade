import os
import time
import importlib.util
from typing import Optional


def _discover_migrations():
    migrations = []
    pkg_dir = os.path.dirname(__file__)
    for f in sorted(os.listdir(pkg_dir)):
        if not f.endswith(".py") or f == "__init__.py":
            continue
        try:
            version = int(f.split("_")[0])
        except ValueError:
            continue
        spec = importlib.util.spec_from_file_location(f"migrations.{f[:-3]}", os.path.join(pkg_dir, f))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        migrations.append({
            "version": version,
            "description": getattr(mod, "DESCRIPTION", ""),
            "run_local": getattr(mod, "run_local", None),
            "run_turso": getattr(mod, "run_turso", None),
        })
    return sorted(migrations, key=lambda m: m["version"])


def run_migrations(conn, turso=None):
    conn.execute(
        """CREATE TABLE IF NOT EXISTS _migrations (
            version     INTEGER PRIMARY KEY,
            description TEXT NOT NULL DEFAULT '',
            applied_at  INTEGER NOT NULL
        )"""
    )
    conn.commit()
    row = conn.execute("SELECT MAX(version) FROM _migrations").fetchone()
    latest = row[0] if row and row[0] else 0

    for m in _discover_migrations():
        if m["version"] <= latest:
            continue
        if m["run_local"]:
            m["run_local"](conn)
        if turso and m["run_turso"]:
            m["run_turso"](turso)
        conn.execute(
            "INSERT INTO _migrations (version, description, applied_at) VALUES (?, ?, ?)",
            (m["version"], m["description"], int(time.time())),
        )
        conn.commit()
