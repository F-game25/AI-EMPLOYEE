import json
import logging
from ..db import cognitive_conn

logger = logging.getLogger(__name__)


def _ensure_table() -> None:
    with cognitive_conn() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS workflow_deps (
                source_workflow TEXT NOT NULL,
                target_workflow TEXT NOT NULL,
                tenant_id TEXT NOT NULL,
                frequency INTEGER DEFAULT 1,
                avg_gap_s REAL DEFAULT 0.0,
                last_seen REAL,
                PRIMARY KEY (source_workflow, target_workflow, tenant_id)
            )
        """)


_ensure_table()


def record_sequence(source: str, target: str, tenant_id: str, gap_s: float = 0.0) -> None:
    import time
    with cognitive_conn() as c:
        c.execute(
            "INSERT INTO workflow_deps VALUES (?,?,?,1,?,?) "
            "ON CONFLICT(source_workflow,target_workflow,tenant_id) DO UPDATE SET "
            "frequency=frequency+1, avg_gap_s=(avg_gap_s+?)/2, last_seen=?",
            (source, target, tenant_id, gap_s, time.time(), gap_s, time.time())
        )


def get_graph(tenant_id: str) -> dict:
    with cognitive_conn() as c:
        rows = c.execute(
            "SELECT * FROM workflow_deps WHERE tenant_id=? AND frequency>=2 ORDER BY frequency DESC",
            (tenant_id,)
        ).fetchall()
    edges = [dict(r) for r in rows]
    nodes = list({e["source_workflow"] for e in edges} | {e["target_workflow"] for e in edges})
    return {"nodes": nodes, "edges": edges}
