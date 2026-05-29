"""Auto-generated agent implementation.

E-Commerce Dashboard — processes specialized tasks in the ecommerce domain.
"""
from __future__ import annotations

from agents.base import BaseAgent

class EcomDashboardAgent(BaseAgent):
    agent_id = "ecom-dashboard"
    required_fields = ("task",)

    def execute(self, payload: dict) -> dict:
        task = payload.get("task", "")
        prompt = f"Process this task: {task}"
        data, tokens = self._ask_json(
            prompt=prompt,
            system=f"You are the E-Commerce Dashboard agent. Provide structured JSON output for {payload.get('type', 'general')} tasks."
        )
        data["tokens_used"] = tokens
        return data
