import asyncio
import json
import time
import logging
from typing import Optional
from ..db import cognitive_conn
from .schema import Initiative

logger = logging.getLogger(__name__)


def _ensure_tables() -> None:
    with cognitive_conn() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS initiatives (
                id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                title TEXT NOT NULL,
                description TEXT DEFAULT '',
                status TEXT DEFAULT 'pending',
                priority INTEGER DEFAULT 5,
                estimated_cost_tokens INTEGER DEFAULT 0,
                actual_cost_tokens INTEGER DEFAULT 0,
                deadline REAL,
                dependencies TEXT DEFAULT '[]',
                assigned_agents TEXT DEFAULT '[]',
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_init_tenant ON initiatives(tenant_id, status)")


_ensure_tables()


def create(init: Initiative) -> str:
    _ensure_tables()
    with cognitive_conn() as c:
        c.execute(
            "INSERT OR REPLACE INTO initiatives VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (init.id, init.tenant_id, init.title, init.description, init.status,
             init.priority, init.estimated_cost_tokens, init.actual_cost_tokens,
             init.deadline, json.dumps(init.dependencies), json.dumps(init.assigned_agents),
             init.created_at, init.updated_at)
        )
    return init.id


def update(init_id: str, **kwargs) -> None:
    _ensure_tables()
    # Strict allowlist prevents SQL injection via column-name interpolation.
    allowed = {"status", "priority", "deadline", "actual_cost_tokens", "description"}
    sets = {k: v for k, v in kwargs.items() if k in allowed}
    if not sets:
        return
    sets["updated_at"] = time.time()
    # All keys are either from the allowlist above or the literal "updated_at" — safe to interpolate.
    cols = ", ".join(f"{k}=?" for k in sets)
    with cognitive_conn() as c:
        c.execute(f"UPDATE initiatives SET {cols} WHERE id=?", (*sets.values(), init_id))


def list_initiatives(tenant_id: str, status: Optional[str] = None) -> list[dict]:
    _ensure_tables()
    with cognitive_conn() as c:
        if status:
            rows = c.execute(
                "SELECT * FROM initiatives WHERE tenant_id=? AND status=? ORDER BY priority",
                (tenant_id, status)
            ).fetchall()
        else:
            rows = c.execute(
                "SELECT * FROM initiatives WHERE tenant_id=? ORDER BY priority",
                (tenant_id,)
            ).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        d["dependencies"] = json.loads(d["dependencies"])
        d["assigned_agents"] = json.loads(d["assigned_agents"])
        result.append(d)
    return result


class InitiativeManager:
    def __init__(self):
        self._running = False

    async def start_lifecycle_loop(self) -> None:
        self._running = True
        while self._running:
            try:
                self._advance_all()
            except Exception as e:
                logger.warning("Initiative lifecycle error: %s", e)
            await asyncio.sleep(60)

    def _advance_all(self) -> None:
        _ensure_tables()
        with cognitive_conn() as c:
            rows = c.execute("SELECT id, tenant_id, status, dependencies, deadline FROM initiatives").fetchall()
        for row in rows:
            if row["status"] == "pending":
                deps = json.loads(row["dependencies"])
                if not deps:
                    update(row["id"], status="active")
            elif row["status"] == "active":
                if row["deadline"] and row["deadline"] < time.time():
                    update(row["id"], status="blocked")

    def stop(self) -> None:
        self._running = False


_instance: Optional[InitiativeManager] = None


def get_initiative_manager() -> InitiativeManager:
    global _instance
    if _instance is None:
        _instance = InitiativeManager()
    return _instance
