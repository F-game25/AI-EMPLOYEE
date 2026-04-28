"""Website Builder Agent — landing page copy and structure generation.

Generates complete, conversion-optimized landing page copy: hero section,
feature blocks, social proof, pricing tables, FAQ, and CTA sections.

Commands (via chat):
  site hero     <product>   — hero section: headline, subhead, CTA
  site features <product>   — 3-6 feature/benefit blocks
  site pricing  <tiers>     — pricing table copy
  site faq      <product>   — 8-10 FAQ questions and answers
  site full     <product>   — complete landing page (all sections)
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from agents.base import BaseAgent

AI_HOME = Path(os.environ.get("AI_HOME", str(Path.home() / ".ai-employee")))

SYSTEM = """You are a world-class conversion copywriter and landing page specialist. Every word earns its place.

Output JSON with this structure:
{
  "page_title": "SEO-optimized page title (60 chars)",
  "meta_description": "Compelling meta description (155 chars)",
  "hero": {
    "headline": "Primary H1 (under 10 words, benefit-driven)",
    "subheadline": "Supporting H2 (one sentence clarifying the headline)",
    "body": "2-3 sentences expanding on the value proposition",
    "cta_primary": "Button text (action verb + benefit)",
    "cta_secondary": "Secondary option (e.g. 'Watch demo')"
  },
  "features": [{"title": "...", "description": "...", "icon_suggestion": "..."}],
  "social_proof": {"testimonial_prompts": ["Ideal testimonial themes"], "stats": ["stat 1", "stat 2"]},
  "pricing": [{"tier": "...", "price": "...", "description": "...", "features": ["..."], "cta": "..."}],
  "faq": [{"question": "...", "answer": "..."}],
  "final_cta": {"headline": "...", "body": "...", "button": "..."},
  "conversion_tips": ["Specific improvement to implement"]
}"""


class WebsiteBuilderAgent(BaseAgent):
    agent_id = "website-builder"
    required_fields = ("task",)

    def execute(self, payload: dict) -> dict:
        product = payload.get("product") or payload.get("task", "")
        audience = payload.get("audience", "")
        pain_point = payload.get("pain_point", "")
        section = payload.get("section", "full")
        tone = payload.get("tone", "professional and approachable")

        prompt = (
            f"Build landing page copy for:\n"
            f"Product/Service: {product}\n"
            f"Target Audience: {audience}\n"
            f"Main Pain Point Solved: {pain_point}\n"
            f"Tone: {tone}\n"
            f"Section requested: {section}"
        )
        data, tokens = self._ask_json(prompt=prompt, system=SYSTEM)
        data["tokens_used"] = tokens
        return data
