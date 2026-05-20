"""Validators ensuring payloads match the existing dashboard contract.

The frontend's brainStore expects nodes/links of a specific shape (see
frontend/src/store/brainStore.js). Use these to fail loudly if the
projection ever drifts from that contract.
"""
from __future__ import annotations

from typing import Any

DASHBOARD_NODE_TYPES = {
    "agent",
    "concept",
    "hidden",
    "input",
    "memory",
    "output",
    "skill",
    "strategy",
    "system",
    "task",
}

DASHBOARD_NODE_GROUPS = {
    "agent",
    "automation",
    "learning",
    "memory",
    "money",
    "system",
}


def validate_dashboard_graph(payload: Any) -> tuple[bool, list[str]]:
    errors: list[str] = []
    if not isinstance(payload, dict):
        return False, ["payload is not a dict"]
    nodes = payload.get("nodes")
    links = payload.get("links")
    if not isinstance(nodes, list):
        errors.append("nodes must be a list")
    if not isinstance(links, list):
        errors.append("links must be a list")
    if errors:
        return False, errors

    seen_ids: set[str] = set()
    for i, n in enumerate(nodes):
        if not isinstance(n, dict):
            errors.append(f"nodes[{i}] not a dict")
            continue
        nid = n.get("id")
        if not isinstance(nid, str) or not nid:
            errors.append(f"nodes[{i}].id missing")
        else:
            seen_ids.add(nid)
        if n.get("type") not in DASHBOARD_NODE_TYPES:
            errors.append(f"nodes[{i}].type {n.get('type')!r} not in {DASHBOARD_NODE_TYPES}")
        if "label" not in n:
            errors.append(f"nodes[{i}].label missing")
        if n.get("group") not in DASHBOARD_NODE_GROUPS:
            errors.append(f"nodes[{i}].group {n.get('group')!r} not in {DASHBOARD_NODE_GROUPS}")

    for i, l in enumerate(links):
        if not isinstance(l, dict):
            errors.append(f"links[{i}] not a dict")
            continue
        s, t = l.get("source"), l.get("target")
        if not s or not t:
            errors.append(f"links[{i}] missing source/target")
        elif s not in seen_ids or t not in seen_ids:
            errors.append(f"links[{i}] points to unknown node")

    return (len(errors) == 0), errors
