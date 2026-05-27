from __future__ import annotations

from agents.base import BaseAgent


class IntelAgent(BaseAgent):
    agent_id = "intel_agent"
    required_fields = ("task",)

    def execute(self, payload: dict[str, str]) -> dict:
        prompt = (
            "Research the company/url from task and return JSON exactly as: "
            "{\"strengths\":[...],\"weaknesses\":[...],\"opportunities\":[...],\"summary\":\"...\"}."
            f" Task: {payload['task']}"
        )
        data, tokens = self._ask_json(prompt=prompt, system="You are a competitive intelligence analyst.")
        data.setdefault("strengths", [])
        data.setdefault("weaknesses", [])
        data.setdefault("opportunities", [])
        data.setdefault("summary", "")
        data["tokens_used"] = tokens
        return data
