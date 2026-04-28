"""Auto-generated agent implementation.

Product Scout — processes specialized tasks in the research domain.
"""
from __future__ import annotations

from agents.base import BaseAgent

class ProductScoutAgent(BaseAgent):
    agent_id = "product-scout"
    required_fields = ("task",)

    def execute(self, payload: dict) -> dict:
        task = payload.get("task", "")
        prompt = f"Process this task: {task}"
        data, tokens = self._ask_json(
            prompt=prompt,
            system=f"You are the Product Scout agent. Provide structured JSON output for {payload.get('type', 'general')} tasks."
        )
        data["tokens_used"] = tokens
        return data
