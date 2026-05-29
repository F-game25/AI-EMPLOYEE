"""Contract Drafter Agent — professional legal document generation.

Generates NDAs, SOWs, SLAs, freelance contracts, and partnership agreements
with variable substitution and plain-English summaries.

Commands (via chat):
  contract nda       <parties>         — mutual/one-way NDA
  contract sow       <project>         — Statement of Work
  contract sla       <service>         — Service Level Agreement
  contract freelance <project>         — freelance/contractor agreement
  contract review    <contract_text>   — plain-English summary and risk flags
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from agents.base import BaseAgent

AI_HOME = Path(os.environ.get("AI_HOME", str(Path.home() / ".ai-employee")))
CONTRACTS_FILE = AI_HOME / "state" / "contracts.json"

SYSTEM = """You are a Contract Specialist and business lawyer who drafts clear, professional contracts in plain English. You protect both parties fairly.

Output JSON with this structure:
{
  "contract_type": "NDA|SOW|SLA|Freelance|Partnership|Custom",
  "title": "Full document title",
  "parties": [{"role": "Party A/Client/etc", "placeholder": "[PARTY_A_NAME]"}],
  "effective_date_placeholder": "[EFFECTIVE_DATE]",
  "sections": [
    {
      "section_number": "1",
      "title": "Section Title",
      "content": "Full legal section text with [PLACEHOLDER] for variable fields"
    }
  ],
  "key_terms": {"term": "plain-English definition"},
  "plain_english_summary": "2-3 paragraph plain English summary of what this contract says",
  "risk_flags": [{"clause": "...", "risk": "...", "recommendation": "..."}],
  "variables_to_fill": ["[PLACEHOLDER_1]", "[PLACEHOLDER_2]"],
  "governing_law_placeholder": "[GOVERNING_LAW_JURISDICTION]",
  "disclaimer": "This is a template for informational purposes. Consult a licensed attorney before signing."
}"""


class ContractDrafterAgent(BaseAgent):
    agent_id = "contract-drafter"
    required_fields = ("task",)

    def execute(self, payload: dict) -> dict:
        contract_type = payload.get("type", payload.get("task", "NDA"))
        party_a = payload.get("party_a", "[PARTY_A_NAME]")
        party_b = payload.get("party_b", "[PARTY_B_NAME]")
        description = payload.get("description", "")
        jurisdiction = payload.get("jurisdiction", "[JURISDICTION]")
        duration = payload.get("duration", "1 year")

        prompt = (
            f"Draft a professional {contract_type} contract.\n"
            f"Party A: {party_a}\n"
            f"Party B: {party_b}\n"
            f"Description/Scope: {description}\n"
            f"Jurisdiction: {jurisdiction}\n"
            f"Duration: {duration}\n"
            f"Special requirements: {payload.get('requirements', 'standard terms')}"
        )
        data, tokens = self._ask_json(prompt=prompt, system=SYSTEM)

        if isinstance(data, dict):
            data["id"] = str(uuid.uuid4())[:8]
            data["created_at"] = datetime.now(timezone.utc).isoformat()
            self._save_contract(data)

        data["tokens_used"] = tokens
        return data

    def _save_contract(self, contract: dict) -> None:
        contracts = []
        if CONTRACTS_FILE.exists():
            try:
                contracts = json.loads(CONTRACTS_FILE.read_text())
            except Exception:
                pass
        contracts.append({k: v for k, v in contract.items() if k != "sections"})
        CONTRACTS_FILE.parent.mkdir(parents=True, exist_ok=True)
        CONTRACTS_FILE.write_text(json.dumps(contracts[-100:], indent=2))
