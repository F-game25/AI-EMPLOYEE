"""Financial Tools — Invoice management, quotes, P&L, and payment reminders.

Comprehensive financial toolset for small business:
  - Invoice creation and management (draft/sent/paid/overdue)
  - Quote creation and conversion to invoices
  - Payment reminders for overdue invoices
  - Simple P&L: revenue from paid invoices, manual expense entries
  - AI-powered invoice and quote generation

Commands (via chat / WhatsApp / Dashboard):
  invoice create <client> <amount>     — create an invoice
  invoice list                         — list all invoices
  invoice send <id>                    — mark invoice as sent
  invoice pay <id>                     — mark invoice as paid
  invoice overdue                      — list overdue invoices
  quote create <client>                — create a quote
  pl summary                           — P&L overview
  expense add <description> <amount>   — add expense entry
  financial status                     — financial overview

State files:
  ~/.ai-employee/state/invoices.json
  ~/.ai-employee/state/expenses.json
"""
import json
import logging
import os
import sys
import uuid
from datetime import datetime, timezone, date, timedelta
from pathlib import Path
from typing import Optional

AI_HOME = Path(os.environ.get("AI_HOME", str(Path.home() / ".ai-employee")))
INVOICES_FILE = AI_HOME / "state" / "invoices.json"
EXPENSES_FILE = AI_HOME / "state" / "expenses.json"

logging.basicConfig(
    level=getattr(logging, os.environ.get("LOG_LEVEL", "WARNING").upper(), logging.WARNING),
    format="%(message)s",
)
logger = logging.getLogger("financial-tools")

_ai_router_path = AI_HOME / "agents" / "ai-router"
if str(_ai_router_path) not in sys.path:
    sys.path.insert(0, str(_ai_router_path))

try:
    from ai_router import query_ai_for_agent as _query_ai_for_agent  # type: ignore
    _AI_AVAILABLE = True
except ImportError:
    _AI_AVAILABLE = False

INVOICE_STATUSES = ["draft", "sent", "paid", "overdue", "cancelled"]

__all__ = [
    "list_invoices",
    "get_invoice",
    "create_invoice",
    "update_invoice",
    "delete_invoice",
    "send_invoice",
    "pay_invoice",
    "list_quotes",
    "create_quote",
    "update_quote",
    "delete_quote",
    "get_pl",
    "list_expenses",
    "add_expense",
    "delete_expense",
    "get_overdue_invoices",
    "check_overdue",
]


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _today_iso() -> str:
    return date.today().isoformat()


def _load_invoices() -> dict:
    if not INVOICES_FILE.exists():
        return {"invoices": [], "quotes": []}
    try:
        return json.loads(INVOICES_FILE.read_text())
    except Exception:
        return {"invoices": [], "quotes": []}


def _save_invoices(data: dict) -> None:
    INVOICES_FILE.parent.mkdir(parents=True, exist_ok=True)
    INVOICES_FILE.write_text(json.dumps(data, indent=2))


def _load_expenses() -> dict:
    if not EXPENSES_FILE.exists():
        return {"expenses": []}
    try:
        return json.loads(EXPENSES_FILE.read_text())
    except Exception:
        return {"expenses": []}


def _save_expenses(data: dict) -> None:
    EXPENSES_FILE.parent.mkdir(parents=True, exist_ok=True)
    EXPENSES_FILE.write_text(json.dumps(data, indent=2))


def _calc_total(items: list) -> float:
    return sum(float(item.get("qty", 1)) * float(item.get("unit_price", 0)) for item in items)


# ─── Invoices ────────────────────────────────────────────────────────────────

def list_invoices(status: Optional[str] = None) -> list:
    """Return all invoices, optionally filtered by status."""
    data = _load_invoices()
    invoices = data.get("invoices", [])
    if status:
        invoices = [i for i in invoices if i.get("status") == status]
    return sorted(invoices, key=lambda x: x.get("created_at", ""), reverse=True)


def get_invoice(invoice_id: str) -> Optional[dict]:
    """Return a single invoice by ID."""
    data = _load_invoices()
    return next((i for i in data["invoices"] if i["id"] == invoice_id), None)


def create_invoice(
    client_name: str,
    client_email: str = "",
    items: Optional[list] = None,
    due_date: Optional[str] = None,
    notes: str = "",
    currency: str = "USD",
    tax_rate: float = 0.0,
) -> dict:
    """Create a new invoice.

    items format: [{"description": "...", "qty": 1, "unit_price": 100.0}]
    """
    items = items or []
    subtotal = _calc_total(items)
    tax = round(subtotal * tax_rate / 100, 2)
    total = round(subtotal + tax, 2)

    invoice_number = f"INV-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{str(uuid.uuid4())[:4].upper()}"
    data = _load_invoices()
    invoice = {
        "id": str(uuid.uuid4()),
        "invoice_number": invoice_number,
        "client_name": client_name,
        "client_email": client_email,
        "items": items,
        "subtotal": subtotal,
        "tax_rate": tax_rate,
        "tax": tax,
        "total": total,
        "currency": currency,
        "notes": notes,
        "status": "draft",
        "due_date": due_date or (date.today() + timedelta(days=30)).isoformat(),
        "sent_at": None,
        "paid_at": None,
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }
    data["invoices"].append(invoice)
    _save_invoices(data)
    logger.info("Invoice created: %s", invoice["invoice_number"])
    return invoice


def update_invoice(invoice_id: str, updates: dict) -> Optional[dict]:
    """Update invoice fields."""
    data = _load_invoices()
    for i, inv in enumerate(data["invoices"]):
        if inv["id"] == invoice_id:
            updates.pop("id", None)
            updates.pop("created_at", None)
            if "items" in updates:
                items = updates["items"]
                subtotal = _calc_total(items)
                tax_rate = updates.get("tax_rate", inv.get("tax_rate", 0))
                tax = round(subtotal * tax_rate / 100, 2)
                updates["subtotal"] = subtotal
                updates["tax"] = tax
                updates["total"] = round(subtotal + tax, 2)
            data["invoices"][i].update(updates)
            data["invoices"][i]["updated_at"] = _now_iso()
            _save_invoices(data)
            return data["invoices"][i]
    return None


def delete_invoice(invoice_id: str) -> bool:
    """Delete an invoice."""
    data = _load_invoices()
    before = len(data["invoices"])
    data["invoices"] = [i for i in data["invoices"] if i["id"] != invoice_id]
    if len(data["invoices"]) < before:
        _save_invoices(data)
        return True
    return False


def send_invoice(invoice_id: str) -> Optional[dict]:
    """Mark an invoice as sent."""
    return update_invoice(invoice_id, {"status": "sent", "sent_at": _now_iso()})


def pay_invoice(invoice_id: str) -> Optional[dict]:
    """Mark an invoice as paid."""
    return update_invoice(invoice_id, {"status": "paid", "paid_at": _now_iso()})


def get_overdue_invoices() -> list:
    """Return all invoices that are past due date but not paid."""
    data = _load_invoices()
    today = _today_iso()
    overdue = []
    for inv in data.get("invoices", []):
        if inv.get("status") in ("sent", "overdue"):
            due = inv.get("due_date", "")
            if due and due < today:
                overdue.append(inv)
    return overdue


def check_overdue() -> list:
    """Mark overdue invoices and return them."""
    data = _load_invoices()
    today = _today_iso()
    marked = []
    for i, inv in enumerate(data["invoices"]):
        if inv.get("status") == "sent":
            due = inv.get("due_date", "")
            if due and due < today:
                data["invoices"][i]["status"] = "overdue"
                data["invoices"][i]["updated_at"] = _now_iso()
                marked.append(data["invoices"][i])
    if marked:
        _save_invoices(data)
    return marked


# ─── Quotes ──────────────────────────────────────────────────────────────────

def list_quotes(status: Optional[str] = None) -> list:
    """Return all quotes."""
    data = _load_invoices()
    quotes = data.get("quotes", [])
    if status:
        quotes = [q for q in quotes if q.get("status") == status]
    return sorted(quotes, key=lambda x: x.get("created_at", ""), reverse=True)


def create_quote(
    client_name: str,
    client_email: str = "",
    items: Optional[list] = None,
    valid_until: Optional[str] = None,
    notes: str = "",
    currency: str = "USD",
) -> dict:
    """Create a new quote."""
    items = items or []
    total = _calc_total(items)
    quote_number = f"QUO-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{str(uuid.uuid4())[:4].upper()}"
    data = _load_invoices()
    quote = {
        "id": str(uuid.uuid4()),
        "quote_number": quote_number,
        "client_name": client_name,
        "client_email": client_email,
        "items": items,
        "total": round(total, 2),
        "currency": currency,
        "notes": notes,
        "status": "draft",
        "valid_until": valid_until or (date.today() + timedelta(days=14)).isoformat(),
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }
    if "quotes" not in data:
        data["quotes"] = []
    data["quotes"].append(quote)
    _save_invoices(data)
    return quote


def update_quote(quote_id: str, updates: dict) -> Optional[dict]:
    """Update quote fields."""
    data = _load_invoices()
    for i, quote in enumerate(data.get("quotes", [])):
        if quote["id"] == quote_id:
            updates.pop("id", None)
            updates.pop("created_at", None)
            data["quotes"][i].update(updates)
            data["quotes"][i]["updated_at"] = _now_iso()
            _save_invoices(data)
            return data["quotes"][i]
    return None


def delete_quote(quote_id: str) -> bool:
    """Delete a quote."""
    data = _load_invoices()
    before = len(data.get("quotes", []))
    data["quotes"] = [q for q in data.get("quotes", []) if q["id"] != quote_id]
    if len(data.get("quotes", [])) < before:
        _save_invoices(data)
        return True
    return False


# ─── P&L ─────────────────────────────────────────────────────────────────────

def get_pl() -> dict:
    """Return a simple P&L overview."""
    data = _load_invoices()
    invoices = data.get("invoices", [])
    exp_data = _load_expenses()
    expenses = exp_data.get("expenses", [])

    revenue = sum(float(i.get("total", 0)) for i in invoices if i.get("status") == "paid")
    pending_revenue = sum(float(i.get("total", 0)) for i in invoices if i.get("status") in ("sent", "overdue"))
    total_expenses = sum(float(e.get("amount", 0)) for e in expenses)
    profit = revenue - total_expenses

    return {
        "revenue": round(revenue, 2),
        "pending_revenue": round(pending_revenue, 2),
        "expenses": round(total_expenses, 2),
        "profit": round(profit, 2),
        "profit_margin": round((profit / revenue * 100) if revenue > 0 else 0, 1),
        "invoice_count": len(invoices),
        "paid_invoices": sum(1 for i in invoices if i.get("status") == "paid"),
        "overdue_invoices": sum(1 for i in invoices if i.get("status") == "overdue"),
        "expense_count": len(expenses),
    }


# ─── Expenses ────────────────────────────────────────────────────────────────

def list_expenses(category: Optional[str] = None) -> list:
    """Return all expense entries."""
    data = _load_expenses()
    expenses = data.get("expenses", [])
    if category:
        expenses = [e for e in expenses if e.get("category") == category]
    return sorted(expenses, key=lambda x: x.get("date", ""), reverse=True)


def add_expense(
    description: str,
    amount: float,
    category: str = "general",
    expense_date: Optional[str] = None,
    notes: str = "",
) -> dict:
    """Add an expense entry."""
    data = _load_expenses()
    expense = {
        "id": str(uuid.uuid4()),
        "description": description,
        "amount": round(float(amount), 2),
        "category": category,
        "date": expense_date or _today_iso(),
        "notes": notes,
        "created_at": _now_iso(),
    }
    data["expenses"].append(expense)
    _save_expenses(data)
    return expense


def delete_expense(expense_id: str) -> bool:
    """Delete an expense entry."""
    data = _load_expenses()
    before = len(data["expenses"])
    data["expenses"] = [e for e in data["expenses"] if e["id"] != expense_id]
    if len(data["expenses"]) < before:
        _save_expenses(data)
        return True
    return False
