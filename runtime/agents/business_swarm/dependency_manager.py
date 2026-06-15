"""dependency_manager — topological ordering of subtasks by depends_on; cycle detection."""

from __future__ import annotations

from typing import Any


class DependencyCycleError(ValueError):
    """Raised when subtask dependencies form a cycle."""


def topological_order(subtasks: list[dict[str, Any]]) -> list[str]:
    """Return subtask ids in dependency order. Raises DependencyCycleError on a cycle."""
    ids = [str(st["id"]) for st in subtasks]
    id_set = set(ids)
    # Only count edges that point at real subtasks (ignore dangling refs honestly).
    deps: dict[str, set[str]] = {
        str(st["id"]): {d for d in (st.get("depends_on") or []) if d in id_set and d != st["id"]}
        for st in subtasks
    }

    ordered: list[str] = []
    resolved: set[str] = set()
    # Kahn-style with deterministic ordering (catalog/subtask order preserved).
    while len(ordered) < len(ids):
        progressed = False
        for sid in ids:
            if sid in resolved:
                continue
            if deps[sid] <= resolved:
                ordered.append(sid)
                resolved.add(sid)
                progressed = True
        if not progressed:
            remaining = [s for s in ids if s not in resolved]
            raise DependencyCycleError(f"dependency cycle among: {remaining}")
    return ordered


def independent_groups(subtasks: list[dict[str, Any]]) -> list[list[str]]:
    """Group subtask ids into waves runnable in parallel (each wave depends only on prior)."""
    ids = [str(st["id"]) for st in subtasks]
    id_set = set(ids)
    deps: dict[str, set[str]] = {
        str(st["id"]): {d for d in (st.get("depends_on") or []) if d in id_set and d != st["id"]}
        for st in subtasks
    }
    waves: list[list[str]] = []
    resolved: set[str] = set()
    while len(resolved) < len(ids):
        wave = [sid for sid in ids if sid not in resolved and deps[sid] <= resolved]
        if not wave:
            remaining = [s for s in ids if s not in resolved]
            raise DependencyCycleError(f"dependency cycle among: {remaining}")
        waves.append(wave)
        resolved.update(wave)
    return waves
