import os
import sys

_backend = os.path.join(os.path.dirname(__file__), 'backend')
if _backend not in sys.path:
    sys.path.insert(0, _backend)

# Re-export public symbols from backend/database.py
from database import (  # noqa: F401, F403
    LOCAL_DB_PATH,
    TURSO_URL,
    TURSO_TOKEN,
    get_db,
    get_live_db,
    get_turso,
    init_db,
    release_db,
    checkpoint_db,
    sync_task_to_turso,
    sync_strategies_to_local,
    save_speed_record,
    get_avg_speed,
)
