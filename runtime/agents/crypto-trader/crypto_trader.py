"""Auto-generated agent implementation.

Crypto Trader — processes specialized tasks in the trading domain.
"""
from __future__ import annotations

from agents.base import BaseAgent

class CryptoTraderAgent(BaseAgent):
    agent_id = "crypto-trader"
    required_fields = ("task",)

    def execute(self, payload: dict) -> dict:
        task = payload.get("task", "")
        prompt = f"Process this task: {task}"
        data, tokens = self._ask_json(
            prompt=prompt,
            system=f"You are the Crypto Trader agent. Provide structured JSON output for {payload.get('type', 'general')} tasks."
        )
        data["tokens_used"] = tokens
        return data
