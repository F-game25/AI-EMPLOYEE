import logging
import time
from ..db import cognitive_conn

logger = logging.getLogger(__name__)


def _ensure_table() -> None:
    with cognitive_conn() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS memory_provenance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                memory_id TEXT NOT NULL,
                decision_id TEXT NOT NULL,
                tenant_id TEXT NOT NULL,
                retrieved_at REAL NOT NULL
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_mp_decision ON memory_provenance(decision_id)")


_ensure_table()


def record_retrieval(memory_id: str, decision_id: str, tenant_id: str) -> None:
    with cognitive_conn() as c:
        c.execute(
            "INSERT INTO memory_provenance(memory_id, decision_id, tenant_id, retrieved_at) VALUES (?,?,?,?)",
            (memory_id, decision_id, tenant_id, time.time())
        )


def get_provenance(decision_id: str) -> list[dict]:
    with cognitive_conn() as c:
        rows = c.execute(
            "SELECT memory_id, retrieved_at FROM memory_provenance WHERE decision_id=? ORDER BY retrieved_at",
            (decision_id,)
        ).fetchall()
    return [dict(r) for r in rows]
