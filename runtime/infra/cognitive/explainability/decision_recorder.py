import json
import logging
from typing import Optional
from .schema import DecisionRecord
from ..db import cognitive_conn

logger = logging.getLogger(__name__)


def _ensure_table() -> None:
    with cognitive_conn() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS decision_records (
                id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                agent_id TEXT NOT NULL,
                workflow_id TEXT,
                decision_type TEXT NOT NULL,
                input_summary TEXT NOT NULL,
                output_summary TEXT NOT NULL,
                memories_used TEXT DEFAULT '[]',
                alternatives_considered TEXT DEFAULT '[]',
                confidence REAL DEFAULT 0.8,
                reasoning_trace_id TEXT,
                decided_at REAL NOT NULL
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_dr_tenant ON decision_records(tenant_id, decided_at)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_dr_agent ON decision_records(agent_id)")


_ensure_table()


def record(d: DecisionRecord) -> str:
    with cognitive_conn() as c:
        c.execute(
            "INSERT OR REPLACE INTO decision_records VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (d.id, d.tenant_id, d.agent_id, d.workflow_id, d.decision_type,
             d.input_summary, d.output_summary,
             json.dumps(d.memories_used), json.dumps(d.alternatives_considered),
             d.confidence, d.reasoning_trace_id, d.decided_at)
        )
    return d.id


def get(decision_id: str) -> Optional[dict]:
    with cognitive_conn() as c:
        row = c.execute("SELECT * FROM decision_records WHERE id=?", (decision_id,)).fetchone()
    if not row:
        return None
    d = dict(row)
    d["memories_used"] = json.loads(d["memories_used"])
    d["alternatives_considered"] = json.loads(d["alternatives_considered"])
    return d


def list_recent(tenant_id: str, limit: int = 50) -> list[dict]:
    with cognitive_conn() as c:
        rows = c.execute(
            "SELECT * FROM decision_records WHERE tenant_id=? ORDER BY decided_at DESC LIMIT ?",
            (tenant_id, limit)
        ).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        d["memories_used"] = json.loads(d["memories_used"])
        d["alternatives_considered"] = json.loads(d["alternatives_considered"])
        result.append(d)
    return result


def list_by_agent(agent_id: str, limit: int = 50) -> list[dict]:
    with cognitive_conn() as c:
        rows = c.execute(
            "SELECT * FROM decision_records WHERE agent_id=? ORDER BY decided_at DESC LIMIT ?",
            (agent_id, limit)
        ).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        d["memories_used"] = json.loads(d["memories_used"])
        d["alternatives_considered"] = json.loads(d["alternatives_considered"])
        result.append(d)
    return result


def get_by_workflow(workflow_id: str) -> list[dict]:
    with cognitive_conn() as c:
        rows = c.execute(
            "SELECT * FROM decision_records WHERE workflow_id=? ORDER BY decided_at DESC",
            (workflow_id,)
        ).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        d["memories_used"] = json.loads(d["memories_used"])
        d["alternatives_considered"] = json.loads(d["alternatives_considered"])
        result.append(d)
    return result


_instance = None


def get_decision_recorder():
    global _instance
    if _instance is None:
        _instance = type("DecisionRecorder", (), {
            "record": staticmethod(record),
            "get": staticmethod(get),
            "list_recent": staticmethod(list_recent),
            "list_by_agent": staticmethod(list_by_agent),
            "get_by_workflow": staticmethod(get_by_workflow),
        })()
    return _instance
