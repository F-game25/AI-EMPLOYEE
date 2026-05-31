"""Auto-generated agent implementation.

Master Orchestrator — processes specialized tasks in the coordination domain.
"""
from __future__ import annotations

from agents.base import BaseAgent

class OrchestratorAgent(BaseAgent):
    agent_id = "orchestrator"
    required_fields = ("task",)

    def execute(self, payload: dict) -> dict:
        task = payload.get("task", "")
        prompt = f"Process this task: {task}"
        data, tokens = self._ask_json(
            prompt=prompt,
            system=f"You are the Master Orchestrator agent. Provide structured JSON output for {payload.get('type', 'general')} tasks."
        )
        data["tokens_used"] = tokens
        return data
