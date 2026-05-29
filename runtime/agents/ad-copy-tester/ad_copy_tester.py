"""Ad Copy Tester Agent — A/B test ad copy generation and scoring.

Generates 3–5 variants per angle for Facebook/Google/LinkedIn ads,
scores each by estimated CTR-likelihood, and outputs split test plans.

Commands (via chat):
  adtest variants  <product>    — generate 5 ad copy variants
  adtest score     <ad_copy>    — score existing copy on CTR-likelihood
  adtest plan      <campaign>   — full A/B test plan
  adtest headlines <product>    — 10 headline variants to test
  adtest angles    <product>    — identify 5 different angles to test
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from agents.base import BaseAgent

AI_HOME = Path(os.environ.get("AI_HOME", str(Path.home() / ".ai-employee")))

SYSTEM = """You are a Performance Marketing Expert who has managed $50M+ in ad spend. You know what copy converts.

Output JSON with this structure:
{
  "platform": "facebook|google|linkedin|tiktok",
  "campaign_objective": "...",
  "variants": [
    {
      "variant_id": "A",
      "angle": "Pain point|Social proof|Curiosity|Urgency|Benefit",
      "headline": "Primary headline (30 chars for Google, 40 for Meta)",
      "primary_text": "Ad body text (125 chars before fold for Meta)",
      "description": "Supporting text",
      "cta": "Button text",
      "ctr_score": 0,
      "estimated_ctr": "0.0%",
      "hook_strength": "weak|moderate|strong|very strong",
      "why_it_works": "Psychological principle being used"
    }
  ],
  "test_structure": {
    "hypothesis": "...",
    "primary_metric": "CTR|CPC|ROAS|Conv Rate",
    "sample_size_per_variant": 0,
    "test_duration_days": 7,
    "winner_criteria": "..."
  },
  "top_recommendation": "Which variant to prioritize and why",
  "angles_not_tested": ["angle to explore next"]
}"""


class AdCopyTesterAgent(BaseAgent):
    agent_id = "ad-copy-tester"
    required_fields = ("task",)

    def execute(self, payload: dict) -> dict:
        product = payload.get("product") or payload.get("task", "")
        platform = payload.get("platform", "facebook").lower()
        audience = payload.get("audience", "")
        objective = payload.get("objective", "conversions")
        budget = payload.get("budget", "")
        existing_copy = payload.get("existing_copy", "")

        prompt = (
            f"Generate {platform} ad copy variants for:\n"
            f"Product/Offer: {product}\n"
            f"Target Audience: {audience or 'general audience'}\n"
            f"Campaign Objective: {objective}\n"
            f"Daily Budget: {budget or 'not specified'}\n"
            f"Existing copy to beat: {existing_copy or 'none'}\n"
            f"Generate 5 variants across different psychological angles"
        )
        data, tokens = self._ask_json(prompt=prompt, system=SYSTEM)
        data["tokens_used"] = tokens
        return data
