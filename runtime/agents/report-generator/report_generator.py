"""Report Generator Agent — weekly/monthly business report compiler.

Reads system state files and compiles formatted Markdown reports covering
revenue, pipeline, content activity, and agent performance.

Commands (via chat):
  report weekly    — this week's business summary
  report monthly   — month-over-month performance report
  report revenue   — revenue deep-dive with trend analysis
  report pipeline  — sales pipeline health and forecast
  report agents    — agent performance and activity summary
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path

from agents.base import BaseAgent

AI_HOME = Path(os.environ.get("AI_HOME", str(Path.home() / ".ai-employee")))
STATE_DIR = AI_HOME / "state"

SYSTEM = """You are a Business Intelligence Reporter who transforms raw data into clear, actionable executive reports.

Output JSON with this structure:
{
  "report_title": "...",
  "period": "Week of MM/DD – MM/DD | Month of MMMM YYYY",
  "generated_at": "...",
  "executive_summary": "3-5 sentence high-level summary with the most important insight",
  "sections": [
    {
      "title": "Section Name",
      "metrics": [{"name": "...", "value": "...", "change": "+/-X%", "trend": "up|down|flat"}],
      "insights": ["key insight 1", "key insight 2"],
      "charts": [{"type": "bar|line|pie", "title": "...", "data_description": "..."}]
    }
  ],
  "highlights": ["Top win this period", "second highlight"],
  "concerns": ["Area needing attention", "another concern"],
  "next_week_priorities": ["Priority 1", "Priority 2", "Priority 3"],
  "report_markdown": "Full formatted Markdown report ready to share"
}"""


class ReportGeneratorAgent(BaseAgent):
    agent_id = "report-generator"
    required_fields = ("task",)

    def execute(self, payload: dict) -> dict:
        report_type = payload.get("type", payload.get("task", "weekly"))
        state_data = self._collect_state(report_type)

        prompt = (
            f"Generate a {report_type} business report.\n"
            f"Report date: {datetime.now(timezone.utc).strftime('%Y-%m-%d')}\n"
            f"System data: {json.dumps(state_data, indent=2)}"
        )
        data, tokens = self._ask_json(prompt=prompt, system=SYSTEM)
        data["tokens_used"] = tokens
        return data

    def _collect_state(self, report_type: str) -> dict:
        result: dict = {}
        for fname, key in [
            ("lead-generator-crm.json", "leads"),
            ("deals.json", "deals"),
            ("invoices.json", "invoices"),
            ("agent_calls.jsonl", "agent_calls_recent"),
        ]:
            fpath = STATE_DIR / fname
            if not fpath.exists():
                result[key] = [] if not fname.endswith(".jsonl") else 0
                continue
            try:
                if fname.endswith(".jsonl"):
                    lines = fpath.read_text().strip().splitlines()
                    result[key] = len(lines)
                else:
                    data = json.loads(fpath.read_text())
                    result[key] = data[:50] if isinstance(data, list) else data
            except Exception:
                result[key] = []

        # Determine date range for filtering
        days = 7 if "week" in report_type else 30
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        result["period_days"] = days
        result["period_start"] = cutoff
        return result
