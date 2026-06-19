"""task_decomposer — split a business goal into 3-8 typed subtasks.

LLM-assisted when engine.api is available; deterministic heuristic fallback otherwise.
Each subtask: {id, description, needed_capability, depends_on[]}.
"""

from __future__ import annotations

import json
import re
from typing import Any

try:  # engine is optional — degrade honestly, never fake.
    from engine.api import generate as _engine_generate  # type: ignore
except Exception:  # pragma: no cover - import guard
    _engine_generate = None

_MIN_SUBTASKS = 3
_MAX_SUBTASKS = 8

# Deterministic business workflow stages → capability hint. Ordered; later stages
# depend on earlier ones. Used for the offline fallback (always available).
_STAGES: list[tuple[str, str, str]] = [
    ("research", "Research the market, audience, and constraints for: {goal}", "research"),
    ("analysis", "Analyze findings and define strategy for: {goal}", "data_analysis"),
    ("planning", "Build an execution plan and milestones for: {goal}", "planning"),
    ("content", "Draft the core content/assets for: {goal}", "content_strategy"),
    ("outreach", "Prepare outreach/distribution for: {goal}", "outreach"),
    ("measurement", "Define metrics and a measurement plan for: {goal}", "kpi_tracking"),
]


def _heuristic(goal: str) -> list[dict[str, Any]]:
    goal = goal.strip() or "the business goal"
    subtasks: list[dict[str, Any]] = []
    prev_id: str | None = None
    for idx, (key, tmpl, cap) in enumerate(_STAGES, start=1):
        sid = f"st{idx}"
        subtasks.append(
            {
                "id": sid,
                "description": tmpl.format(goal=goal),
                "needed_capability": cap,
                "depends_on": [prev_id] if prev_id else [],
            }
        )
        prev_id = sid
    return subtasks


def _parse_llm(raw: str) -> list[dict[str, Any]]:
    match = re.search(r"\[.*\]", raw, re.DOTALL)
    if not match:
        raise ValueError("no JSON array in LLM output")
    data = json.loads(match.group(0))
    if not isinstance(data, list):
        raise ValueError("LLM output is not a list")
    out: list[dict[str, Any]] = []
    valid_ids: set[str] = set()
    for i, item in enumerate(data, start=1):
        if not isinstance(item, dict):
            continue
        sid = str(item.get("id") or f"st{i}")
        valid_ids.add(sid)
        out.append(
            {
                "id": sid,
                "description": str(item.get("description") or "").strip(),
                "needed_capability": str(item.get("needed_capability") or "general").strip(),
                "depends_on": [str(d) for d in (item.get("depends_on") or [])],
            }
        )
    # Drop dangling dependencies the model may have hallucinated.
    for st in out:
        st["depends_on"] = [d for d in st["depends_on"] if d in valid_ids and d != st["id"]]
    return out


def decompose(goal: str) -> list[dict[str, Any]]:
    """Return 3-8 subtasks for `goal`. Always returns a valid list."""
    if _engine_generate is not None:
        try:
            prompt = (
                "Decompose this business goal into 3 to 8 sequential subtasks. "
                "Return ONLY a JSON array; each element: "
                '{"id":"st1","description":"...","needed_capability":"<one capability keyword>",'
                '"depends_on":["st-id",...]}.\n\nGoal: ' + goal
            )
            raw = _engine_generate(
                prompt=prompt,
                system="You are a precise project planner. Output strict JSON only.",
            )
            parsed = [s for s in _parse_llm(raw) if s["description"]]
            if _MIN_SUBTASKS <= len(parsed) <= _MAX_SUBTASKS:
                return parsed
            if len(parsed) > _MAX_SUBTASKS:
                return parsed[:_MAX_SUBTASKS]
            # Too few → fall through to deterministic plan.
        except Exception:
            pass  # honest fallback below — no fabrication
    return _heuristic(goal)
