import hashlib
import json
import time
import logging
from ..db import cognitive_conn

logger = logging.getLogger(__name__)
_TTL = 300  # seconds


def _ensure_table() -> None:
    with cognitive_conn() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS wf_fingerprints (
                hash TEXT PRIMARY KEY,
                workflow_id TEXT NOT NULL,
                tenant_id TEXT NOT NULL,
                started_at REAL NOT NULL,
                expires_at REAL NOT NULL
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_fp_tenant ON wf_fingerprints(tenant_id)")


_ensure_table()


def _fingerprint(workflow_type: str, input_keys: list, tenant_id: str) -> str:
    payload = json.dumps({"t": workflow_type, "k": sorted(input_keys), "tid": tenant_id}, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


def check_or_register(workflow_type: str, input_keys: list, workflow_id: str, tenant_id: str) -> dict:
    fp = _fingerprint(workflow_type, input_keys, tenant_id)
    now = time.time()
    with cognitive_conn() as c:
        row = c.execute(
            "SELECT workflow_id FROM wf_fingerprints WHERE hash=? AND expires_at>?",
            (fp, now)
        ).fetchone()
        if row:
            return {"duplicate": True, "existing_workflow_id": row["workflow_id"]}
        c.execute(
            "INSERT OR REPLACE INTO wf_fingerprints VALUES (?,?,?,?,?)",
            (fp, workflow_id, tenant_id, now, now + _TTL)
        )
    return {"duplicate": False, "workflow_id": workflow_id}


def expire_old() -> int:
    with cognitive_conn() as c:
        cur = c.execute("DELETE FROM wf_fingerprints WHERE expires_at<?", (time.time(),))
        return cur.rowcount


def list_active(tenant_id: str) -> list[dict]:
    with cognitive_conn() as c:
        rows = c.execute(
            "SELECT * FROM wf_fingerprints WHERE tenant_id=? AND expires_at>?",
            (tenant_id, time.time())
        ).fetchall()
    return [dict(r) for r in rows]


def cleanup_expired() -> int:
    """Clean up expired fingerprints. Returns count deleted."""
    return expire_old()


def get_dedup_engine():
    """Get singleton deduplication engine instance."""
    return type("DeduplicationEngine", (), {
        "check_or_register": staticmethod(check_or_register),
        "list_active": staticmethod(list_active),
        "cleanup_expired": staticmethod(cleanup_expired),
    })()
