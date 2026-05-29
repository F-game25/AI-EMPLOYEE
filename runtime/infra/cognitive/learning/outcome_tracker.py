import logging
from .schema import OutcomeRecord
from ..db import cognitive_conn

logger = logging.getLogger(__name__)


def _ensure_table() -> None:
    with cognitive_conn() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS outcome_records (
                id TEXT PRIMARY KEY,
                workflow_id TEXT NOT NULL,
                agent_id TEXT NOT NULL,
                tenant_id TEXT NOT NULL,
                success INTEGER NOT NULL,
                quality_score REAL NOT NULL,
                duration_ms REAL NOT NULL,
                cost_tokens INTEGER DEFAULT 0,
                user_feedback INTEGER,
                recorded_at REAL NOT NULL
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_or_agent ON outcome_records(agent_id, tenant_id, recorded_at)")


_ensure_table()


def record(o: OutcomeRecord) -> str:
    with cognitive_conn() as c:
        c.execute(
            "INSERT OR REPLACE INTO outcome_records VALUES (?,?,?,?,?,?,?,?,?,?)",
            (o.id, o.workflow_id, o.agent_id, o.tenant_id,
             1 if o.success else 0, o.quality_score, o.duration_ms,
             o.cost_tokens, o.user_feedback, o.recorded_at)
        )
    return o.id


def get_recent(tenant_id: str, agent_id: str = None, limit: int = 50) -> list[dict]:
    with cognitive_conn() as c:
        if agent_id:
            rows = c.execute(
                "SELECT * FROM outcome_records WHERE tenant_id=? AND agent_id=? ORDER BY recorded_at DESC LIMIT ?",
                (tenant_id, agent_id, limit)
            ).fetchall()
        else:
            rows = c.execute(
                "SELECT * FROM outcome_records WHERE tenant_id=? ORDER BY recorded_at DESC LIMIT ?",
                (tenant_id, limit)
            ).fetchall()
    return [dict(r) for r in rows]


_instance = None


def get_outcome_tracker():
    global _instance
    if _instance is None:
        _instance = type("OutcomeTracker", (), {
            "record": staticmethod(record),
            "get_recent": staticmethod(get_recent),
        })()
    return _instance
