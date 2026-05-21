"""Four memory graph views for the living neural-network UI (WS3).

Maps the memory subsystem onto four force-graph payloads, all in the dashboard
{nodes, links, stats} shape so the frontend renderer can be reused:

  shortterm — episodic cache entries, with `decay` for fade animation
  longterm  — persistent vector-store knowledge (semantic + procedural)
  relations — concept↔concept edges from the native graph store
  unified   — all of the above + live task nodes, cross-linked

No fake data: an empty subsystem yields an empty graph, not placeholders.
"""
from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path

logger = logging.getLogger(__name__)

VIEWS = ("shortterm", "longterm", "relations", "unified")

# Group → matches frontend GROUP_COLORS (money/learning/automation/memory/system/agent)
_TYPE_GROUP = {
    "episodic": "automation",
    "semantic": "learning",
    "procedural": "memory",
    "task": "agent",
    "concept": "memory",
}


def _label(text: str, n: int = 42) -> str:
    t = (text or "").strip().replace("\n", " ")
    return (t[:n] + "…") if len(t) > n else (t or "·")


def _state_dir() -> Path:
    # Canonical: STATE_DIR → AI_EMPLOYEE_HOME/AI_HOME → ~/.ai-employee, then /state.
    # Matches start.sh and the other modules so every subsystem reads one state dir.
    home = Path(os.environ.get("AI_EMPLOYEE_HOME") or os.environ.get("AI_HOME") or Path.home() / ".ai-employee")
    return Path(os.environ.get("STATE_DIR") or home / "state").resolve()


def _shortterm(limit: int) -> dict:
    """Episodic short-term cache → nodes with decay; chained by recency."""
    try:
        from memory.short_term_cache import get_short_term_cache
        snap = get_short_term_cache().snapshot_detailed()
    except Exception as e:  # noqa: BLE001
        logger.warning("shortterm view failed: %s", e)
        return {"nodes": [], "links": [], "stats": {}}
    nodes, links = [], []
    items = sorted(snap.items(), key=lambda kv: kv[1].get("ttl_remaining", 0), reverse=True)[:limit]
    prev = None
    for key, meta in items:
        val = meta.get("value")
        text = val.get("text") if isinstance(val, dict) else str(val)
        nid = f"st:{key}"
        nodes.append({
            "id": nid, "label": _label(text), "type": "episodic", "group": "automation",
            "decay": meta.get("decay", 0.0), "ttl_remaining": round(meta.get("ttl_remaining", 0), 1),
            "val": max(1, 4 * (1 - meta.get("decay", 0.0))),
        })
        if prev:
            links.append({"source": prev, "target": nid, "type": "RECALL_SEQ", "weight": 0.3})
        prev = nid
    return {"nodes": nodes, "links": links, "stats": {"node_count": len(nodes), "link_count": len(links)}}


def _longterm(limit: int) -> dict:
    """Vector-store knowledge → nodes grouped by memory_type."""
    try:
        from memory.vector_store import get_vector_store
        entries = get_vector_store().snapshot(limit=limit)
    except Exception as e:  # noqa: BLE001
        logger.warning("longterm view failed: %s", e)
        return {"nodes": [], "links": [], "stats": {}}
    nodes = []
    for e in entries:
        meta = e.get("metadata") or {}
        mtype = meta.get("memory_type") or e.get("memory_type") or "semantic"
        nid = str(e.get("id") or e.get("key") or _label(e.get("text", ""), 24))
        nodes.append({
            "id": f"lt:{nid}", "label": _label(e.get("text", "")), "type": mtype,
            "group": _TYPE_GROUP.get(mtype, "learning"),
            "val": 2 + 4 * float(e.get("importance", 0.4) or 0.4),
        })
    return {"nodes": nodes, "links": [], "stats": {"node_count": len(nodes), "link_count": 0}}


def _relations(limit: int) -> dict:
    """Concept graph (native graph store) → nodes + edges."""
    try:
        from neural_brain.graph.native_graph_store import NativeGraphStore
        store = NativeGraphStore()
        if not store.available:  # property, not method
            return {"nodes": [], "links": [], "stats": {}}
        snap = store.full_snapshot(limit=limit)
    except Exception as e:  # noqa: BLE001
        logger.warning("relations view failed: %s", e)
        return {"nodes": [], "links": [], "stats": {}}
    nodes = [{
        "id": f"rel:{n.get('id')}", "label": _label(n.get("label", "")),
        "type": n.get("type") or "concept", "group": n.get("group") or "memory",
        "val": 2 + 4 * float(n.get("confidence", 0.5) or 0.5),
    } for n in snap.get("nodes", [])]
    links = [{
        "source": f"rel:{l.get('source')}", "target": f"rel:{l.get('target')}",
        "type": l.get("type") or "RELATED", "weight": float(l.get("weight", 0.5) or 0.5),
    } for l in snap.get("links", [])]
    return {"nodes": nodes, "links": links, "stats": {"node_count": len(nodes), "link_count": len(links)}}


def _live_tasks(limit: int = 40) -> list[dict]:
    """Recent task nodes from state/tasks.json (best-effort)."""
    try:
        p = _state_dir() / "tasks.json"
        if not p.exists():
            return []
        data = json.loads(p.read_text() or "[]")
        tasks = data if isinstance(data, list) else (data.get("tasks") or list(data.values()))
        out = []
        for t in tasks[:limit]:
            if not isinstance(t, dict):
                continue
            tid = str(t.get("id") or t.get("task_id") or t.get("name", ""))[:48]
            status = t.get("status", "pending")
            out.append({
                "id": f"task:{tid}", "label": _label(t.get("goal") or t.get("name") or tid, 36),
                "type": "task", "group": "agent", "status": status,
                "active": status in ("active", "running", "in_progress"),
                "val": 5,
            })
        return out
    except Exception as e:  # noqa: BLE001
        logger.warning("live tasks failed: %s", e)
        return []


def _unified(limit: int) -> dict:
    """Everything merged + live tasks — the 'alive' whole-system graph."""
    st, lt, rel = _shortterm(limit), _longterm(limit), _relations(limit)
    nodes: dict[str, dict] = {}
    links: list[dict] = []
    for part in (lt, rel, st):
        for n in part["nodes"]:
            nodes.setdefault(n["id"], n)
        links.extend(part["links"])
    for tnode in _live_tasks():
        nodes.setdefault(tnode["id"], tnode)
    return {"nodes": list(nodes.values()), "links": links,
            "stats": {"node_count": len(nodes), "link_count": len(links),
                      "sources": {"shortterm": len(st["nodes"]), "longterm": len(lt["nodes"]),
                                  "relations": len(rel["nodes"])}}}


_BUILDERS = {"shortterm": _shortterm, "longterm": _longterm, "relations": _relations, "unified": _unified}


def build_view(view: str, limit: int = 300) -> dict:
    """Return a {nodes, links, stats, view, ts} payload for one of VIEWS."""
    fn = _BUILDERS.get(view)
    if fn is None:
        return {"nodes": [], "links": [], "stats": {}, "view": view, "error": "unknown view"}
    payload = fn(limit)
    payload["view"] = view
    payload["ts"] = time.time()
    return payload
