import json
import time
import logging
from ..db import cognitive_conn

logger = logging.getLogger(__name__)
_MAX_INTERACTIONS = 500


def _ensure_table() -> None:
    with cognitive_conn() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS conversation_memory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                tenant_id TEXT NOT NULL,
                summary TEXT NOT NULL,
                topic TEXT,
                recorded_at REAL NOT NULL
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_cm_user ON conversation_memory(user_id, tenant_id, recorded_at)")


_ensure_table()


def record(user_id: str, tenant_id: str, summary: str, topic: str = None) -> None:
    now = time.time()
    with cognitive_conn() as c:
        c.execute(
            "INSERT INTO conversation_memory(user_id, tenant_id, summary, topic, recorded_at) VALUES (?,?,?,?,?)",
            (user_id, tenant_id, summary, topic, now)
        )
        # Keep only last 500 per user
        c.execute(
            "DELETE FROM conversation_memory WHERE user_id=? AND tenant_id=? AND id NOT IN "
            "(SELECT id FROM conversation_memory WHERE user_id=? AND tenant_id=? ORDER BY recorded_at DESC LIMIT ?)",
            (user_id, tenant_id, user_id, tenant_id, _MAX_INTERACTIONS)
        )


def get_context(user_id: str, tenant_id: str) -> dict:
    with cognitive_conn() as c:
        rows = c.execute(
            "SELECT * FROM conversation_memory WHERE user_id=? AND tenant_id=? ORDER BY recorded_at DESC LIMIT 5",
            (user_id, tenant_id)
        ).fetchall()
        total = c.execute(
            "SELECT COUNT(*) as n FROM conversation_memory WHERE user_id=? AND tenant_id=?",
            (user_id, tenant_id)
        ).fetchone()["n"]
    return {
        "user_id": user_id,
        "interaction_count": total,
        "recent": [dict(r) for r in rows],
    }
