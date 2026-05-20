import logging
from .schema import OperationalCycle
from ..db import cognitive_conn

logger = logging.getLogger(__name__)


def _ensure_table() -> None:
    with cognitive_conn() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS op_cycles (
                workflow_type TEXT NOT NULL,
                tenant_id TEXT NOT NULL,
                period_days INTEGER NOT NULL,
                confidence REAL NOT NULL,
                last_peak REAL NOT NULL,
                detected_at REAL NOT NULL,
                PRIMARY KEY (workflow_type, tenant_id)
            )
        """)


_ensure_table()


def store_cycle(c: OperationalCycle) -> None:
    with cognitive_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO op_cycles VALUES (?,?,?,?,?,?)",
            (c.workflow_type, c.tenant_id, c.period_days, c.confidence, c.last_peak, c.detected_at)
        )


def get_cycles(tenant_id: str) -> list[dict]:
    with cognitive_conn() as c:
        rows = c.execute(
            "SELECT * FROM op_cycles WHERE tenant_id=? AND confidence>0.7 ORDER BY confidence DESC",
            (tenant_id,)
        ).fetchall()
    return [dict(r) for r in rows]
