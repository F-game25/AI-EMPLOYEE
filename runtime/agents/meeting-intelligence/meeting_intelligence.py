"""Meeting Intelligence Agent — Transcription, AI summarization, and follow-up generation.

Handles the full meeting workflow:
  - Meeting records: title, date, participants, transcript
  - AI-powered summarization: key points, decisions, action items
  - Follow-up email generation addressed to attendees
  - Meeting history and search

Commands (via chat / WhatsApp / Dashboard):
  meeting add <title>               — add a new meeting record
  meeting list                      — list all meetings
  meeting summarize <id>            — AI-summarize a meeting transcript
  meeting followup <id>             — generate follow-up email
  meeting status                    — meetings overview

State files:
  ~/.ai-employee/state/meetings.json
"""
import json
import logging
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

AI_HOME = Path(os.environ.get("AI_HOME", str(Path.home() / ".ai-employee")))
MEETINGS_FILE = AI_HOME / "state" / "meetings.json"

logging.basicConfig(
    level=getattr(logging, os.environ.get("LOG_LEVEL", "WARNING").upper(), logging.WARNING),
    format="%(message)s",
)
logger = logging.getLogger("meeting-intelligence")

_ai_router_path = AI_HOME / "agents" / "ai-router"
if str(_ai_router_path) not in sys.path:
    sys.path.insert(0, str(_ai_router_path))

try:
    from ai_router import query_ai_for_agent as _query_ai_for_agent  # type: ignore
    _AI_AVAILABLE = True
except ImportError:
    _AI_AVAILABLE = False

__all__ = [
    "list_meetings",
    "get_meeting",
    "add_meeting",
    "update_meeting",
    "delete_meeting",
    "summarize_meeting",
    "generate_followup_email",
]


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_meetings() -> dict:
    if not MEETINGS_FILE.exists():
        return {"meetings": []}
    try:
        return json.loads(MEETINGS_FILE.read_text())
    except Exception:
        return {"meetings": []}


def _save_meetings(data: dict) -> None:
    MEETINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    MEETINGS_FILE.write_text(json.dumps(data, indent=2))


def list_meetings(search: Optional[str] = None) -> list:
    """Return all meetings, optionally filtered by search term."""
    data = _load_meetings()
    meetings = data.get("meetings", [])
    if search:
        q = search.lower()
        meetings = [
            m for m in meetings
            if q in m.get("title", "").lower()
            or any(q in p.lower() for p in m.get("participants", []))
        ]
    return sorted(meetings, key=lambda x: x.get("date", ""), reverse=True)


def get_meeting(meeting_id: str) -> Optional[dict]:
    """Return a single meeting by ID."""
    data = _load_meetings()
    return next((m for m in data["meetings"] if m["id"] == meeting_id), None)


def add_meeting(
    title: str,
    date: str = "",
    participants: Optional[list] = None,
    transcript: str = "",
    notes: str = "",
    meeting_type: str = "general",
) -> dict:
    """Create a new meeting record."""
    data = _load_meetings()
    meeting = {
        "id": str(uuid.uuid4()),
        "title": title,
        "date": date or _now_iso(),
        "participants": participants or [],
        "transcript": transcript,
        "notes": notes,
        "meeting_type": meeting_type,
        "summary": "",
        "key_points": [],
        "decisions": [],
        "action_items": [],
        "followup_email": "",
        "summarized_at": None,
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }
    data["meetings"].append(meeting)
    _save_meetings(data)
    logger.info("Meeting added: %s", meeting["id"])
    return meeting


def update_meeting(meeting_id: str, updates: dict) -> Optional[dict]:
    """Update meeting fields."""
    data = _load_meetings()
    for i, meeting in enumerate(data["meetings"]):
        if meeting["id"] == meeting_id:
            updates.pop("id", None)
            updates.pop("created_at", None)
            data["meetings"][i].update(updates)
            data["meetings"][i]["updated_at"] = _now_iso()
            _save_meetings(data)
            return data["meetings"][i]
    return None


def delete_meeting(meeting_id: str) -> bool:
    """Delete a meeting. Returns True if deleted."""
    data = _load_meetings()
    before = len(data["meetings"])
    data["meetings"] = [m for m in data["meetings"] if m["id"] != meeting_id]
    if len(data["meetings"]) < before:
        _save_meetings(data)
        return True
    return False


def summarize_meeting(meeting_id: str) -> Optional[dict]:
    """AI-summarize a meeting transcript into key points, decisions, and action items."""
    meeting = get_meeting(meeting_id)
    if not meeting:
        return None

    transcript = meeting.get("transcript", "").strip()
    if not transcript:
        return update_meeting(meeting_id, {
            "summary": "No transcript provided.",
            "key_points": [],
            "decisions": [],
            "action_items": [],
            "summarized_at": _now_iso(),
        })

    if _AI_AVAILABLE:
        prompt = (
            f"Analyze this meeting transcript and extract structured insights.\n\n"
            f"Meeting: {meeting.get('title', 'Untitled')}\n"
            f"Participants: {', '.join(meeting.get('participants', []))}\n"
            f"Date: {meeting.get('date', '')}\n\n"
            f"Transcript:\n{transcript[:4000]}\n\n"
            f"Respond ONLY with valid JSON:\n"
            f'{{"summary": "2-3 sentence overview", '
            f'"key_points": ["point1", "point2"], '
            f'"decisions": ["decision1"], '
            f'"action_items": [{{"item": "task", "owner": "person", "due": "date"}}]}}'
        )
        try:
            result = _query_ai_for_agent("meeting-intelligence", prompt)
            content = result.get("content", result.get("text", ""))
            start = content.find("{")
            end = content.rfind("}") + 1
            if start >= 0 and end > start:
                parsed = json.loads(content[start:end])
                return update_meeting(meeting_id, {
                    "summary": parsed.get("summary", ""),
                    "key_points": parsed.get("key_points", []),
                    "decisions": parsed.get("decisions", []),
                    "action_items": parsed.get("action_items", []),
                    "summarized_at": _now_iso(),
                })
        except Exception:
            pass

    # Fallback: basic extraction
    lines = [l.strip() for l in transcript.splitlines() if l.strip()]
    summary = f"Meeting '{meeting.get('title')}' with {len(meeting.get('participants', []))} participant(s). {len(lines)} transcript lines."
    return update_meeting(meeting_id, {
        "summary": summary,
        "key_points": lines[:5],
        "decisions": [],
        "action_items": [],
        "summarized_at": _now_iso(),
    })


def generate_followup_email(meeting_id: str) -> Optional[dict]:
    """AI-generate a follow-up email for a meeting."""
    meeting = get_meeting(meeting_id)
    if not meeting:
        return None

    if _AI_AVAILABLE:
        action_items = meeting.get("action_items", [])
        action_text = "\n".join(
            f"- {a.get('item', a) if isinstance(a, dict) else a}" for a in action_items
        ) or "No specific action items recorded."

        prompt = (
            f"Write a professional meeting follow-up email.\n\n"
            f"Meeting: {meeting.get('title', 'Our Meeting')}\n"
            f"Date: {meeting.get('date', '')}\n"
            f"Participants: {', '.join(meeting.get('participants', []))}\n"
            f"Summary: {meeting.get('summary', '')}\n"
            f"Key Points: {', '.join(meeting.get('key_points', []))}\n"
            f"Action Items:\n{action_text}\n\n"
            f"Write a concise, professional follow-up email. Include subject line.\n"
            f"Respond ONLY with valid JSON:\n"
            f'{{"subject": "...", "body": "..."}}'
        )
        try:
            result = _query_ai_for_agent("meeting-intelligence", prompt)
            content = result.get("content", result.get("text", ""))
            start = content.find("{")
            end = content.rfind("}") + 1
            if start >= 0 and end > start:
                parsed = json.loads(content[start:end])
                followup = f"Subject: {parsed.get('subject', '')}\n\n{parsed.get('body', '')}"
                return update_meeting(meeting_id, {"followup_email": followup})
        except Exception:
            pass

    # Fallback template
    participants = ", ".join(meeting.get("participants", ["team"]))
    action_items = meeting.get("action_items", [])
    action_text = "\n".join(
        f"• {a.get('item', a) if isinstance(a, dict) else a}" for a in action_items
    ) or "• Review discussed topics and report back"
    followup = (
        f"Subject: Follow-up: {meeting.get('title', 'Our Meeting')}\n\n"
        f"Hi {participants},\n\n"
        f"Thank you for joining today's meeting. Here's a quick recap:\n\n"
        f"Summary: {meeting.get('summary', 'See notes.')}\n\n"
        f"Action Items:\n{action_text}\n\n"
        f"Please let me know if you have any questions.\n\n"
        f"Best regards"
    )
    return update_meeting(meeting_id, {"followup_email": followup})
