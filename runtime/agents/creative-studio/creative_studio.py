"""Auto-generated agent implementation.

Creative Studio — processes specialized tasks in the content domain.
"""
from __future__ import annotations

from agents.base import BaseAgent

class CreativeStudioAgent(BaseAgent):
    agent_id = "creative-studio"
    required_fields = ("task",)

    def execute(self, payload: dict) -> dict:
        task = payload.get("task", "")
        prompt = f"Process this task: {task}"
        data, tokens = self._ask_json(
            prompt=prompt,
            system=f"You are the Creative Studio agent. Provide structured JSON output for {payload.get('type', 'general')} tasks."
        )
        data["tokens_used"] = tokens
        return data
