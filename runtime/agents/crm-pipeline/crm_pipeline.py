"""CRM Pipeline Agent — deal pipeline management.

Tracks deals through stages, flags stale deals, sends follow-up reminders,
and calculates pipeline conversion rates and expected revenue.

Commands (via chat):
  crm view       — view all deals by stage
  crm advance    — advance a deal to next stage
  crm stale      — list deals with no activity > 7 days
  crm forecast   — expected revenue from open pipeline
  crm stats      — conversion rates and pipeline summary
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path

from agents.base import BaseAgent

AI_HOME = Path(os.environ.get("AI_HOME", str(Path.home() / ".ai-employee")))
DEALS_FILE = AI_HOME / "state" / "deals.json"

STAGES = ["new_lead", "qualified", "proposal_sent", "negotiation", "closed_won", "closed_lost"]

SYSTEM = """You are a CRM Pipeline Manager. Analyze deal pipeline data and return actionable insights as JSON.

Output JSON with this structure:
{
  "pipeline_summary": {"total_deals": 0, "open_deals": 0, "closed_won": 0, "closed_lost": 0},
  "stage_breakdown": {"stage_name": {"count": 0, "total_value": 0}},
  "stale_deals": [{"id": "...", "company": "...", "days_inactive": 0, "recommended_action": "..."}],
  "conversion_rate": "0%",
  "expected_revenue": 0,
  "top_opportunities": [{"id": "...", "company": "...", "value": 0, "next_step": "..."}],
  "recommendations": ["action 1", "action 2"]
}"""


class CRMPipelineAgent(BaseAgent):
    agent_id = "crm-pipeline"
    required_fields = ("task",)

    def execute(self, payload: dict) -> dict:
        deals = self._load_deals()
        task = payload.get("task", "view")
        stale_threshold = int(payload.get("stale_days", 7))

        now = datetime.now(timezone.utc)
        stale = []
        for d in deals:
            updated = d.get("updated_at") or d.get("created_at", "")
            if updated:
                try:
                    dt = datetime.fromisoformat(updated.replace("Z", "+00:00"))
                    days = (now - dt).days
                    if days >= stale_threshold and d.get("stage") not in ("closed_won", "closed_lost"):
                        stale.append({**d, "_days_inactive": days})
                except Exception:
                    pass

        prompt = (
            f"Task: {task}\n"
            f"Deals ({len(deals)} total, {len(stale)} stale):\n"
            f"{json.dumps({'deals': deals[:30], 'stale_deals': stale}, indent=2)}"
        )
        data, tokens = self._ask_json(prompt=prompt, system=SYSTEM)
        data["tokens_used"] = tokens
        return data

    def _load_deals(self) -> list:
        if not DEALS_FILE.exists():
            return []
        try:
            return json.loads(DEALS_FILE.read_text())
        except Exception:
            return []
