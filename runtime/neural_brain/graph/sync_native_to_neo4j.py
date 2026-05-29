"""One-shot sync: native SQLite graph → Neo4j.

The native store (`native_memory_graph.db`) is the always-on floor; Neo4j is the
upgrade. On boot (after Neo4j comes up) we mirror existing native nodes/edges into
Neo4j so the graph backend is populated from day one. Idempotent (MERGE on id).

Run:  python -m neural_brain.graph.sync_native_to_neo4j
Honors NEO4J_URI/USER/PASSWORD; no-ops cleanly if Neo4j is unavailable.
"""
from __future__ import annotations

import logging

logger = logging.getLogger("neo4j_sync")


def sync(limit: int = 5000) -> dict:
    from neural_brain.config import get_settings
    from neural_brain.graph.native_graph_store import NativeGraphStore
    from neural_brain.graph.neo4j_adapter import Neo4jAdapter

    native = NativeGraphStore()
    if not native.available:
        return {"ok": False, "reason": "native store unavailable"}

    s = get_settings()
    adapter = Neo4jAdapter(s.neo4j_uri, s.neo4j_user, s.neo4j_password)
    if not adapter.health().get("connected"):
        return {"ok": False, "reason": "neo4j unavailable", "error": adapter._init_error}

    snap = native.full_snapshot(limit=limit)
    nodes, links = snap.get("nodes", []), snap.get("links", [])

    for n in nodes:
        adapter.run_write(
            "MERGE (c:Concept {id:$id}) "
            "ON CREATE SET c.label=$label, c.type=$type, c.group=$group, "
            "c.confidence=$conf, c.source=$src, c.created_at=timestamp() "
            "ON MATCH SET c.label=$label, c.type=$type, c.group=$group, c.confidence=$conf",
            id=str(n.get("id")), label=str(n.get("label", "")), type=str(n.get("type", "concept")),
            group=str(n.get("group", "memory")), conf=float(n.get("confidence", 0.5) or 0.5),
            src=str(n.get("source", "native_sync")),
        )
    for l in links:
        adapter.run_write(
            "MATCH (a:Concept {id:$s}), (b:Concept {id:$t}) "
            "MERGE (a)-[r:RELATED {type:$type}]->(b) "
            "ON CREATE SET r.weight=$w ON MATCH SET r.weight=$w",
            s=str(l.get("source")), t=str(l.get("target")),
            type=str(l.get("type", "RELATED")), w=float(l.get("weight", 0.5) or 0.5),
        )

    count = adapter.run_read("MATCH (c:Concept) RETURN count(c) AS n")
    adapter.close()
    return {"ok": True, "nodes_synced": len(nodes), "links_synced": len(links),
            "neo4j_concept_count": (count[0]["n"] if count else None)}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(sync())
