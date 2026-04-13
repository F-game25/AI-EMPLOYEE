from __future__ import annotations

from typing import Any

from agents.base import BaseAgent


class ContentMasterAgent(BaseAgent):
    agent_id = "content_master"
    required_fields = ("task",)

    def execute(self, payload: dict[str, Any]) -> dict[str, Any]:
        req = {
            "type": payload.get("type", "post"),
            "topic": payload.get("topic", payload["task"]),
            "tone": payload.get("tone", "professional"),
            "length": payload.get("length", "medium"),
        }
        prompt = (
            "Generate content and return JSON with keys: type, topic, tone, length, content, outline.\n"
            f"Input: {req}"
        )
        data, tokens = self._ask_json(prompt=prompt, system="You are a content strategy expert.")
        if "content" not in data:
            data["content"] = data.get("raw", "")
        data["tokens_used"] = tokens
        return data
