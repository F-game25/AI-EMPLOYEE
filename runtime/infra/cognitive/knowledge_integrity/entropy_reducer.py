import logging
import math
from ..db import cognitive_conn

logger = logging.getLogger(__name__)


def prune_stale(tenant_id: str, min_access_count: int = 0) -> int:
    """Delete stale memories with low access patterns."""
    with cognitive_conn() as c:
        cur = c.execute(
            "DELETE FROM memory_lifecycle WHERE tenant_id=? AND lifecycle_state='stale' AND access_count<=?",
            (tenant_id, min_access_count)
        )
        return cur.rowcount


def calculate_entropy(tenant_id: str) -> float:
    """Calculate Shannon entropy of lifecycle state distribution (0=ordered, 1=chaotic)."""
    with cognitive_conn() as c:
        rows = c.execute(
            "SELECT lifecycle_state, COUNT(*) as cnt FROM memory_lifecycle WHERE tenant_id=? GROUP BY lifecycle_state",
            (tenant_id,)
        ).fetchall()
    total = sum(r["cnt"] for r in rows)
    if total <= 1:
        return 0.0
    entropy = 0.0
    for r in rows:
        p = r["cnt"] / total
        if p > 0:
            entropy -= p * math.log2(p)
    max_entropy = math.log2(len(rows)) if len(rows) > 1 else 1.0
    return entropy / max_entropy if max_entropy > 0 else 0.0


def get_stats(tenant_id: str) -> dict:
    """Get comprehensive knowledge entropy statistics."""
    with cognitive_conn() as c:
        total = c.execute("SELECT COUNT(*) as n FROM memory_lifecycle WHERE tenant_id=?", (tenant_id,)).fetchone()["n"]
        states = c.execute(
            "SELECT lifecycle_state, COUNT(*) as cnt FROM memory_lifecycle WHERE tenant_id=? GROUP BY lifecycle_state",
            (tenant_id,)
        ).fetchall()
        avg_conf = c.execute(
            "SELECT AVG(confidence) as avg FROM memory_lifecycle WHERE tenant_id=?", (tenant_id,)
        ).fetchone()["avg"] or 0.0
        low_conf = c.execute(
            "SELECT COUNT(*) as n FROM memory_lifecycle WHERE tenant_id=? AND confidence < 0.5", (tenant_id,)
        ).fetchone()["n"]

    state_dict = {r["lifecycle_state"]: r["cnt"] for r in states}
    entropy = calculate_entropy(tenant_id)

    return {
        "total_memories": total,
        "by_lifecycle": state_dict,
        "avg_confidence": round(avg_conf, 3),
        "low_confidence_count": low_conf,
        "entropy_score": round(entropy, 3),
        "entropy_health": "good" if entropy < 0.4 else "fair" if entropy < 0.7 else "poor",
        "tenant_id": tenant_id
    }


def report(tenant_id: str) -> dict:
    """Backward compatibility report function."""
    return get_stats(tenant_id)
