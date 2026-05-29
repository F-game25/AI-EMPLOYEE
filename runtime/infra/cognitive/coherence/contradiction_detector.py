"""Contradiction detection engine.

Monitors agent output for logical contradictions using cosine similarity.
Tracks results in rolling window and escalates to HITL when conflicts detected.
"""
import collections
import time
import logging
from typing import Optional
from ..db import cognitive_conn
from .schema import Contradiction

logger = logging.getLogger(__name__)

_WINDOW = 100  # last N results to compare
_SIM_THRESHOLD = 0.3  # cosine sim below this = contradiction
_result_window: collections.deque = collections.deque(maxlen=_WINDOW)


def _ensure_table() -> None:
    """Create contradictions table if not exists."""
    with cognitive_conn() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS contradictions (
                id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                agent_a TEXT NOT NULL,
                agent_b TEXT NOT NULL,
                claim_a TEXT NOT NULL,
                claim_b TEXT NOT NULL,
                detected_at REAL NOT NULL,
                resolved INTEGER DEFAULT 0,
                resolution TEXT
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_cont_tenant ON contradictions(tenant_id, resolved)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_cont_time ON contradictions(detected_at DESC)")


_ensure_table()


def _cosine_sim(a: str, b: str) -> float:
    """Compute cosine similarity between two text strings."""
    sa, sb = set(a.lower().split()), set(b.lower().split())
    if not sa or not sb:
        return 0.0
    intersection = len(sa & sb)
    union = len(sa | sb)
    return intersection / (union + 1e-9) if union > 0 else 0.0


def ingest_result(agent_id: str, tenant_id: str, result: dict) -> None:
    """Ingest agent result and check for contradictions with recent results."""
    entry = {"agent": agent_id, "tenant": tenant_id, "data": result, "ts": time.time()}

    contradictions_found = 0
    for prev in list(_result_window):
        if prev["tenant"] != tenant_id:
            continue
        for key in result:
            if key not in prev["data"]:
                continue
            a_val = str(result[key]).strip()
            b_val = str(prev["data"][key]).strip()
            if not a_val or not b_val:
                continue
            sim = _cosine_sim(a_val, b_val)
            if sim < _SIM_THRESHOLD and a_val != b_val:
                _record_contradiction(tenant_id, agent_id, prev["agent"], f"{key}={a_val}", f"{key}={b_val}")
                contradictions_found += 1

    if contradictions_found > 0:
        logger.warning(f"Found {contradictions_found} contradiction(s) for {agent_id} in tenant {tenant_id}")

    _result_window.append(entry)


def _record_contradiction(tenant_id: str, a: str, b: str, claim_a: str, claim_b: str) -> None:
    """Record a detected contradiction."""
    c = Contradiction(tenant_id=tenant_id, agent_a=a, agent_b=b, claim_a=claim_a, claim_b=claim_b)
    with cognitive_conn() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO contradictions VALUES (?,?,?,?,?,?,?,?,?)",
            (c.id, c.tenant_id, c.agent_a, c.agent_b, c.claim_a, c.claim_b, c.detected_at, 0, None)
        )
        conn.commit()
    logger.info(f"Contradiction recorded: {a} vs {b} in {tenant_id}")

    try:
        from core.bus import get_message_bus
        get_message_bus().publish_sync("notifications", {
            "event": "cognitive:contradiction",
            "tenant_id": tenant_id,
            "agents": [a, b],
            "id": c.id,
        })
    except Exception as e:
        logger.debug(f"Bus publish failed: {e}")


def resolve_contradiction(cont_id: str, resolution: str) -> None:
    """Mark contradiction as resolved."""
    with cognitive_conn() as c:
        c.execute(
            "UPDATE contradictions SET resolved=1, resolution=? WHERE id=?",
            (resolution, cont_id)
        )
        c.commit()


def list_contradictions(tenant_id: str, resolved: bool = False, limit: int = 50) -> list[dict]:
    """List contradictions for tenant."""
    with cognitive_conn() as c:
        rows = c.execute(
            "SELECT * FROM contradictions WHERE tenant_id=? AND resolved=? ORDER BY detected_at DESC LIMIT ?",
            (tenant_id, 1 if resolved else 0, limit)
        ).fetchall()
    return [dict(r) for r in rows]
