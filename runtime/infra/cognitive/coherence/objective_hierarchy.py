import time
from typing import Optional
from ..db import cognitive_conn
from .schema import ObjectiveNode


def _ensure_table() -> None:
    with cognitive_conn() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS objectives (
                id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                title TEXT NOT NULL,
                description TEXT DEFAULT '',
                priority INTEGER DEFAULT 5,
                parent_id TEXT,
                status TEXT DEFAULT 'active',
                source_agent TEXT,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_obj_tenant ON objectives(tenant_id, status)")


_ensure_table()


def add_objective(obj: ObjectiveNode) -> str:
    with cognitive_conn() as c:
        c.execute(
            "INSERT OR REPLACE INTO objectives VALUES (?,?,?,?,?,?,?,?,?,?)",
            (obj.id, obj.tenant_id, obj.title, obj.description, obj.priority,
             obj.parent_id, obj.status, obj.source_agent, obj.created_at, obj.updated_at)
        )
    return obj.id


def get_priority_stack(tenant_id: str) -> list[dict]:
    with cognitive_conn() as c:
        rows = c.execute(
            "SELECT * FROM objectives WHERE tenant_id=? AND status='active' ORDER BY priority ASC",
            (tenant_id,)
        ).fetchall()
    return [dict(r) for r in rows]


def update_status(obj_id: str, status: str) -> None:
    with cognitive_conn() as c:
        c.execute(
            "UPDATE objectives SET status=?, updated_at=? WHERE id=?",
            (status, time.time(), obj_id)
        )


def list_objectives(tenant_id: str, status: Optional[str] = None) -> list[dict]:
    with cognitive_conn() as c:
        if status:
            rows = c.execute(
                "SELECT * FROM objectives WHERE tenant_id=? AND status=? ORDER BY priority",
                (tenant_id, status)
            ).fetchall()
        else:
            rows = c.execute(
                "SELECT * FROM objectives WHERE tenant_id=? ORDER BY priority",
                (tenant_id,)
            ).fetchall()
    return [dict(r) for r in rows]
