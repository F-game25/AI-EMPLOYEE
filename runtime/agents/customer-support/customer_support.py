"""Customer Support Agent — support ticket triage and response drafting.

Classifies incoming support issues, drafts empathetic reply templates,
assigns priority levels, and flags escalations.

Commands (via chat):
  support triage  <issue>    — classify and draft reply for an issue
  support reply   <ticket>   — generate a reply for a specific ticket
  support escalate <ticket>  — generate escalation summary
  support faq     <topic>    — generate FAQ answer for topic
  support status             — list open tickets and priority distribution
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from agents.base import BaseAgent

AI_HOME = Path(os.environ.get("AI_HOME", str(Path.home() / ".ai-employee")))
TICKETS_FILE = AI_HOME / "state" / "support-tickets.json"

SYSTEM = """You are a Customer Support Specialist. You triage support issues with empathy and clarity.

Output JSON with this structure:
{
  "category": "refund|billing|bug|onboarding|feature_request|shipping|account|other",
  "priority": "critical|high|medium|low",
  "sentiment": "frustrated|neutral|positive",
  "escalate": true|false,
  "escalation_reason": "...",
  "draft_reply": "Complete ready-to-send reply text (empathetic, clear, with next steps)",
  "internal_note": "Brief note for the support team",
  "estimated_resolution_time": "e.g. 24 hours",
  "related_faq": "relevant FAQ topic if applicable"
}

Rules:
- Always acknowledge the customer's frustration before explaining
- Never promise what you can't deliver
- Escalate if: legal threat, media mention, payment dispute > $500, data breach concern
- Keep replies under 150 words unless complexity requires more"""


class CustomerSupportAgent(BaseAgent):
    agent_id = "customer-support"
    required_fields = ("task",)

    def execute(self, payload: dict) -> dict:
        issue = payload.get("issue") or payload.get("task", "")
        customer = payload.get("customer", "Customer")
        context = payload.get("context", "")

        prompt = (
            f"Triage this support issue and draft a reply.\n"
            f"Customer: {customer}\n"
            f"Issue: {issue}\n"
            f"Additional context: {context}"
        )
        data, tokens = self._ask_json(prompt=prompt, system=SYSTEM)

        if isinstance(data, dict):
            ticket = {
                "id": f"ticket-{int(datetime.now(timezone.utc).timestamp())}",
                "customer": customer,
                "issue": issue[:200],
                "category": data.get("category", "other"),
                "priority": data.get("priority", "medium"),
                "status": "open",
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            self._save_ticket(ticket)

        data["tokens_used"] = tokens
        return data

    def _save_ticket(self, ticket: dict) -> None:
        tickets = []
        if TICKETS_FILE.exists():
            try:
                tickets = json.loads(TICKETS_FILE.read_text())
            except Exception:
                pass
        tickets.append(ticket)
        TICKETS_FILE.parent.mkdir(parents=True, exist_ok=True)
        TICKETS_FILE.write_text(json.dumps(tickets[-500:], indent=2))
