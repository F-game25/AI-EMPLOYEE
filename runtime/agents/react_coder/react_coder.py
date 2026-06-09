"""ReAct Coder Agent — writes, reads, and executes code to fulfil coding tasks."""
from __future__ import annotations

from typing import Any

from agents.base import BaseAgent
from engine.agent.agent_loop import ReActAgent
from tools.registry import get_tool_registry
from core.orchestrator import get_llm_client

_SYSTEM_PROMPT = """\
You are a ReAct coding agent. You solve coding tasks by reading existing code,
writing files, running shell commands, and executing code to verify correctness.

Always output ONLY valid JSON:
{
  "thought": "<reasoning>",
  "action": "<tool_name or 'finish'>",
  "action_input": <dict or final answer string>
}

Workflow:
1. Read relevant files to understand context.
2. Write or modify files to implement the solution.
3. Run shell commands or code to verify the implementation.
4. Finish with a clear summary of what was done and any test results.
"""

_CODER_TOOLS = {"read_file", "write_file", "list_dir", "shell_exec", "code_exec", "llm_infer"}


class ReactCoderAgent(BaseAgent):
    agent_id = "react_coder"
    required_fields = ("task",)

    def execute(self, payload: dict[str, Any]) -> dict[str, Any]:
        task = payload["task"]
        context = {k: v for k, v in payload.items() if k != "task"}

        registry = get_tool_registry()
        # Filtered registry proxy that only exposes coder tools
        filtered = _FilteredRegistry(registry, _CODER_TOOLS)

        react = ReActAgent(
            tools=filtered,
            llm=self.client,
            max_steps=payload.get("max_steps", 20),
            max_risk=2,
        )
        # Override system prompt via a custom reason step
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
    """Wraps ToolRegistry to expose only a named subset of tools."""

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
