"""High-level Knowledge Graph API backed by native graph memory.

The embedded SQLite graph is the offline-first core backend. A Neo4j adapter
may mirror reads/writes when available, but graph memory must not become a
no-op just because an external graph server is offline.
"""
from __future__ import annotations

import hashlib
import logging
from typing import Any

from neural_brain.graph.neo4j_adapter import Neo4jAdapter
from neural_brain.graph.native_graph_store import NativeGraphStore

logger = logging.getLogger(__name__)

# Whitelist for relationship types (Cypher rel-type cannot be parameterised).
_ALLOWED_RELS: frozenset[str] = frozenset(
    {"RELATES_TO", "USED_IN", "PRODUCED", "DERIVED_FROM", "MENTIONS"}
)

# Labels that are safe to combine onto a Concept node when type != "Concept".
_TYPE_LABEL_WHITELIST: frozenset[str] = frozenset(
    {"Concept", "Skill", "Memory", "Strategy", "Output", "Input", "Task"}
)


def _hash16(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]


def _hash12(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:12]


class BrainGraph:
    def __init__(self, adapter: Neo4jAdapter, native_store: NativeGraphStore | None = None) -> None:
        self._adapter = adapter
        self._native = native_store or NativeGraphStore()
        self._adapter_available_cached: bool | None = None

    # ── status ────────────────────────────────────────────────────────────
    @property
    def available(self) -> bool:
        return bool(self._native.available or self.adapter_available)

    @property
    def adapter_available(self) -> bool:
        if self._adapter_available_cached is None:
            self._adapter_available_cached = bool(self._adapter.health().get("connected"))
        return self._adapter_available_cached

    def _refresh_availability(self) -> bool:
        self._adapter_available_cached = None
        return self.available

    # ── upserts ───────────────────────────────────────────────────────────
    def upsert_concept(
        self,
        label: str,
        *,
        type: str = "Concept",
        weight: float = 1.0,
    ) -> str:
        cid = _hash16(f"{type}:{label.lower()}")
        try:
            self._native.upsert_node(
                cid,
                label,
                type=type,
                group=type,
                source="python_brain_graph",
                confidence=weight,
                metadata={"neo4j_compatible_label": "Concept"},
            )
        except Exception as e:
            logger.warning("native upsert_concept failed for %s: %s", label, e)
        if not self.adapter_available:
            return cid

        # Build the optional secondary label safely from a whitelist.
        extra_label = ""
        if type and type != "Concept" and type in _TYPE_LABEL_WHITELIST:
            extra_label = f":{type}"

        cypher = (
            f"MERGE (c:Concept{extra_label} {{id:$id}}) "
            "ON CREATE SET c.label=$label, c.type=$type, c.weight=$weight, c.created_at=timestamp() "
            "ON MATCH  SET c.weight = c.weight + 0.05*($weight - c.weight) "
            "RETURN c.id AS id"
        )
        try:
            self._adapter.run_write(cypher, id=cid, label=label, type=type, weight=weight)
        except Exception as e:
            logger.warning("upsert_concept failed for %s: %s", label, e)
        return cid

    def upsert_skill(self, name: str, description: str = "") -> str:
        sid = "skill_" + _hash12(name)
        try:
            self._native.upsert_node(
                sid,
                name,
                type="Skill",
                group="Skill",
                source="python_brain_graph",
                metadata={"description": description},
            )
        except Exception as e:
            logger.warning("native upsert_skill failed for %s: %s", name, e)
        if not self.adapter_available:
            return sid
        cypher = (
            "MERGE (s:Skill {id:$id}) "
            "ON CREATE SET s.name=$name, s.description=$desc, s.created_at=timestamp() "
            "ON MATCH  SET s.description = CASE WHEN $desc <> '' THEN $desc ELSE s.description END "
            "RETURN s.id AS id"
        )
        try:
            self._adapter.run_write(cypher, id=sid, name=name, desc=description)
        except Exception as e:
            logger.warning("upsert_skill failed for %s: %s", name, e)
        return sid

    def attach_memory(
        self,
        memory_id: str,
        concept_ids: list[str],
        *,
        label: str = "MENTIONS",
    ) -> None:
        if not concept_ids:
            return
        try:
            self._native.attach_memory(memory_id, concept_ids, label=label)
        except Exception as e:
            logger.warning("native attach_memory failed for %s: %s", memory_id, e)
        if not self.adapter_available:
            return
        if label not in _ALLOWED_RELS:
            logger.warning("attach_memory rejected non-whitelisted rel %r", label)
            return
        # Only MENTIONS makes semantic sense from Memory→Concept here.
        cypher = (
            "MERGE (m:Memory {id:$mid}) "
            "ON CREATE SET m.created_at=timestamp() "
            "WITH m "
            "UNWIND $cids AS cid "
            "MATCH (c:Concept {id:cid}) "
            f"MERGE (m)-[r:{label}]->(c) "
            "ON CREATE SET r.created_at=timestamp(), r.strength=1 "
            "ON MATCH  SET r.strength = r.strength + 1"
        )
        try:
            self._adapter.run_write(cypher, mid=memory_id, cids=concept_ids)
        except Exception as e:
            logger.warning("attach_memory failed for %s: %s", memory_id, e)

    def link(
        self,
        src_id: str,
        dst_id: str,
        *,
        rel: str = "RELATES_TO",
        strength: float = 0.5,
    ) -> None:
        try:
            self._native.upsert_edge(src_id, dst_id, rel=rel, strength=strength, source_system="python_brain_graph")
        except Exception as e:
            logger.warning("native graph link failed (%s -> %s): %s", src_id, dst_id, e)
        if not self.adapter_available:
            return
        if rel not in _ALLOWED_RELS:
            logger.warning("link rejected non-whitelisted rel %r", rel)
            return
        cypher = (
            "MATCH (a {id:$s}), (b {id:$d}) "
            f"MERGE (a)-[r:{rel}]->(b) "
            "ON CREATE SET r.created_at=timestamp(), r.strength=$strength "
            "ON MATCH  SET r.strength = r.strength + 0.1*($strength - r.strength)"
        )
        try:
            self._adapter.run_write(cypher, s=src_id, d=dst_id, strength=strength)
        except Exception as e:
            logger.warning("link failed (%s -> %s): %s", src_id, dst_id, e)

    # ── reads ─────────────────────────────────────────────────────────────
    def neighborhood(
        self,
        seed_ids: list[str] | None = None,
        *,
        seed_labels: list[str] | None = None,
        depth: int = 2,
        limit: int = 50,
    ) -> dict[str, Any]:
        empty = {"nodes": [], "links": []}
        if not self.available:
            return empty
        if not self.adapter_available:
            return self._native.neighborhood(seed_ids=seed_ids, limit=limit)

        # Validate depth (Cypher path range can't be parameterised).
        depth = max(1, min(int(depth), 5))

        try:
            if seed_ids:
                # Try APOC first for richer subgraph traversal.
                apoc_cypher = (
                    "MATCH (n) WHERE n.id IN $ids "
                    "CALL apoc.path.subgraphAll(n, {maxLevel:$depth, limit:$limit}) "
                    "YIELD nodes, relationships "
                    "RETURN nodes, relationships"
                )
                try:
                    rows = self._adapter.run_read(
                        apoc_cypher, ids=seed_ids, depth=depth, limit=limit
                    )
                    nodes_acc: list[Any] = []
                    rels_acc: list[Any] = []
                    for r in rows:
                        nodes_acc.extend(r.get("nodes") or [])
                        rels_acc.extend(r.get("relationships") or [])
                    return _materialize_subgraph(nodes_acc, rels_acc)
                except Exception:
                    # APOC unavailable — fall back to a plain variable-length pattern.
                    fallback = (
                        f"MATCH (n)-[r*1..{depth}]-(m) "
                        "WHERE n.id IN $ids "
                        "RETURN n, r, m LIMIT $limit"
                    )
                    rows = self._adapter.run_read(fallback, ids=seed_ids, limit=limit)
                    return _materialize_path_rows(rows)

            # No seeds: top concepts by weight, plus first-degree neighbours.
            cypher = (
                "MATCH (c:Concept) "
                "WITH c ORDER BY coalesce(c.weight, 0) DESC LIMIT $limit "
                "OPTIONAL MATCH (c)-[r]-(m) "
                "RETURN c, r, m"
            )
            rows = self._adapter.run_read(cypher, limit=limit)
            return _materialize_path_rows(rows)
        except Exception as e:
            logger.warning("neighborhood query failed: %s", e)
            return self._native.neighborhood(seed_ids=seed_ids, limit=limit)

    def full_snapshot(self, *, limit: int = 200) -> dict[str, Any]:
        if not self.available:
            return {"nodes": [], "links": []}
        if not self.adapter_available:
            return self._native.full_snapshot(limit=limit)
        try:
            cypher = (
                "MATCH (c:Concept) "
                "WITH c ORDER BY coalesce(c.weight, 0) DESC LIMIT $limit "
                "OPTIONAL MATCH (c)-[r]-(m) "
                "RETURN c, r, m"
            )
            rows = self._adapter.run_read(cypher, limit=limit)
            return _materialize_path_rows(rows)
        except Exception as e:
            logger.warning("full_snapshot failed: %s", e)
            return self._native.full_snapshot(limit=limit)

    def stats(self) -> dict[str, Any]:
        native_stats = self._native.stats()
        out = {
            "concepts": 0,
            "skills": 0,
            "memories": 0,
            "relationships": 0,
            "available": self.available,
            "native": native_stats,
            "backend": "native_sqlite_graph",
            "neo4j_connected": self.adapter_available,
        }
        if not self.adapter_available:
            out.update({
                "concepts": int(native_stats.get("concepts") or 0),
                "skills": int(native_stats.get("skills") or 0),
                "memories": int(native_stats.get("memories") or 0),
                "relationships": int(native_stats.get("relationships") or 0),
            })
            return out
        try:
            rows = self._adapter.run_read(
                "MATCH (c:Concept) WITH count(c) AS concepts "
                "MATCH (s:Skill) WITH concepts, count(s) AS skills "
                "MATCH (m:Memory) WITH concepts, skills, count(m) AS memories "
                "MATCH ()-[r]->() "
                "RETURN concepts, skills, memories, count(r) AS relationships"
            )
            if rows:
                row = rows[0]
                out.update(
                    {
                        "concepts": int(row.get("concepts") or 0),
                        "skills": int(row.get("skills") or 0),
                        "memories": int(row.get("memories") or 0),
                        "relationships": int(row.get("relationships") or 0),
                    }
                )
        except Exception as e:
            logger.warning("stats query failed: %s", e)
        return out


# ── result materialisation helpers ────────────────────────────────────────
def _node_to_dict(n: Any) -> dict[str, Any]:
    """Convert a neo4j Node (or already-dict) into the raw form."""
    if isinstance(n, dict) and "id" in n and "labels" in n and "props" in n:
        return n
    try:
        labels = list(getattr(n, "labels", []) or [])
        props = dict(n)  # neo4j Node supports dict()
    except Exception:
        labels, props = [], {}
    nid = props.get("id") or str(getattr(n, "element_id", "") or getattr(n, "id", ""))
    label = props.get("label") or props.get("name") or nid
    return {"id": nid, "label": label, "labels": labels, "props": props}


def _rel_to_dict(r: Any) -> dict[str, Any]:
    try:
        rtype = getattr(r, "type", None) or r.get("type") if isinstance(r, dict) else None
        rtype = rtype or getattr(r, "type", "RELATES_TO")
        start = getattr(r, "start_node", None)
        end = getattr(r, "end_node", None)
        s_id = (dict(start).get("id") if start is not None else None) or ""
        e_id = (dict(end).get("id") if end is not None else None) or ""
        props = dict(r)
    except Exception:
        return {}
    return {"source": s_id, "target": e_id, "rel": rtype, "props": props}


def _materialize_subgraph(nodes: list[Any], rels: list[Any]) -> dict[str, Any]:
    seen_n: dict[str, dict[str, Any]] = {}
    seen_l: set[tuple[str, str, str]] = set()
    out_links: list[dict[str, Any]] = []
    for n in nodes:
        nd = _node_to_dict(n)
        if nd.get("id") and nd["id"] not in seen_n:
            seen_n[nd["id"]] = nd
    for r in rels:
        rd = _rel_to_dict(r)
        if not rd:
            continue
        key = (rd["source"], rd["target"], rd["rel"])
        if key in seen_l:
            continue
        seen_l.add(key)
        out_links.append(rd)
    return {"nodes": list(seen_n.values()), "links": out_links}


def _materialize_path_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Rows from a `RETURN n, r, m` (with optional list `r`) pattern."""
    seen_n: dict[str, dict[str, Any]] = {}
    seen_l: set[tuple[str, str, str]] = set()
    out_links: list[dict[str, Any]] = []

    for row in rows:
        for key in ("n", "c", "m"):
            node = row.get(key)
            if node is None:
                continue
            nd = _node_to_dict(node)
            if nd.get("id") and nd["id"] not in seen_n:
                seen_n[nd["id"]] = nd

        rel = row.get("r")
        if rel is None:
            continue
        rels = rel if isinstance(rel, list) else [rel]
        for rr in rels:
            rd = _rel_to_dict(rr)
            if not rd or not rd.get("source") or not rd.get("target"):
                continue
            k = (rd["source"], rd["target"], rd["rel"])
            if k in seen_l:
                continue
            seen_l.add(k)
            out_links.append(rd)

    return {"nodes": list(seen_n.values()), "links": out_links}
