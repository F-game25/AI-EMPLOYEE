import logging
import uuid
import time
from .schema import DuplicateCluster
from ..db import cognitive_conn

logger = logging.getLogger(__name__)
_SIM_THRESHOLD = 0.92


def _ensure_table() -> None:
    with cognitive_conn() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS duplicate_clusters (
                cluster_id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                memory_ids TEXT NOT NULL,
                similarity REAL NOT NULL,
                recommended_keep TEXT NOT NULL,
                detected_at REAL NOT NULL
            )
        """)


_ensure_table()


def _word_sim(a: str, b: str) -> float:
    sa, sb = set(a.lower().split()), set(b.lower().split())
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def find_duplicates(memories: list[dict], tenant_id: str) -> list[DuplicateCluster]:
    clusters = []
    seen = set()
    for i, m1 in enumerate(memories):
        if m1["id"] in seen:
            continue
        group = [m1]
        for m2 in memories[i+1:]:
            if m2["id"] in seen:
                continue
            try:
                try:
                    from engine.api import embed
                    e1, e2 = embed(m1.get("content", "")), embed(m2.get("content", ""))
                    norm1 = sum(x*x for x in e1) ** 0.5
                    norm2 = sum(x*x for x in e2) ** 0.5
                    if norm1 > 0 and norm2 > 0:
                        sim = sum(a*b for a, b in zip(e1, e2)) / (norm1 * norm2)
                    else:
                        sim = 0.0
                except (ImportError, Exception):
                    sim = _word_sim(m1.get("content", ""), m2.get("content", ""))
            except Exception:
                sim = _word_sim(m1.get("content", ""), m2.get("content", ""))
            if sim >= _SIM_THRESHOLD:
                group.append(m2)
                seen.add(m2["id"])
        if len(group) > 1:
            keep = max(group, key=lambda x: x.get("confidence", 1.0))["id"]
            cluster = DuplicateCluster(
                cluster_id=str(uuid.uuid4()),
                tenant_id=tenant_id,
                memory_ids=[m["id"] for m in group],
                similarity_scores=[_word_sim(m["content"], m1.get("content", "")) for m in group],
                canonical_id=keep,
                consolidated_text=" ".join([m.get("content", "") for m in group])[:500],
            )
            clusters.append(cluster)
            _store_cluster(cluster, tenant_id)
    return clusters


def _store_cluster(c: DuplicateCluster, tenant_id: str) -> None:
    import json
    with cognitive_conn() as conn:
        sim_avg = sum(c.similarity_scores) / max(len(c.similarity_scores), 1) if c.similarity_scores else 0.0
        conn.execute(
            "INSERT OR REPLACE INTO duplicate_clusters VALUES (?,?,?,?,?,?)",
            (c.cluster_id, tenant_id, json.dumps(c.memory_ids), sim_avg, c.canonical_id or c.memory_ids[0] if c.memory_ids else "", c.detected_at)
        )


def list_clusters(tenant_id: str) -> list[dict]:
    import json
    with cognitive_conn() as c:
        rows = c.execute(
            "SELECT * FROM duplicate_clusters WHERE tenant_id=? ORDER BY detected_at DESC LIMIT 50",
            (tenant_id,)
        ).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        d["memory_ids"] = json.loads(d["memory_ids"])
        d["recommended_keep"] = d.get("recommended_keep", "")
        result.append(d)
    return result


_instance = None


def get_deduplicator():
    global _instance
    if _instance is None:
        _instance = type("Deduplicator", (), {
            "find_duplicates": staticmethod(find_duplicates),
            "list_clusters": staticmethod(list_clusters),
        })()
    return _instance
