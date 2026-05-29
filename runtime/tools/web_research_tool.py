"""web_research — atomic tool wrapping :class:`AutoResearchAgent.research`.

Input::

    {"query": "...", "hop": 0, "task_id": "optional"}

Output::

    {"status", "findings_count", "sources": [...], "hop"}
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from .registry import register_tool

logger = logging.getLogger(__name__)


def _call(input_data: dict[str, Any]) -> dict[str, Any]:
    query = str(input_data.get("query") or "").strip()
    if not query:
        return {"status": "error", "error": "query is required"}
    hop = int(input_data.get("hop", 0))
    task_id = str(input_data.get("task_id") or "tool-web-research")
    try:
        from core.auto_research_agent import get_auto_researcher
        researcher = get_auto_researcher()
        result = asyncio.run(researcher.research(gaps=[query], goal=query, hop=hop, task_id=task_id))
        return {"status": "success", **result}
    except Exception as e:
        logger.warning("web_research tool failed: %s", e)
        return {"status": "error", "error": str(e)}


register_tool(
    name="web_research",
    description="Run an autonomous web-research round on a query; persists findings to all memory layers.",
    call=_call,
    input_schema={
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "hop": {"type": "integer", "minimum": 0, "maximum": 5},
            "task_id": {"type": "string"},
        },
        "required": ["query"],
    },
    output_schema={
        "type": "object",
        "properties": {
            "status": {"type": "string"},
            "findings_count": {"type": "integer"},
            "sources": {"type": "array", "items": {"type": "string"}},
            "hop": {"type": "integer"},
        },
    },
    tags=["research", "web", "memory"],
)
