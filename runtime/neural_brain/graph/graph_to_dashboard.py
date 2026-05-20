"""Transform BrainGraph.full_snapshot() output into the dashboard wire format.

BrainGraph returns:
  {
    "nodes": [{"id", "label", "labels": [...], "props": {...}}],
    "links": [{"source", "target", "rel", "props": {...}}]
  }

Dashboard (brainStore) expects:
  {
    "nodes": [{"id", "label", "type", "group", "weight", "activation"}],
    "links": [{"source", "target", "strength"}],
    "connections": [{"from", "to", "weight"}],  # legacy mirror
    "stats": {"node_count", "link_count"}
  }
"""
from __future__ import annotations

from typing import Any

# Maps Neo4j label -> canonical lowercase dashboard node type.
_LABEL_TO_TYPE: dict[str, str] = {
    "Concept": "concept",
    "Skill": "skill",
    "Memory": "memory",
    "Task": "task",
    "Output": "output",
    "Input": "input",
    "Strategy": "strategy",
    "Agent": "agent",
}

_TYPE_TO_GROUP: dict[str, str] = {
    "concept": "money",
    "skill": "money",
    "strategy": "money",
    "memory": "memory",
    "task": "automation",
    "output": "automation",
    "input": "learning",
    "hidden": "learning",
    "agent": "agent",
}

_REL_WEIGHT: dict[str, float] = {
    "RELATES_TO": 0.3,
    "USED_IN": 0.5,
    "PRODUCED": 0.6,
    "DERIVED_FROM": 0.4,
    "MENTIONS": 0.25,
}


def _infer_type(node: dict[str, Any]) -> str:
    for lbl in node.get("labels", []):
        if lbl in _LABEL_TO_TYPE:
            return _LABEL_TO_TYPE[lbl]
    props = node.get("props", {})
    t = str(props.get("type") or props.get("node_type") or "").strip()
    return _LABEL_TO_TYPE.get(t, _LABEL_TO_TYPE.get(t.title(), t.lower() or "skill"))


def _infer_group(node_type: str) -> str:
    return _TYPE_TO_GROUP.get(node_type, "system")


def graph_to_dashboard(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Convert a BrainGraph snapshot to the dashboard wire format."""
    raw_nodes: list[dict[str, Any]] = snapshot.get("nodes", [])
    raw_links: list[dict[str, Any]] = snapshot.get("links", [])

    nodes: list[dict[str, Any]] = []
    for n in raw_nodes:
        props = n.get("props", {})
        node_type = _infer_type(n)
        nodes.append({
            "id": n.get("id", ""),
            "label": n.get("label") or n.get("id", ""),
            "type": node_type,
            "group": _infer_group(node_type),
            "weight": float(props.get("weight", 1.0)),
            "activation": float(props.get("activation", 0.3)),
        })

    connections: list[dict[str, Any]] = []
    for lnk in raw_links:
        src = lnk.get("source", "")
        tgt = lnk.get("target", "")
        if not src or not tgt:
            continue
        rel = lnk.get("rel", "RELATES_TO")
        lnk_props = lnk.get("props", {})
        weight = float(lnk_props.get("strength", lnk_props.get("weight", _REL_WEIGHT.get(rel, 0.3))))
        connections.append({"from": src, "to": tgt, "weight": weight})

    return {
        "nodes": nodes,
        "links": [
            {"source": c["from"], "target": c["to"], "strength": c["weight"]}
            for c in connections
        ],
        "connections": connections,
        "stats": {
            "node_count": len(nodes),
            "link_count": len(connections),
        },
    }
