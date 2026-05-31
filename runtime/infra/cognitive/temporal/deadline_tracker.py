import asyncio
import time
import logging
from typing import Optional
from .schema import Deadline
from ..db import cognitive_conn

logger = logging.getLogger(__name__)


def _ensure_table() -> None:
    with cognitive_conn() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS deadlines (
                id TEXT PRIMARY KEY,
                initiative_id TEXT NOT NULL,
                tenant_id TEXT NOT NULL,
                deadline_ts REAL NOT NULL,
                priority INTEGER DEFAULT 5,
                status TEXT DEFAULT 'pending',
                created_at REAL NOT NULL
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_dl_tenant ON deadlines(tenant_id, status)")


_ensure_table()


def create(d: Deadline) -> str:
    with cognitive_conn() as c:
        c.execute(
            "INSERT OR REPLACE INTO deadlines VALUES (?,?,?,?,?,?,?)",
            (d.id, d.initiative_id, d.tenant_id, d.deadline_ts, d.priority, d.status, d.created_at)
        )
    return d.id


def list_upcoming(tenant_id: str, hours_ahead: int = 24) -> list[dict]:
    cutoff = time.time() + hours_ahead * 3600
    with cognitive_conn() as c:
        rows = c.execute(
            "SELECT * FROM deadlines WHERE tenant_id=? AND deadline_ts<=? AND status NOT IN ('completed','archived') ORDER BY deadline_ts ASC",
            (tenant_id, cutoff)
        ).fetchall()
    return [dict(r) for r in rows]


class DeadlineTracker:
    def __init__(self):
        self._running = False

    async def start(self) -> None:
        self._running = True
        while self._running:
            await asyncio.sleep(60)
            self._check_deadlines()

    def _check_deadlines(self) -> None:
        with cognitive_conn() as c:
            tenants = c.execute("SELECT DISTINCT tenant_id FROM deadlines").fetchall()
        now = time.time()
        for row in tenants:
            tid = row["tenant_id"]
            upcoming = list_upcoming(tid, 24)
            for d in upcoming:
                if d["deadline_ts"] < now:
                    self._emit("temporal:deadline_missed", tid, d["initiative_id"])
                elif d["deadline_ts"] < now + 86400:
                    self._emit("temporal:deadline_critical", tid, d["initiative_id"])

    def _emit(self, event: str, tenant_id: str, initiative_id: str) -> None:
        try:
            from core.bus import get_message_bus
            get_message_bus().publish_sync("notifications", {
                "event": event, "tenant_id": tenant_id, "initiative_id": initiative_id
            })
        except Exception:
            pass

    def stop(self) -> None:
        self._running = False


_instance: Optional[DeadlineTracker] = None


def get_deadline_tracker() -> DeadlineTracker:
    global _instance
    if _instance is None:
        _instance = DeadlineTracker()
    return _instance
