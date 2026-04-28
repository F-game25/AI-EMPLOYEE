"""Analytics BI Agent — business intelligence dashboard from system state files.

Reads leads, tasks, revenue, and activity data to produce KPI summaries,
trend analysis, anomaly detection, and executive-ready reports.

Commands (via chat):
  bi dashboard    — full KPI dashboard: leads, tasks, revenue, agents
  bi kpis         — core KPIs with period-over-period comparison
  bi revenue      — revenue breakdown and trend
  bi pipeline     — sales pipeline health metrics
  bi report       — full weekly/monthly BI report
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from agents.base import BaseAgent

AI_HOME = Path(os.environ.get("AI_HOME", str(Path.home() / ".ai-employee")))
STATE_DIR = AI_HOME / "state"

SYSTEM = """You are a Business Intelligence Analyst. You receive raw system state data and produce executive-level KPI summaries.

Output JSON with this structure:
{
  "summary": "2-sentence headline of business health",
  "kpis": {"leads_total": 0, "deals_open": 0, "revenue_total": 0, "tasks_completed": 0, "conversion_rate": "0%"},
  "trends": [{"metric": "...", "direction": "up|down|flat", "change": "...", "insight": "..."}],
  "anomalies": [{"metric": "...", "value": "...", "expected": "...", "action": "..."}],
  "top_actions": ["prioritized action 1", "action 2", "action 3"],
  "health_grade": "A|B|C|D",
  "health_reason": "one sentence why"
}"""


class AnalyticsBIAgent(BaseAgent):
    agent_id = "analytics-bi"
    required_fields = ("task",)

    def execute(self, payload: dict) -> dict:
        state_data = self._collect_state()
        report_type = payload.get("type", payload.get("task", "dashboard"))
        prompt = (
            f"Generate a business intelligence {report_type} report. "
            f"System state data:\n{json.dumps(state_data, indent=2)}"
        )
        data, tokens = self._ask_json(prompt=prompt, system=SYSTEM)
        data["report_type"] = report_type
        data["generated_at"] = datetime.now(timezone.utc).isoformat()
        data["tokens_used"] = tokens
        return data

    def _collect_state(self) -> dict:
        result: dict = {"collected_at": datetime.now(timezone.utc).isoformat()}
        for fname, key in [
            ("lead-generator-crm.json", "leads"),
            ("deals.json", "deals"),
            ("tasks.json", "tasks"),
        ]:
            fpath = STATE_DIR / fname
            if fpath.exists():
                try:
                    result[key] = json.loads(fpath.read_text())
                except Exception:
                    result[key] = []
            else:
                result[key] = []

        activity_file = STATE_DIR / "bus.jsonl"
        if activity_file.exists():
            lines = activity_file.read_text().strip().splitlines()[-50:]
            result["recent_activity_count"] = len(lines)
        else:
            result["recent_activity_count"] = 0

        return result
