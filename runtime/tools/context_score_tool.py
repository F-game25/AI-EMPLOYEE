"""context_score — atomic tool wrapping :class:`ContextSufficiencyEvaluator`.

Input::

    {"goal": "...", "min_score": 0.6}

Output::

    {"status", "score", "sufficient", "gaps", "memory_hits", "graph_hits"}
"""
from __future__ import annotations

import logging
from typing import Any

from .registry import register_tool

logger = logging.getLogger(__name__)


def _call(input_data: dict[str, Any]) -> dict[str, Any]:
    goal = str(input_data.get("goal") or "").strip()
    if not goal:
        return {"status": "error", "error": "goal is required"}
    min_score = input_data.get("min_score")
    try:
        from core.context_evaluator import get_context_evaluator
        evaluator = get_context_evaluator()
        result = evaluator.evaluate(goal, min_score=float(min_score) if min_score is not None else None)
        return {"status": "success", **result}
    except Exception as e:
        logger.warning("context_score tool failed: %s", e)
        return {"status": "error", "error": str(e)}


register_tool(
    name="context_score",
    description="Score whether the system has enough memory to answer a goal at high quality; returns gap queries.",
    call=_call,
    input_schema={
        "type": "object",
        "properties": {
            "goal": {"type": "string"},
            "min_score": {"type": "number"},
        },
        "required": ["goal"],
    },
    output_schema={
        "type": "object",
        "properties": {
            "status": {"type": "string"},
            "score": {"type": "number"},
            "sufficient": {"type": "boolean"},
            "gaps": {"type": "array", "items": {"type": "string"}},
            "memory_hits": {"type": "integer"},
            "graph_hits": {"type": "integer"},
        },
    },
    tags=["research", "context", "memory"],
)
