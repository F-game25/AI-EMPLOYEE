from __future__ import annotations

from typing import Any

from agents.base import BaseAgent


class LeadHunterAgent(BaseAgent):
    agent_id = "lead_hunter"
    required_fields = ("task",)

    def execute(self, payload: dict[str, Any]) -> dict[str, Any]:
        prompt = (
            "Extract niche/location from the task and return JSON with this exact shape:\n"
            "{\"leads\":[{\"name\":\"\",\"company\":\"\",\"contact\":\"\",\"relevance_score\":0.0}]}\n"
            f"Task: {payload['task']}"
        )
        data, tokens = self._ask_json(prompt=prompt, system="You are a B2B lead generation specialist.")
        leads = data.get("leads") if isinstance(data, dict) else None
        if not isinstance(leads, list):
            leads = []
        return {"leads": leads, "tokens_used": tokens}
