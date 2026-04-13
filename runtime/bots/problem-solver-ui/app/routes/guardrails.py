from __future__ import annotations

from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException

from app.schemas import GuardrailDecisionResponse, GuardrailItem
from app.state import store

router = APIRouter(prefix="/guardrails", tags=["guardrails"])


def _items() -> list[dict]:
    data = store.read("guardrails", [])
    if not data:
        seed = [{"id": "gr-1", "reason": "Sample review", "status": "pending", "created_at": datetime.now(timezone.utc).isoformat()}]
        store.write("guardrails", seed)
        return seed
    return data


@router.get("/pending", response_model=list[GuardrailItem])
def pending_guardrails() -> list[GuardrailItem]:
    return [GuardrailItem(id=i["id"], reason=i["reason"], created_at=i["created_at"]) for i in _items() if i.get("status") == "pending"]


@router.post("/{guardrail_id}/approve", response_model=GuardrailDecisionResponse)
def approve_guardrail(guardrail_id: str) -> GuardrailDecisionResponse:
    items = _items()
    for item in items:
        if item.get("id") == guardrail_id:
            item["status"] = "approved"
            store.write("guardrails", items)
            return GuardrailDecisionResponse(id=guardrail_id, status="approved")
    raise HTTPException(status_code=404, detail="Guardrail not found")


@router.post("/{guardrail_id}/reject", response_model=GuardrailDecisionResponse)
def reject_guardrail(guardrail_id: str) -> GuardrailDecisionResponse:
    items = _items()
    for item in items:
        if item.get("id") == guardrail_id:
            item["status"] = "rejected"
            store.write("guardrails", items)
            return GuardrailDecisionResponse(id=guardrail_id, status="rejected")
    raise HTTPException(status_code=404, detail="Guardrail not found")
