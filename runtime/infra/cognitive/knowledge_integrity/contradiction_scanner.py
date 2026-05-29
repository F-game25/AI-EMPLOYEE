import logging
import time
import uuid
from .schema import Contradiction
from ..db import cognitive_conn

logger = logging.getLogger(__name__)


def _ensure_table() -> None:
    with cognitive_conn() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS contradictions (
                id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                memory_id_a TEXT NOT NULL,
                memory_id_b TEXT NOT NULL,
                conflict_type TEXT DEFAULT 'logical',
                confidence REAL DEFAULT 0.8,
                description TEXT,
                detected_at REAL NOT NULL
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_contra_tenant ON contradictions(tenant_id, detected_at)")


_ensure_table()


def scan(memories: list[dict], tenant_id: str = "system") -> list[Contradiction]:
    conflicts = []
    by_topic: dict[str, list] = {}
    for m in memories:
        topic = m.get("topic") or m.get("key", "")
        if topic:
            by_topic.setdefault(topic, []).append(m)

    for topic, group in by_topic.items():
        if len(group) < 2:
            continue
        values = [m.get("content", "") for m in group]
        for i in range(len(values)):
            for j in range(i+1, len(values)):
                contradiction_info = _check_contradiction(values[i], values[j])
                if contradiction_info:
                    contra = Contradiction(
                        id=str(uuid.uuid4()),
                        tenant_id=tenant_id,
                        memory_id_a=group[i].get("id", ""),
                        memory_id_b=group[j].get("id", ""),
                        conflict_type=contradiction_info["type"],
                        confidence=contradiction_info["confidence"],
                        description=f"{topic}: '{values[i][:50]}' vs '{values[j][:50]}'"
                    )
                    conflicts.append(contra)
                    _store_contradiction(contra)
    return conflicts


def _check_contradiction(a: str, b: str) -> dict | None:
    negations = {"not", "no", "never", "without", "false", "incorrect", "wrong"}
    words_a = set(a.lower().split())
    words_b = set(b.lower().split())
    overlap = words_a & words_b
    if not overlap:
        return None
    neg_a = bool(negations & words_a)
    neg_b = bool(negations & words_b)
    if neg_a != neg_b and len(overlap) >= 3:
        return {"type": "logical", "confidence": min(0.95, len(overlap) / max(len(words_a), len(words_b)))}
    return None


def _store_contradiction(c: Contradiction) -> None:
    with cognitive_conn() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO contradictions VALUES (?,?,?,?,?,?,?,?)",
            (c.id, c.tenant_id, c.memory_id_a, c.memory_id_b, c.conflict_type,
             c.confidence, c.description, c.detected_at)
        )


def list_contradictions(tenant_id: str, limit: int = 50) -> list[dict]:
    with cognitive_conn() as c:
        rows = c.execute(
            "SELECT * FROM contradictions WHERE tenant_id=? ORDER BY detected_at DESC LIMIT ?",
            (tenant_id, limit)
        ).fetchall()
    return [dict(r) for r in rows]
