"""ContextResearchSkill — exposes context-evaluate + auto-research to the planner.

Planner can include this skill as a step in a task graph; when executed it
runs the same loop as :class:`AgentController._run_context_research_loop`
but as a stateless skill so it can be composed by any agent.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable

from skills.base import SkillBase

logger = logging.getLogger(__name__)


class ContextResearchSkill(SkillBase):
    """Score context for a goal and (optionally) research gaps to fill them."""

    name = "context-research"
    description = "Evaluate context sufficiency for a goal and research knowledge gaps."
    version = "1.0"
    capability_tags = ["research", "learning", "memory", "context"]
    input_schema = {
        "type": "object",
        "properties": {
            "goal": {"type": "string"},
            "max_hops": {"type": "integer", "minimum": 0, "maximum": 5},
            "force_research": {"type": "boolean"},
        },
        "required": ["goal"],
    }
    output_schema = {
        "type": "object",
        "properties": {
            "status": {"type": "string"},
            "score": {"type": "number"},
            "sufficient": {"type": "boolean"},
            "gaps": {"type": "array"},
            "hops": {"type": "array"},
            "findings_count": {"type": "integer"},
        },
        "required": ["status"],
    }
    allowed_actions = ["skill_dispatch"]

    def execute(
        self,
        input_data: dict[str, Any],
        action_runner: Callable[[str, dict[str, Any]], dict[str, Any]],
    ) -> dict[str, Any]:
        goal = str(input_data.get("goal") or "").strip()
        if not goal:
            return {"status": "error", "error": "goal is required"}
        max_hops = int(input_data.get("max_hops", 3))
        force = bool(input_data.get("force_research", False))

        try:
            from core.context_evaluator import get_context_evaluator
            from core.auto_research_agent import get_auto_researcher
        except Exception as e:
            return {"status": "error", "error": f"research components unavailable: {e}"}

        evaluator = get_context_evaluator()
        researcher = get_auto_researcher()

        try:
            evaluation = evaluator.evaluate(goal)
        except Exception as e:
            return {"status": "error", "error": f"evaluation failed: {e}"}

        hops: list[dict] = []
        findings_count = 0
        if force or not evaluation.get("sufficient"):
            for hop in range(max_hops):
                try:
                    result = asyncio.run(researcher.research(
                        gaps=evaluation.get("gaps") or [goal],
                        goal=goal, hop=hop, task_id="skill-context-research",
                    ))
                except Exception as e:
                    logger.warning("context-research hop %d failed: %s", hop, e)
                    break
                hops.append(result)
                findings_count += int(result.get("findings_count", 0))
                if result.get("budget_exhausted") or not result.get("findings_count"):
                    break
                try:
                    evaluation = evaluator.evaluate(goal)
                except Exception:
                    break
                if evaluation.get("sufficient"):
                    break

        return {
            "status": "success",
            "score": evaluation.get("score", 0.0),
            "sufficient": evaluation.get("sufficient", False),
            "gaps": evaluation.get("gaps", []),
            "hops": hops,
            "findings_count": findings_count,
            "memory_hits": evaluation.get("memory_hits", 0),
            "graph_hits": evaluation.get("graph_hits", 0),
        }
