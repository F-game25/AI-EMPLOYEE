"""Auto-generated agent implementation.

Email Ninja — processes specialized tasks in the sales domain.
"""
from __future__ import annotations

from agents.base import BaseAgent

class EmailNinjaAgent(BaseAgent):
    agent_id = "email-ninja"
    required_fields = ("task",)

    def execute(self, payload: dict) -> dict:
        task = payload.get("task", "")
        prompt = f"Process this task: {task}"
        data, tokens = self._ask_json(
            prompt=prompt,
            system=f"You are the Email Ninja agent. Provide structured JSON output for {payload.get('type', 'general')} tasks."
        )
        data["tokens_used"] = tokens
        return data
