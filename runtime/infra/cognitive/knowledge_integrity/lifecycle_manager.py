import asyncio
import time
import logging
from typing import Optional
from .schema import MemoryLifecycleState
from ..db import cognitive_conn

logger = logging.getLogger(__name__)

_AGING_DAYS = 7
_STALE_DAYS = 30
_ARCHIVE_DAYS = 90


def _ensure_table() -> None:
    with cognitive_conn() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS memory_lifecycle (
                memory_id TEXT NOT NULL,
                tenant_id TEXT NOT NULL,
                lifecycle_state TEXT DEFAULT 'fresh',
                confidence REAL DEFAULT 1.0,
                access_count INTEGER DEFAULT 0,
                source_agent TEXT,
                created_at REAL NOT NULL,
                last_accessed REAL NOT NULL,
                PRIMARY KEY (memory_id, tenant_id)
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_ml_tenant ON memory_lifecycle(tenant_id, lifecycle_state)")


_ensure_table()


def register(memory_id: str, tenant_id: str, source_agent: str = "unknown", confidence: float = 1.0) -> None:
    now = time.time()
    with cognitive_conn() as c:
        c.execute(
            "INSERT OR IGNORE INTO memory_lifecycle VALUES (?,?,?,?,?,?,?,?)",
            (memory_id, tenant_id, MemoryLifecycleState.FRESH, confidence, 0, source_agent, now, now)
        )


def record_access(memory_id: str, tenant_id: str) -> None:
    now = time.time()
    with cognitive_conn() as c:
        c.execute(
            "UPDATE memory_lifecycle SET access_count=access_count+1, last_accessed=? WHERE memory_id=? AND tenant_id=?",
            (now, memory_id, tenant_id)
        )


def quarantine(memory_id: str, tenant_id: str) -> None:
    with cognitive_conn() as c:
        c.execute(
            "UPDATE memory_lifecycle SET lifecycle_state=? WHERE memory_id=? AND tenant_id=?",
            (MemoryLifecycleState.QUARANTINED, memory_id, tenant_id)
        )


def restore(memory_id: str, tenant_id: str) -> None:
    with cognitive_conn() as c:
        c.execute(
            "UPDATE memory_lifecycle SET lifecycle_state=? WHERE memory_id=? AND tenant_id=?",
            (MemoryLifecycleState.STABLE, memory_id, tenant_id)
        )


def get_counts(tenant_id: str) -> dict:
    with cognitive_conn() as c:
        rows = c.execute(
            "SELECT lifecycle_state, COUNT(*) as cnt FROM memory_lifecycle WHERE tenant_id=? GROUP BY lifecycle_state",
            (tenant_id,)
        ).fetchall()
    return {r["lifecycle_state"]: r["cnt"] for r in rows}


def run_decay(tenant_id: str) -> int:
    now = time.time()
    aging_cutoff  = now - _AGING_DAYS * 86400
    stale_cutoff  = now - _STALE_DAYS * 86400
    archive_cutoff = now - _ARCHIVE_DAYS * 86400
    changed = 0
    with cognitive_conn() as c:
        r1 = c.execute(
            "UPDATE memory_lifecycle SET lifecycle_state=? WHERE tenant_id=? AND lifecycle_state NOT IN (?,?,?) AND last_accessed<?",
            (MemoryLifecycleState.ARCHIVED, tenant_id, MemoryLifecycleState.QUARANTINED, MemoryLifecycleState.ARCHIVED, MemoryLifecycleState.STALE, archive_cutoff)
        )
        r2 = c.execute(
            "UPDATE memory_lifecycle SET lifecycle_state=? WHERE tenant_id=? AND lifecycle_state NOT IN (?,?,?) AND last_accessed<?",
            (MemoryLifecycleState.STALE, tenant_id, MemoryLifecycleState.QUARANTINED, MemoryLifecycleState.ARCHIVED, MemoryLifecycleState.STALE, stale_cutoff)
        )
        r3 = c.execute(
            "UPDATE memory_lifecycle SET lifecycle_state=? WHERE tenant_id=? AND lifecycle_state='fresh' AND last_accessed<?",
            (MemoryLifecycleState.AGING, tenant_id, aging_cutoff)
        )
        changed = (r1.rowcount or 0) + (r2.rowcount or 0) + (r3.rowcount or 0)
    return changed


class LifecycleManager:
    def __init__(self):
        self._running = False

    async def start(self) -> None:
        self._running = True
        while self._running:
            await asyncio.sleep(6 * 3600)
            try:
                # Run decay for all known tenants
                with cognitive_conn() as c:
                    tenants = c.execute("SELECT DISTINCT tenant_id FROM memory_lifecycle").fetchall()
                for row in tenants:
                    run_decay(row["tenant_id"])
            except Exception as e:
                logger.warning("Lifecycle decay error: %s", e)

    def stop(self) -> None:
        self._running = False


_instance: Optional[LifecycleManager] = None


def get_lifecycle_manager() -> LifecycleManager:
    global _instance
    if _instance is None:
        _instance = LifecycleManager()
    return _instance
