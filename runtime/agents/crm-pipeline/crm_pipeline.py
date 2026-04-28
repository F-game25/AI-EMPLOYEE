"""CRM Pipeline Agent — manage deal lifecycle and pipeline stages."""
import json
from typing import Any

from base import BaseAgent


class CRMPipelineAgent(BaseAgent):
    """Manage CRM deals: create, advance stages, track pipeline."""

    agent_id = "crm-pipeline"
    required_fields = ("action", "company")

    def execute(self, payload: dict[str, Any]) -> dict[str, Any]:
        action = payload.get("action")

        if action == "list":
            return self._list_deals()
        elif action == "create":
            return self._create_deal(payload)
        elif action == "advance":
            return self._advance_stage(payload)
        elif action == "status":
            return self._pipeline_status()
        else:
            return {"error": f"Unknown action: {action}"}

    def _list_deals(self) -> dict[str, Any]:
        """List all deals for tenant."""
        deals = self._query_db("deals", "stage != 'closed_lost'")
        return {
            "count": len(deals),
            "deals": sorted(deals, key=lambda x: x.get("created_at", ""), reverse=True)[:10]
        }

    def _create_deal(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Create new deal."""
        data = {
            "title": payload.get("title", payload.get("company")),
            "company": payload.get("company"),
            "value": float(payload.get("value", 0)),
            "stage": "new_lead",
            "probability_percent": 0,
            "notes": payload.get("notes", "")
        }

        result = self._save_to_db("deals", data)
        return {
            "status": "created",
            "deal_id": result.get("deal_id"),
            "company": data["company"]
        }

    def _advance_stage(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Advance deal to next stage."""
        deal_id = payload.get("deal_id")
        current_stage = payload.get("current_stage", "new_lead")

        stages = ["new_lead", "qualified", "proposal_sent", "negotiation", "closed_won"]
        if current_stage not in stages:
            return {"error": f"Invalid stage: {current_stage}"}

        idx = stages.index(current_stage)
        next_stage = stages[min(idx + 1, len(stages) - 1)]

        self._update_db("deals", {"stage": next_stage}, "deal_id = %s", (deal_id,))
        return {"status": "advanced", "from": current_stage, "to": next_stage}

    def _pipeline_status(self) -> dict[str, Any]:
        """Get pipeline summary by stage."""
        deals = self._query_db("deals")
        summary = {}

        for deal in deals:
            stage = deal.get("stage", "unknown")
            if stage not in summary:
                summary[stage] = {"count": 0, "total_value": 0}

            summary[stage]["count"] += 1
            summary[stage]["total_value"] += float(deal.get("value", 0))

        return {
            "status": "pipeline_summary",
            "by_stage": summary,
            "total_deals": len(deals)
        }


if __name__ == "__main__":
    agent = CRMPipelineAgent()
    result = agent.run({"action": "status", "company": "Acme Corp"})
    print(result)
