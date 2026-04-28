"""Personal Brand Agent — builds complete personal brand assets.

Creates LinkedIn bio/headline/about section, thought leadership content,
brand voice guide, and 30-day content plans.

Commands (via chat):
  brand audit    <name> <role>   — audit current brand and gaps
  brand bio      <name> <role>   — generate short + long bio variants
  brand linkedin <name>          — full LinkedIn profile optimization
  brand content  <name>          — 30-day thought leadership content plan
  brand voice    <name>          — brand voice guide with do/don't examples
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from agents.base import BaseAgent

AI_HOME = Path(os.environ.get("AI_HOME", str(Path.home() / ".ai-employee")))

SYSTEM = """You are a Personal Branding Strategist who has helped hundreds of executives and entrepreneurs build powerful personal brands on LinkedIn and beyond.

Output JSON with this structure:
{
  "brand_summary": "2-sentence positioning statement",
  "linkedin_headline": "Attention-grabbing headline under 220 chars (role + value prop + unique differentiator)",
  "linkedin_about": "Full LinkedIn About section (1500-2000 chars, first-person, story-driven, ends with CTA)",
  "short_bio": "Twitter/speaker bio under 160 chars",
  "long_bio": "Full professional bio 300-400 words (third-person)",
  "brand_voice": {"tone": "...", "avoid": ["..."], "signature_phrases": ["..."]},
  "content_pillars": ["pillar 1", "pillar 2", "pillar 3"],
  "content_plan": [{"week": 1, "theme": "...", "post_ideas": ["..."]}],
  "differentiation": "What makes this person uniquely positioned vs peers",
  "quick_wins": ["immediate action 1", "action 2", "action 3"]
}"""


class PersonalBrandAgent(BaseAgent):
    agent_id = "personal-brand"
    required_fields = ("task",)

    def execute(self, payload: dict) -> dict:
        name = payload.get("name", "")
        role = payload.get("role", payload.get("task", ""))
        niche = payload.get("niche", "")
        audience = payload.get("audience", "")
        achievements = payload.get("achievements", "")
        brand_type = payload.get("type", "full")

        prompt = (
            f"Build a complete personal brand for:\n"
            f"Name: {name}\n"
            f"Role/Title: {role}\n"
            f"Niche/Industry: {niche}\n"
            f"Target Audience: {audience}\n"
            f"Key Achievements: {achievements}\n"
            f"Request type: {brand_type}\n"
            f"Task: {payload.get('task', '')}"
        )
        data, tokens = self._ask_json(prompt=prompt, system=SYSTEM)
        data["tokens_used"] = tokens
        return data
