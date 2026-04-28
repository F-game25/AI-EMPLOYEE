"""Invoicing Agent — professional invoice generation and tracking.

Generates invoice drafts from deal/project data, tracks payment status,
calculates taxes, and produces accounts receivable summaries.

Commands (via chat):
  invoice create  <client> <items>  — generate invoice draft
  invoice list                      — list all invoices with status
  invoice overdue                   — list overdue invoices
  invoice report                    — AR summary with aging buckets
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path

from agents.base import BaseAgent

AI_HOME = Path(os.environ.get("AI_HOME", str(Path.home() / ".ai-employee")))
INVOICES_FILE = AI_HOME / "state" / "invoices.json"

SYSTEM = """You are a professional Invoicing Specialist. Generate complete, professional invoice drafts.

Output JSON with this structure:
{
  "invoice_number": "INV-YYYYMMDD-XXXX",
  "client_name": "...",
  "issue_date": "YYYY-MM-DD",
  "due_date": "YYYY-MM-DD",
  "line_items": [{"description": "...", "quantity": 1, "unit_price": 0.00, "amount": 0.00}],
  "subtotal": 0.00,
  "tax_rate": 0.0,
  "tax_amount": 0.00,
  "total": 0.00,
  "currency": "USD",
  "payment_terms": "Net 30",
  "payment_instructions": "Bank transfer / PayPal / Stripe link",
  "notes": "Optional thank you or terms note",
  "email_subject": "Invoice [number] from [your company]",
  "email_body": "Professional covering email text"
}"""


class InvoicingAgent(BaseAgent):
    agent_id = "invoicing"
    required_fields = ("task",)

    def execute(self, payload: dict) -> dict:
        client = payload.get("client", payload.get("task", ""))
        items = payload.get("items", [])
        tax_rate = float(payload.get("tax_rate", 0))
        payment_terms = payload.get("payment_terms", "Net 30")
        currency = payload.get("currency", "USD")

        prompt = (
            f"Create a professional invoice.\n"
            f"Client: {client}\n"
            f"Line items: {json.dumps(items) if items else 'Derive from task description'}\n"
            f"Tax rate: {tax_rate}%\n"
            f"Payment terms: {payment_terms}\n"
            f"Currency: {currency}\n"
            f"Task/description: {payload.get('task', '')}"
        )
        data, tokens = self._ask_json(prompt=prompt, system=SYSTEM)

        if isinstance(data, dict) and "invoice_number" not in data:
            ts = datetime.now(timezone.utc)
            data["invoice_number"] = f"INV-{ts.strftime('%Y%m%d')}-{str(uuid.uuid4())[:4].upper()}"

        if isinstance(data, dict):
            data["id"] = str(uuid.uuid4())
            data["status"] = "draft"
            data["created_at"] = datetime.now(timezone.utc).isoformat()
            self._save_invoice(data)

        data["tokens_used"] = tokens
        return data

    def _save_invoice(self, invoice: dict) -> None:
        invoices = []
        if INVOICES_FILE.exists():
            try:
                invoices = json.loads(INVOICES_FILE.read_text())
            except Exception:
                pass
        invoices.append(invoice)
        INVOICES_FILE.parent.mkdir(parents=True, exist_ok=True)
        INVOICES_FILE.write_text(json.dumps(invoices, indent=2))
