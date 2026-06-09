"""ReAct Planner Agent — decomposes complex goals into subtask plans."""
from __future__ import annotations

from typing import Any

from agents.base import BaseAgent
from engine.agent.agent_loop import ReActAgent
from tools.registry import get_tool_registry

_SYSTEM_PROMPT = """\
You are a ReAct planning agent. You decompose complex goals into concrete,
executable subtasks and determine the correct agent or skill for each.

Always output ONLY valid JSON:
{
  "thought": "<reasoning>",
  "action": "<tool_name or 'finish'>",
  "action_input": <dict or final answer string>
}

When finishing, the answer must be a JSON object:
{
  "plan": [
    {"subtask": "description", "agent": "react_coder|react_researcher|problem-solver", "priority": 1}
  ],
  "summary": "one-line plan summary"
}
"""

_PLANNER_TOOLS = {"llm_infer", "get_memory", "read_file"}


class ReactPlannerAgent(BaseAgent):
    agent_id = "react_planner"
    required_fields = ("task",)

    def execute(self, payload: dict[str, Any]) -> dict[str, Any]:
        task = payload["task"]
        context = {k: v for k, v in payload.items() if k != "task"}

        registry = get_tool_registry()
        filtered = _FilteredRegistry(registry, _PLANNER_TOOLS)

        react = ReActAgent(
            tools=filtered,
            llm=self.client,
            max_steps=8,
            max_risk=0,
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
