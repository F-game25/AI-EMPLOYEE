from __future__ import annotations

from agents.base import BaseAgent


class EmailNinjaAgent(BaseAgent):
    agent_id = "email_ninja"
    required_fields = ("task",)

    def execute(self, payload: dict) -> dict:
        req = {
            "product": payload.get("product", ""),
            "audience": payload.get("audience", ""),
            "sequence_length": payload.get("sequence_length", 3),
            "task": payload.get("task", ""),
        }
        prompt = (
            "Create a cold email sequence and return JSON with key 'sequence' as an array of "
            "{subject, body, send_day}. Input: "
            f"{req}"
        )
        data, tokens = self._ask_json(prompt=prompt, system="You are an expert SDR email copywriter.")
        seq = data.get("sequence") if isinstance(data, dict) else None
        if not isinstance(seq, list):
            seq = []
        return {"sequence": seq, "tokens_used": tokens}
