"""Customer Support Agent — helpdesk, knowledge base, AI reply suggestions."""
import json
import sys
import time
import uuid
from pathlib import Path
from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/api/support", tags=["support"])

_HOME = Path.home() / ".ai-employee" / "state"
_HOME.mkdir(parents=True, exist_ok=True)
_FILE = _HOME / "support.json"
_AI_ROUTER_DIR = str(Path(__file__).parent.parent.parent / "ai-router")

TICKET_STATUSES = ["open", "in_progress", "waiting", "resolved", "closed"]
PRIORITIES = ["low", "medium", "high", "urgent"]
CATEGORIES = ["billing", "technical", "general", "feature_request", "bug", "other"]


def _load() -> dict:
    if _FILE.exists():
        try:
            return json.loads(_FILE.read_text())
        except Exception:
            pass
    return {"tickets": [], "kb_articles": []}


def _save(data: dict) -> None:
    _FILE.write_text(json.dumps(data, indent=2))


@router.get("/tickets")
def list_tickets(status: str = None):
    data = _load()
    tickets = data["tickets"]
    if status:
        tickets = [t for t in tickets if t.get("status") == status]
    return JSONResponse(tickets)


@router.post("/tickets")
async def create_ticket(payload: dict):
    data = _load()
    ticket_num = f"SUP-{len(data['tickets']) + 1001}"
    ticket = {
        "id": str(uuid.uuid4())[:8],
        "number": ticket_num,
        "subject": payload.get("subject", "Support Request"),
        "description": payload.get("description", ""),
        "customer_email": payload.get("customer_email", ""),
        "customer_name": payload.get("customer_name", ""),
        "status": "open",
        "priority": payload.get("priority", "medium"),
        "category": payload.get("category", "general"),
        "assigned_to": "",
        "messages": [],
        "tags": payload.get("tags", []),
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "resolved_at": "",
    }
    data["tickets"].append(ticket)
    _save(data)
    return JSONResponse(ticket)


@router.patch("/tickets/{tid}")
async def update_ticket(tid: str, payload: dict):
    data = _load()
    for t in data["tickets"]:
        if t["id"] == tid:
            t.update({k: v for k, v in payload.items() if k not in ("id", "number")})
            t["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            if payload.get("status") in ("resolved", "closed") and not t.get("resolved_at"):
                t["resolved_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            _save(data)
            return JSONResponse(t)
    return JSONResponse({"error": "not found"}, status_code=404)


@router.post("/tickets/{tid}/reply")
async def reply_to_ticket(tid: str, payload: dict):
    data = _load()
    for t in data["tickets"]:
        if t["id"] == tid:
            message = {
                "id": str(uuid.uuid4())[:8],
                "content": payload.get("content", ""),
                "author": payload.get("author", "Support Agent"),
                "is_internal": payload.get("is_internal", False),
                "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }
            t.setdefault("messages", []).append(message)
            t["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            if t["status"] == "open":
                t["status"] = "in_progress"
            _save(data)
            return JSONResponse(message)
    return JSONResponse({"error": "not found"}, status_code=404)


@router.post("/tickets/{tid}/ai-suggest")
async def ai_suggest_reply(tid: str):
    data = _load()
    for t in data["tickets"]:
        if t["id"] == tid:
            prompt = (
                f"Write a helpful, professional customer support reply:\n"
                f"Subject: {t['subject']}\n"
                f"Description: {t['description']}\n"
                f"Category: {t.get('category', 'general')}\n\n"
                f"Be concise, empathetic, and solution-focused."
            )
            fallback = (
                "Thank you for contacting support. We've received your request "
                "and will respond within 24 hours."
            )
            try:
                if _AI_ROUTER_DIR not in sys.path:
                    sys.path.insert(0, _AI_ROUTER_DIR)
                from ai_router import query_ai_for_agent  # type: ignore[import]
                result = query_ai_for_agent("customer-support", prompt)
                suggestion = result.get("content", result.get("text", fallback))
            except Exception:
                suggestion = fallback
            return JSONResponse({"suggestion": suggestion})
    return JSONResponse({"error": "not found"}, status_code=404)


@router.get("/kb")
def list_kb_articles():
    return JSONResponse(_load()["kb_articles"])


@router.post("/kb")
async def create_kb_article(payload: dict):
    data = _load()
    article = {
        "id": str(uuid.uuid4())[:8],
        "title": payload.get("title", ""),
        "content": payload.get("content", ""),
        "category": payload.get("category", "general"),
        "tags": payload.get("tags", []),
        "views": 0,
        "helpful_votes": 0,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    data["kb_articles"].append(article)
    _save(data)
    return JSONResponse(article)


@router.get("/stats")
def support_stats():
    data = _load()
    tickets = data["tickets"]
    return JSONResponse({
        "total": len(tickets),
        "open": len([t for t in tickets if t.get("status") == "open"]),
        "in_progress": len([t for t in tickets if t.get("status") == "in_progress"]),
        "resolved": len([t for t in tickets if t.get("status") in ("resolved", "closed")]),
        "by_priority": {p: len([t for t in tickets if t.get("priority") == p]) for p in PRIORITIES},
        "by_category": {c: len([t for t in tickets if t.get("category") == c]) for c in CATEGORIES},
        "kb_articles": len(data["kb_articles"]),
    })
