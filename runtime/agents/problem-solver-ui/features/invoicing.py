"""Financial Overview & Invoicing — invoices, expenses, P&L report."""
import json
import time
import uuid
from pathlib import Path
from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/api/finance", tags=["finance"])

_HOME = Path.home() / ".ai-employee" / "state"
_HOME.mkdir(parents=True, exist_ok=True)
_FILE = _HOME / "finance.json"


def _load() -> dict:
    if _FILE.exists():
        try:
            return json.loads(_FILE.read_text())
        except Exception:
            pass
    return {"invoices": [], "expenses": []}


def _save(data: dict) -> None:
    _FILE.write_text(json.dumps(data, indent=2))


@router.get("/invoices")
def list_invoices():
    return JSONResponse(_load()["invoices"])


@router.post("/invoices")
async def create_invoice(payload: dict):
    data = _load()
    inv_num = f"INV-{len(data['invoices']) + 1001}"
    subtotal = float(payload.get("subtotal", 0))
    tax_rate = float(payload.get("tax_rate", 0))
    tax_amount = round(subtotal * tax_rate / 100, 2)
    total = round(subtotal + tax_amount, 2)
    invoice = {
        "id": str(uuid.uuid4())[:8],
        "number": inv_num,
        "client": payload.get("client", ""),
        "client_email": payload.get("client_email", ""),
        "items": payload.get("items", []),
        "subtotal": subtotal,
        "tax_rate": tax_rate,
        "tax_amount": tax_amount,
        "total": total,
        "currency": payload.get("currency", "USD"),
        "status": "draft",
        "due_date": payload.get("due_date", ""),
        "notes": payload.get("notes", ""),
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "paid_at": "",
    }
    data["invoices"].append(invoice)
    _save(data)
    return JSONResponse(invoice)


@router.patch("/invoices/{inv_id}")
async def update_invoice(inv_id: str, payload: dict):
    data = _load()
    for inv in data["invoices"]:
        if inv["id"] == inv_id:
            inv.update({k: v for k, v in payload.items() if k != "id"})
            _save(data)
            return JSONResponse(inv)
    return JSONResponse({"error": "not found"}, status_code=404)


@router.post("/invoices/{inv_id}/send")
async def send_invoice(inv_id: str):
    data = _load()
    for inv in data["invoices"]:
        if inv["id"] == inv_id:
            inv["status"] = "sent"
            inv["sent_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            _save(data)
            return JSONResponse({"ok": True, "number": inv["number"]})
    return JSONResponse({"error": "not found"}, status_code=404)


@router.post("/invoices/{inv_id}/mark-paid")
async def mark_paid(inv_id: str):
    data = _load()
    for inv in data["invoices"]:
        if inv["id"] == inv_id:
            inv["status"] = "paid"
            inv["paid_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            _save(data)
            return JSONResponse({"ok": True})
    return JSONResponse({"error": "not found"}, status_code=404)


@router.delete("/invoices/{inv_id}")
async def delete_invoice(inv_id: str):
    data = _load()
    data["invoices"] = [i for i in data["invoices"] if i["id"] != inv_id]
    _save(data)
    return JSONResponse({"ok": True})


@router.get("/expenses")
def list_expenses():
    return JSONResponse(_load()["expenses"])


@router.post("/expenses")
async def create_expense(payload: dict):
    data = _load()
    expense = {
        "id": str(uuid.uuid4())[:8],
        "description": payload.get("description", ""),
        "amount": float(payload.get("amount", 0)),
        "currency": payload.get("currency", "USD"),
        "category": payload.get("category", "other"),
        "date": payload.get("date", time.strftime("%Y-%m-%d")),
        "receipt_url": payload.get("receipt_url", ""),
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    data["expenses"].append(expense)
    _save(data)
    return JSONResponse(expense)


@router.delete("/expenses/{exp_id}")
async def delete_expense(exp_id: str):
    data = _load()
    data["expenses"] = [e for e in data["expenses"] if e["id"] != exp_id]
    _save(data)
    return JSONResponse({"ok": True})


@router.get("/pl-report")
def pl_report():
    data = _load()
    invoices = data["invoices"]
    expenses = data["expenses"]
    revenue = sum(inv.get("total", 0) for inv in invoices if inv.get("status") == "paid")
    pending = sum(
        inv.get("total", 0) for inv in invoices if inv.get("status") in ("sent", "draft")
    )
    total_expenses = sum(e.get("amount", 0) for e in expenses)
    by_category: dict[str, float] = {}
    for e in expenses:
        cat = e.get("category", "other")
        by_category[cat] = by_category.get(cat, 0) + e.get("amount", 0)
    return JSONResponse({
        "revenue": revenue,
        "pending_revenue": pending,
        "total_expenses": total_expenses,
        "gross_profit": revenue - total_expenses,
        "profit_margin": round((revenue - total_expenses) / max(revenue, 1) * 100, 1),
        "total_invoices": len(invoices),
        "paid_invoices": len([i for i in invoices if i.get("status") == "paid"]),
        "overdue_invoices": len([i for i in invoices if i.get("status") == "sent"]),
        "expenses_by_category": by_category,
    })
