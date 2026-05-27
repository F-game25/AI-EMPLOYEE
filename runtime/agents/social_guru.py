from __future__ import annotations

from agents.base import BaseAgent


class SocialGuruAgent(BaseAgent):
    agent_id = "social_guru"
    required_fields = ("task",)

    def execute(self, payload: dict) -> dict:
        prompt = (
            "Generate platform specific posts and return JSON with this shape: "
            "{posts:[{platform, copy, hashtags, optimal_posting_time}]}. "
            f"Task: {payload['task']}"
        )
        data, tokens = self._ask_json(prompt=prompt, system="You are a social media strategist.")
        posts = data.get("posts") if isinstance(data, dict) else None
        if not isinstance(posts, list):
            posts = []
        return {"posts": posts, "tokens_used": tokens}
