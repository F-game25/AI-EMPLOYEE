"""Risk Analyst Agent — business and project risk assessment.

Produces SWOT analysis, risk registers with likelihood/impact matrices,
mitigation strategies, and priority action plans.

Commands (via chat):
  risk assess  <project>     — full risk assessment
  risk swot    <company>     — SWOT analysis
  risk register <project>    — risk register with matrix
  risk mitigate <risk>       — mitigation strategy for specific risk
  risk report  <project>     — complete risk report
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from agents.base import BaseAgent

AI_HOME = Path(os.environ.get("AI_HOME", str(Path.home() / ".ai-employee")))

SYSTEM = """You are a Risk Management Expert and Business Strategist who helps organizations identify, quantify, and mitigate risks before they become crises.

Output JSON with this structure:
{
  "subject": "...",
  "risk_summary": "One-paragraph executive summary of risk profile",
  "overall_risk_level": "low|medium|high|critical",
  "swot": {
    "strengths": [{"item": "...", "strategic_value": "..."}],
    "weaknesses": [{"item": "...", "mitigation": "..."}],
    "opportunities": [{"item": "...", "action": "..."}],
    "threats": [{"item": "...", "probability": "low|medium|high", "mitigation": "..."}]
  },
  "risk_register": [
    {
      "risk_id": "R-001",
      "category": "financial|operational|strategic|legal|reputational|technical",
      "description": "...",
      "likelihood": 1,
      "impact": 1,
      "risk_score": 1,
      "risk_level": "low|medium|high|critical",
      "current_controls": "...",
      "mitigation_strategy": "...",
      "owner": "...",
      "timeline": "immediate|30 days|90 days|ongoing"
    }
  ],
  "top_risks": ["Risk 1 (score X/25)", "Risk 2", "Risk 3"],
  "mitigation_roadmap": [
    {"priority": 1, "action": "...", "resource": "...", "timeline": "...", "expected_risk_reduction": "..."}
  ],
  "risk_matrix_summary": "Heat map description: X critical, Y high, Z medium, W low risks",
  "immediate_actions": ["Action required this week"]
}"""


class RiskAnalystAgent(BaseAgent):
    agent_id = "risk-analyst"
    required_fields = ("task",)

    def execute(self, payload: dict) -> dict:
        subject = payload.get("subject") or payload.get("company") or payload.get("task", "")
        context = payload.get("context", "")
        industry = payload.get("industry", "")
        stage = payload.get("stage", "")
        focus = payload.get("focus", "comprehensive")

        prompt = (
            f"Conduct a {focus} risk assessment for:\n"
            f"Subject: {subject}\n"
            f"Industry: {industry or 'general'}\n"
            f"Stage/Size: {stage or 'not specified'}\n"
            f"Context: {context or 'standard business risk assessment'}"
        )
        data, tokens = self._ask_json(prompt=prompt, system=SYSTEM)
        data["tokens_used"] = tokens
        return data
