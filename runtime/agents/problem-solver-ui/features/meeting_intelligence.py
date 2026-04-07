"""Meeting Intelligence — transcript analysis, summary, action items, follow-ups."""
import json
import sys
import time
import uuid
from pathlib import Path
from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/api/meetings", tags=["meetings"])

_HOME = Path.home() / ".ai-employee" / "state"
_HOME.mkdir(parents=True, exist_ok=True)
_FILE = _HOME / "meetings.json"
_AI_ROUTER_DIR = str(Path(__file__).parent.parent.parent / "ai-router")


def _load() -> dict:
    if _FILE.exists():
        try:
            return json.loads(_FILE.read_text())
        except Exception:
            pass
    return {"meetings": []}


def _save(data: dict) -> None:
    _FILE.write_text(json.dumps(data, indent=2))


def _query_ai(prompt: str, fallback: str) -> str:
    try:
        if _AI_ROUTER_DIR not in sys.path:
            sys.path.insert(0, _AI_ROUTER_DIR)
        from ai_router import query_ai_for_agent  # type: ignore[import]
        result = query_ai_for_agent("meeting-intelligence", prompt)
        return result.get("content", result.get("text", fallback))
    except Exception:
        return fallback


@router.get("/")
def list_meetings():
    return JSONResponse(_load()["meetings"])


@router.post("/")
async def create_meeting(payload: dict):
    data = _load()
    meeting = {
        "id": str(uuid.uuid4())[:8],
        "title": payload.get("title", "Untitled Meeting"),
        "platform": payload.get("platform", "zoom"),
        "date": payload.get("date", time.strftime("%Y-%m-%d")),
        "participants": payload.get("participants", []),
        "transcript": payload.get("transcript", ""),
        "summary": "",
        "action_items": [],
        "follow_up_email": "",
        "status": "pending",
        "duration_mins": payload.get("duration_mins", 0),
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    data["meetings"].append(meeting)
    _save(data)
    return JSONResponse(meeting)


@router.post("/{mid}/analyze")
async def analyze_meeting(mid: str, payload: dict):
    data = _load()
    for m in data["meetings"]:
        if m["id"] == mid:
            transcript = payload.get("transcript", m.get("transcript", ""))
            m["transcript"] = transcript
            prompt = (
                f"Analyze this meeting transcript and provide:\n"
                f"1. A concise 3-sentence summary\n"
                f"2. Action items (bullet list)\n"
                f"3. A follow-up email draft\n\n"
                f"Transcript:\n{transcript[:3000]}"
            )
            fallback = (
                "Summary: Meeting covered key agenda items.\n\n"
                "Action Items:\n- Review meeting notes\n- Send follow-up\n\n"
                "Follow-up Email:\nHi team,\n\nThank you for the meeting. "
                "Please find the action items below.\n\nBest regards"
            )
            content = _query_ai(prompt, fallback)
            m["summary"] = content[:500]
            m["action_items"] = [
                line.lstrip("- ").strip()
                for line in content.split("\n")
                if line.strip().startswith("-")
            ][:10]
            m["follow_up_email"] = content
            m["status"] = "analyzed"
            m["analyzed_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            _save(data)
            return JSONResponse(m)
    return JSONResponse({"error": "not found"}, status_code=404)


@router.patch("/{mid}")
async def update_meeting(mid: str, payload: dict):
    data = _load()
    for m in data["meetings"]:
        if m["id"] == mid:
            m.update({k: v for k, v in payload.items() if k != "id"})
            _save(data)
            return JSONResponse(m)
    return JSONResponse({"error": "not found"}, status_code=404)


@router.delete("/{mid}")
async def delete_meeting(mid: str):
    data = _load()
    data["meetings"] = [m for m in data["meetings"] if m["id"] != mid]
    _save(data)
    return JSONResponse({"ok": True})


@router.get("/stats")
def meeting_stats():
    data = _load()
    meetings = data["meetings"]
    return JSONResponse({
        "total": len(meetings),
        "analyzed": len([m for m in meetings if m.get("status") == "analyzed"]),
        "pending": len([m for m in meetings if m.get("status") == "pending"]),
        "total_duration_mins": sum(m.get("duration_mins", 0) for m in meetings),
    })
