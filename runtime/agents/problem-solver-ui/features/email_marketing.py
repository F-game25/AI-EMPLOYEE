"""Email Marketing Automation — campaigns, sequences, open/click tracking."""
import json
import time
import uuid
from pathlib import Path
from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/api/email-mkt", tags=["email-marketing"])

_HOME = Path.home() / ".ai-employee" / "state"
_HOME.mkdir(parents=True, exist_ok=True)
_FILE = _HOME / "email_marketing.json"


def _load() -> dict:
    if _FILE.exists():
        try:
            return json.loads(_FILE.read_text())
        except Exception:
            pass
    return {"campaigns": [], "templates": [], "sequences": [], "events": []}


def _save(data: dict) -> None:
    _FILE.write_text(json.dumps(data, indent=2))


@router.get("/campaigns")
def list_campaigns():
    return JSONResponse(_load()["campaigns"])


@router.post("/campaigns")
async def create_campaign(payload: dict):
    data = _load()
    campaign = {
        "id": str(uuid.uuid4())[:8],
        "name": payload.get("name", "New Campaign"),
        "subject": payload.get("subject", ""),
        "body": payload.get("body", ""),
        "recipients": payload.get("recipients", []),
        "status": "draft",
        "sent": 0,
        "opened": 0,
        "clicked": 0,
        "replied": 0,
        "tags": payload.get("tags", []),
        "scheduled_at": payload.get("scheduled_at", ""),
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    data["campaigns"].append(campaign)
    _save(data)
    return JSONResponse(campaign)


@router.patch("/campaigns/{cid}")
async def update_campaign(cid: str, payload: dict):
    data = _load()
    for c in data["campaigns"]:
        if c["id"] == cid:
            c.update({k: v for k, v in payload.items() if k != "id"})
            _save(data)
            return JSONResponse(c)
    return JSONResponse({"error": "not found"}, status_code=404)


@router.delete("/campaigns/{cid}")
async def delete_campaign(cid: str):
    data = _load()
    data["campaigns"] = [c for c in data["campaigns"] if c["id"] != cid]
    _save(data)
    return JSONResponse({"ok": True})


@router.post("/campaigns/{cid}/send")
async def send_campaign(cid: str):
    data = _load()
    for c in data["campaigns"]:
        if c["id"] == cid:
            c["status"] = "sent"
            c["sent"] = len(c.get("recipients", []))
            c["sent_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            _save(data)
            return JSONResponse({"ok": True, "sent": c["sent"]})
    return JSONResponse({"error": "not found"}, status_code=404)


@router.get("/templates")
def list_templates():
    return JSONResponse(_load()["templates"])


@router.post("/templates")
async def create_template(payload: dict):
    data = _load()
    tmpl = {
        "id": str(uuid.uuid4())[:8],
        "name": payload.get("name", "New Template"),
        "subject": payload.get("subject", ""),
        "body": payload.get("body", ""),
        "category": payload.get("category", "cold"),
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    data["templates"].append(tmpl)
    _save(data)
    return JSONResponse(tmpl)


@router.get("/sequences")
def list_sequences():
    return JSONResponse(_load()["sequences"])


@router.post("/sequences")
async def create_sequence(payload: dict):
    data = _load()
    seq = {
        "id": str(uuid.uuid4())[:8],
        "name": payload.get("name", "New Sequence"),
        "steps": payload.get("steps", []),
        "delay_days": payload.get("delay_days", [1, 3, 7]),
        "active": True,
        "enrolled": 0,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    data["sequences"].append(seq)
    _save(data)
    return JSONResponse(seq)


@router.post("/track/{event_type}/{campaign_id}")
async def track_event(event_type: str, campaign_id: str):
    data = _load()
    event = {
        "id": str(uuid.uuid4())[:8],
        "type": event_type,
        "campaign_id": campaign_id,
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    data["events"].append(event)
    for c in data["campaigns"]:
        if c["id"] == campaign_id:
            if event_type == "open":
                c["opened"] = c.get("opened", 0) + 1
            elif event_type == "click":
                c["clicked"] = c.get("clicked", 0) + 1
            elif event_type == "reply":
                c["replied"] = c.get("replied", 0) + 1
    _save(data)
    return JSONResponse({"ok": True})


@router.get("/stats")
def email_stats():
    data = _load()
    campaigns = data["campaigns"]
    sent = sum(c.get("sent", 0) for c in campaigns)
    opened = sum(c.get("opened", 0) for c in campaigns)
    clicked = sum(c.get("clicked", 0) for c in campaigns)
    return JSONResponse({
        "total_campaigns": len(campaigns),
        "total_sent": sent,
        "total_opened": opened,
        "total_clicked": clicked,
        "open_rate": round(opened / max(sent, 1) * 100, 1),
        "click_rate": round(clicked / max(sent, 1) * 100, 1),
        "active_sequences": len([s for s in data["sequences"] if s.get("active")]),
    })
