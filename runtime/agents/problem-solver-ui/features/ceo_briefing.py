"""Daily CEO Briefing — morning summary with key actions and live business metrics."""
import json
import sys
import time
import uuid
from pathlib import Path
from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/api/briefing", tags=["briefing"])

_HOME = Path.home() / ".ai-employee" / "state"
_HOME.mkdir(parents=True, exist_ok=True)
_FILE = _HOME / "briefings.json"
_AI_ROUTER_DIR = str(Path(__file__).parent.parent.parent / "ai-router")


def _load() -> dict:
    if _FILE.exists():
        try:
            return json.loads(_FILE.read_text())
        except Exception:
            pass
    return {"briefings": [], "settings": {"auto_generate": True, "time": "08:00"}}


def _save(data: dict) -> None:
    _FILE.write_text(json.dumps(data, indent=2))


def _read_state(fname: str) -> dict:
    p = _HOME / fname
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception:
            pass
    return {}


@router.get("/latest")
def get_latest():
    data = _load()
    if data["briefings"]:
        return JSONResponse(data["briefings"][-1])
    return JSONResponse({"message": "No briefing yet. Click Generate to create one."})


@router.get("/history")
def get_history():
    return JSONResponse(_load()["briefings"][-30:])


@router.post("/generate")
async def generate_briefing():
    crm = _read_state("crm.json")
    email = _read_state("email_marketing.json")
    social = _read_state("social_media.json")
    meetings = _read_state("meetings.json")

    leads = crm.get("leads", [])
    today = time.strftime("%Y-%m-%d")
    new_leads = len([l for l in leads if l.get("created_at", "")[:10] == today])
    won_deals = len([l for l in leads if l.get("stage") == "won"])
    pipeline_value = sum(
        l.get("value", 0) for l in leads if l.get("stage") not in ("won", "lost")
    )
    campaigns = email.get("campaigns", [])
    posts = social.get("posts", [])
    meeting_list = meetings.get("meetings", [])

    today_label = time.strftime("%A, %B %d, %Y")
    prompt = (
        f"Generate a concise CEO morning briefing for {today_label}.\n"
        f"Data: {new_leads} new leads today, {won_deals} won deals total, "
        f"${pipeline_value:,} in pipeline, {len(campaigns)} email campaigns, "
        f"{len(posts)} social posts, {len(meeting_list)} meetings.\n\n"
        f"Format sections: 1) Yesterday's Wins 2) Today's Priorities "
        f"3) Key Metrics 4) Action Items"
    )
    fallback = (
        f"Good morning! Briefing for {today_label}.\n\n"
        f"📊 Key Metrics:\n"
        f"• Pipeline: ${pipeline_value:,} | New Leads: {new_leads} | Won: {won_deals}\n\n"
        f"🎯 Today's Priorities:\n"
        f"• Review pipeline and follow up on hot leads\n"
        f"• Check email campaign performance\n"
        f"• Review scheduled social posts\n\n"
        f"✅ Action Items:\n"
        f"• Update CRM with latest interactions\n"
        f"• Respond to urgent emails\n"
        f"• Approve pending workflows"
    )
    try:
        if _AI_ROUTER_DIR not in sys.path:
            sys.path.insert(0, _AI_ROUTER_DIR)
        from ai_router import query_ai_for_agent  # type: ignore[import]
        result = query_ai_for_agent("ceo-briefing", prompt)
        content = result.get("content", result.get("text", fallback))
    except Exception:
        content = fallback

    briefing = {
        "id": str(uuid.uuid4())[:8],
        "date": today,
        "content": content,
        "metrics": {
            "new_leads": new_leads,
            "won_deals": won_deals,
            "pipeline_value": pipeline_value,
        },
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    data = _load()
    data["briefings"].append(briefing)
    data["briefings"] = data["briefings"][-90:]
    _save(data)
    return JSONResponse(briefing)


@router.get("/settings")
def get_settings():
    return JSONResponse(_load()["settings"])


@router.post("/settings")
async def update_settings(payload: dict):
    data = _load()
    data["settings"].update(payload)
    _save(data)
    return JSONResponse(data["settings"])
