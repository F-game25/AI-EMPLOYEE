from __future__ import annotations

from agents.base import BaseAgent


class SupportBotAgent(BaseAgent):
    agent_id = "support_bot"
    required_fields = ("task",)

    def execute(self, payload: dict) -> dict:
        kb = payload.get("knowledge_base", "")
        prompt = (
            "Given the user question and knowledge base, return JSON: "
            "{answer, confidence, escalate_flag}."
            f" Question: {payload['task']}\nKnowledge base: {kb}"
        )
        data, tokens = self._ask_json(prompt=prompt, system="You are a customer support assistant.")
        data.setdefault("answer", data.get("raw", ""))
        data.setdefault("confidence", 0.0)
        data.setdefault("escalate_flag", False)
        data["tokens_used"] = tokens
        return data
