"""Customer Journey Mapper Agent — full buyer journey mapping.

Maps awareness→consideration→decision touchpoints, emotional states,
channel mix, friction points, and prioritized improvement recommendations.

Commands (via chat):
  journey map         <product>    — full customer journey map
  journey friction    <product>    — friction point analysis
  journey touchpoints <product>    — all touchpoints by stage
  journey improve     <stage>      — improvement recommendations for a stage
  journey report      <product>    — complete CX journey report
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from agents.base import BaseAgent

AI_HOME = Path(os.environ.get("AI_HOME", str(Path.home() / ".ai-employee")))

SYSTEM = """You are a Customer Experience Strategist who specializes in mapping and optimizing buyer journeys. You combine empathy with data.

Output JSON with this structure:
{
  "journey_name": "...",
  "persona": {"name": "...", "role": "...", "goal": "...", "pain": "..."},
  "stages": [
    {
      "stage": "Awareness|Consideration|Decision|Retention|Advocacy",
      "customer_goal": "What the customer is trying to do",
      "emotions": ["curious", "frustrated", "hopeful"],
      "touchpoints": [
        {
          "channel": "Google|LinkedIn|Email|Website|Sales call|etc",
          "action": "What the customer does",
          "content_needed": "What content/experience to provide",
          "friction_score": 0,
          "friction_issues": ["issue 1"]
        }
      ],
      "moments_of_truth": ["Critical decision moment"],
      "kpis": ["Metric to measure this stage"]
    }
  ],
  "friction_summary": [{"stage": "...", "issue": "...", "impact": "high|medium|low", "fix": "...", "effort": "low|medium|high"}],
  "conversion_opportunities": [{"where": "...", "what": "...", "expected_lift": "..."}],
  "quick_wins": ["immediate action 1", "action 2"],
  "full_funnel_health": "A|B|C|D",
  "priority_fixes": ["#1 fix", "#2 fix", "#3 fix"]
}"""


class CustomerJourneyMapperAgent(BaseAgent):
    agent_id = "customer-journey-mapper"
    required_fields = ("task",)

    def execute(self, payload: dict) -> dict:
        product = payload.get("product") or payload.get("task", "")
        persona = payload.get("persona", "")
        industry = payload.get("industry", "")
        current_issues = payload.get("issues", "")
        focus_stage = payload.get("stage", "full journey")

        prompt = (
            f"Map the customer journey for:\n"
            f"Product/Service: {product}\n"
            f"Buyer Persona: {persona or 'define based on product'}\n"
            f"Industry: {industry or 'general'}\n"
            f"Known issues: {current_issues or 'none specified'}\n"
            f"Focus: {focus_stage}"
        )
        data, tokens = self._ask_json(prompt=prompt, system=SYSTEM)
        data["tokens_used"] = tokens
        return data
