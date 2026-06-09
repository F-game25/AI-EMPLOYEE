"""ReAct Researcher Agent — searches, fetches, and synthesises information."""
from __future__ import annotations

from typing import Any

from agents.base import BaseAgent
from engine.agent.agent_loop import ReActAgent
from tools.registry import get_tool_registry

_SYSTEM_PROMPT = """\
You are a ReAct research agent. You find, fetch, and synthesise information
to answer questions and produce research briefs.

Always output ONLY valid JSON:
{
  "thought": "<reasoning>",
  "action": "<tool_name or 'finish'>",
  "action_input": <dict or final answer string>
}

Workflow:
1. Use web_search or web_fetch to gather sources.
2. Use get_memory to check what's already known.
3. Use llm_infer to summarise or analyse gathered content.
4. Finish with a structured brief: summary, key findings, sources.
"""

_RESEARCHER_TOOLS = {"web_search", "web_fetch", "get_memory", "embed_text", "llm_infer", "read_file"}


class ReactResearcherAgent(BaseAgent):
    agent_id = "react_researcher"
    required_fields = ("task",)

    def execute(self, payload: dict[str, Any]) -> dict[str, Any]:
        task = payload["task"]
        context = {k: v for k, v in payload.items() if k != "task"}

        registry = get_tool_registry()
        filtered = _FilteredRegistry(registry, _RESEARCHER_TOOLS)

        react = ReActAgent(
            tools=filtered,
            llm=self.client,
            max_steps=payload.get("max_steps", 12),
            max_risk=2,
        )
        react._system = _SYSTEM_PROMPT

        result = react.run(task, context=context)
        return {
            "output": result.output,
            "status": result.status,
            "steps": len(result.steps),
            "tokens_used": result.tokens_used,
            "run_id": result.run_id,
        }


class _FilteredRegistry:
    def __init__(self, registry, allowed: set[str]) -> None:
        self._reg = registry
        self._allowed = allowed

    def list_tools(self, max_risk: int = 5):
        return [t for t in self._reg.list_tools(max_risk) if t["name"] in self._allowed]

    def get(self, name: str):
        if name not in self._allowed:
            return None
        return self._reg.get(name)

    def execute(self, name: str, payload: dict, agent_id: str = "system") -> dict:
        if name not in self._allowed:
            return {"ok": False, "error": f"Tool '{name}' not available to this agent"}
        return self._reg.execute(name, payload, agent_id=agent_id)
