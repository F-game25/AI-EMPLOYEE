"""Auto-generated agent implementation.

Support Bot — processes specialized tasks in the support domain.
"""
from __future__ import annotations

from agents.base import BaseAgent

class SupportBotAgent(BaseAgent):
    agent_id = "support-bot"
    required_fields = ("task",)

    def execute(self, payload: dict) -> dict:
        task = payload.get("task", "")
        prompt = f"Process this task: {task}"
        data, tokens = self._ask_json(
            prompt=prompt,
            system=f"You are the Support Bot agent. Provide structured JSON output for {payload.get('type', 'general')} tasks."
        )
        data["tokens_used"] = tokens
        return data
