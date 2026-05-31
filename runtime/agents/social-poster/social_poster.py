"""Auto-generated agent implementation.

Social Poster — processes specialized tasks in the social domain.
"""
from __future__ import annotations

from agents.base import BaseAgent

class SocialPosterAgent(BaseAgent):
    agent_id = "social-poster"
    required_fields = ("task",)

    def execute(self, payload: dict) -> dict:
        task = payload.get("task", "")
        prompt = f"Process this task: {task}"
        data, tokens = self._ask_json(
            prompt=prompt,
            system=f"You are the Social Poster agent. Provide structured JSON output for {payload.get('type', 'general')} tasks."
        )
        data["tokens_used"] = tokens
        return data
