"""Auto-generated agent implementation.

Data Analyst — processes specialized tasks in the analytics domain.
May require human approval for sensitive data access.
"""
from __future__ import annotations

from agents.base import BaseAgent
from core.hitl_gate import HITLGate

hitl = HITLGate()

class DataAnalystAgent(BaseAgent):
    agent_id = "data-analyst"
    required_fields = ("task",)

    def execute(self, payload: dict) -> dict:
        task = payload.get("task", "")

        # Require approval for sensitive data analysis
        if any(keyword in task.lower() for keyword in ["export", "download", "dump", "all records", "all users"]):
            approval = hitl.require_approval(
                payload,
                risk_level="medium",
                blocking=True,
                timeout_seconds=3600
            )
            if not approval.get("approved"):
                return {"error": f"Data analysis blocked: {approval.get('reason', 'Human approval required')}"}

        prompt = f"Process this task: {task}"
        data, tokens = self._ask_json(
            prompt=prompt,
            system=f"You are the Data Analyst agent. Provide structured JSON output for {payload.get('type', 'general')} tasks."
        )
        data["tokens_used"] = tokens
        return data
