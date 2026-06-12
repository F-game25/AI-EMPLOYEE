"""Turn a ready spec into thin vertical slices, one per acceptance criterion.

Hard gate: refuses (status='blocked') any spec whose status is not 'ready' —
planning on an unclarified spec is how scope rot starts.
"""
from __future__ import annotations

import re

_FILE_HINTS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("endpoint", "route", "api", "backend", "server"), "backend/routes/"),
    (("ui", "page", "component", "frontend", "render", "display", "modal"), "frontend/src/components/"),
    (("agent", "agents"), "runtime/agents/"),
    (("skill", "skills"), "runtime/skills/"),
    (("pipeline", "engine", "core", "memory", "orchestrator"), "runtime/core/"),
)


def _normalize(spec: dict) -> tuple[dict, str]:
    """Accept the build_spec envelope or a bare spec body."""
    spec = spec or {}
    if "spec" in spec and "status" in spec:
        return spec["spec"] or {}, str(spec["status"])
    return spec, str(spec.get("status", "ready"))


def build_plan(spec: dict) -> dict:
    """-> {slices: [{id, title, files_hint, depends_on, acceptance_ids}], status}"""
    body, status = _normalize(spec)
    if status != "ready":
        return {"slices": [], "status": "blocked",
                "reason": f"spec status is '{status}', not 'ready' — clarify before planning"}
    criteria = body.get("acceptance_criteria") or []
    if not criteria:
        return {"slices": [], "status": "blocked",
                "reason": "spec has no acceptance criteria — nothing checkable to plan against"}

    slices: list[dict] = []
    for i, c in enumerate(criteria):
        words = set(re.findall(r"[a-z]+", str(c.get("statement", "")).lower()))
        hints = [path for keys, path in _FILE_HINTS if words & set(keys)]
        if c.get("checkable_via") == "test" and "tests/" not in hints:
            hints.append("tests/")
        slices.append({
            "id": f"S{i + 1}",
            "title": str(c.get("statement", ""))[:100],
            "files_hint": hints or ["runtime/"],
            "depends_on": [f"S{i}"] if i else [],
            "acceptance_ids": [c.get("id", f"AC-{i + 1}")],
        })
    return {"slices": slices, "status": "planned"}
