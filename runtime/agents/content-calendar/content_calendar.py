"""Content Calendar Agent — Plan, schedule, and track content across all platforms.

Manages a multi-platform content calendar:
  - Calendar entries: date, platform, content_type, title, content, status
  - AI-powered 30-day content plan generation
  - Content statuses: idea → draft → scheduled → published
  - Platform and content type filtering

Commands (via chat / WhatsApp / Dashboard):
  calendar add <date> <platform> <type> <title>  — add calendar entry
  calendar list                                   — list all entries
  calendar generate <niche> <days>               — AI-generate content plan
  calendar today                                  — today's scheduled content
  calendar status                                 — calendar overview

State files:
  ~/.ai-employee/state/content-calendar.json
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
CALENDAR_FILE = AI_HOME / "state" / "content-calendar.json"

logging.basicConfig(
    level=getattr(logging, os.environ.get("LOG_LEVEL", "WARNING").upper(), logging.WARNING),
    format="%(message)s",
)
logger = logging.getLogger("content-calendar")

_ai_router_path = AI_HOME / "agents" / "ai-router"
if str(_ai_router_path) not in sys.path:
    sys.path.insert(0, str(_ai_router_path))

try:
    from ai_router import query_ai_for_agent as _query_ai_for_agent  # type: ignore
    _AI_AVAILABLE = True
except ImportError:
    _AI_AVAILABLE = False

CONTENT_TYPES = ["post", "reel", "story", "article", "email", "video", "podcast", "thread"]
PLATFORMS = ["instagram", "twitter", "linkedin", "tiktok", "facebook", "youtube", "blog", "email"]
CONTENT_STATUSES = ["idea", "draft", "scheduled", "published", "archived"]

__all__ = [
    "list_entries",
    "get_entry",
    "add_entry",
    "update_entry",
    "delete_entry",
    "generate_calendar",
    "get_calendar_stats",
    "get_entries_for_date",
]


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _today_str() -> str:
    return date.today().isoformat()


def _load_calendar() -> dict:
    if not CALENDAR_FILE.exists():
        return {"entries": []}
    try:
        return json.loads(CALENDAR_FILE.read_text())
    except Exception:
        return {"entries": []}


def _save_calendar(data: dict) -> None:
    CALENDAR_FILE.parent.mkdir(parents=True, exist_ok=True)
    CALENDAR_FILE.write_text(json.dumps(data, indent=2))


def list_entries(
    platform: Optional[str] = None,
    status: Optional[str] = None,
    content_type: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> list:
    """Return calendar entries with optional filters."""
    data = _load_calendar()
    entries = data.get("entries", [])
    if platform:
        entries = [e for e in entries if e.get("platform") == platform]
    if status:
        entries = [e for e in entries if e.get("status") == status]
    if content_type:
        entries = [e for e in entries if e.get("content_type") == content_type]
    if date_from:
        entries = [e for e in entries if e.get("date", "") >= date_from]
    if date_to:
        entries = [e for e in entries if e.get("date", "") <= date_to]
    return sorted(entries, key=lambda x: x.get("date", ""))


def get_entry(entry_id: str) -> Optional[dict]:
    """Return a single calendar entry by ID."""
    data = _load_calendar()
    return next((e for e in data["entries"] if e["id"] == entry_id), None)


def add_entry(
    date_str: str,
    platform: str,
    content_type: str,
    title: str,
    content: str = "",
    status: str = "idea",
    tags: Optional[list] = None,
    notes: str = "",
) -> dict:
    """Add a new calendar entry."""
    data = _load_calendar()
    entry = {
        "id": str(uuid.uuid4()),
        "date": date_str,
        "platform": platform,
        "content_type": content_type,
        "title": title,
        "content": content,
        "status": status,
        "tags": tags or [],
        "notes": notes,
        "published_at": None,
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }
    data["entries"].append(entry)
    _save_calendar(data)
    logger.info("Calendar entry added: %s on %s", title, date_str)
    return entry


def update_entry(entry_id: str, updates: dict) -> Optional[dict]:
    """Update a calendar entry."""
    data = _load_calendar()
    for i, entry in enumerate(data["entries"]):
        if entry["id"] == entry_id:
            updates.pop("id", None)
            updates.pop("created_at", None)
            if updates.get("status") == "published" and not entry.get("published_at"):
                updates["published_at"] = _now_iso()
            data["entries"][i].update(updates)
            data["entries"][i]["updated_at"] = _now_iso()
            _save_calendar(data)
            return data["entries"][i]
    return None


def delete_entry(entry_id: str) -> bool:
    """Delete a calendar entry."""
    data = _load_calendar()
    before = len(data["entries"])
    data["entries"] = [e for e in data["entries"] if e["id"] != entry_id]
    if len(data["entries"]) < before:
        _save_calendar(data)
        return True
    return False


def get_entries_for_date(target_date: Optional[str] = None) -> list:
    """Return all entries for a specific date (defaults to today)."""
    target = target_date or _today_str()
    data = _load_calendar()
    return [e for e in data.get("entries", []) if e.get("date") == target]


def generate_calendar(
    niche: str,
    days: int = 30,
    platforms: Optional[list] = None,
    tone: str = "engaging",
) -> list:
    """AI-generate a content calendar for the given niche and time period."""
    target_platforms = platforms or ["instagram", "linkedin", "twitter"]
    start_date = date.today()

    if _AI_AVAILABLE:
        prompt = (
            f"Create a {days}-day content calendar for a {niche} business.\n\n"
            f"Platforms: {', '.join(target_platforms)}\n"
            f"Content tone: {tone}\n"
            f"Start date: {start_date.isoformat()}\n\n"
            f"Generate {min(days, 20)} varied content entries mixing posts, reels, articles, and stories.\n"
            f"Spread across different platforms and content types.\n\n"
            f"Respond ONLY with valid JSON array:\n"
            f'[{{"date": "YYYY-MM-DD", "platform": "instagram", '
            f'"content_type": "post", "title": "...", "content": "...", "tags": ["tag1"]}}]'
        )
        try:
            result = _query_ai_for_agent("content-calendar", prompt)
            content_str = result.get("content", result.get("text", ""))
            start = content_str.find("[")
            end = content_str.rfind("]") + 1
            if start >= 0 and end > start:
                entries_data = json.loads(content_str[start:end])
                created = []
                for entry_data in entries_data[:days]:
                    try:
                        entry = add_entry(
                            date_str=entry_data.get("date", start_date.isoformat()),
                            platform=entry_data.get("platform", target_platforms[0]),
                            content_type=entry_data.get("content_type", "post"),
                            title=entry_data.get("title", "Untitled"),
                            content=entry_data.get("content", ""),
                            status="scheduled",
                            tags=entry_data.get("tags", []),
                        )
                        created.append(entry)
                    except Exception:
                        pass
                if created:
                    return created
        except Exception:
            pass

    # Fallback: generate template calendar
    created = []
    content_ideas = [
        ("How to use AI to automate your business", "article"),
        ("Behind the scenes of our process", "reel"),
        ("5 tips for productivity", "post"),
        ("Customer success story spotlight", "story"),
        ("Industry insight and trends", "post"),
        ("Q&A with our team", "reel"),
        ("Product feature highlight", "post"),
        ("Weekly motivation and tips", "post"),
    ]
    import itertools
    platform_cycle = itertools.cycle(target_platforms)
    for i in range(min(days, 30)):
        entry_date = (start_date + timedelta(days=i)).isoformat()
        idea_title, content_type = content_ideas[i % len(content_ideas)]
        platform = next(platform_cycle)
        entry = add_entry(
            date_str=entry_date,
            platform=platform,
            content_type=content_type,
            title=f"{idea_title} — {niche}",
            content=f"Content about {niche}: {idea_title}",
            status="idea",
            tags=[niche.lower().replace(" ", "-"), platform],
        )
        created.append(entry)
    return created


def get_calendar_stats() -> dict:
    """Return content calendar statistics."""
    data = _load_calendar()
    entries = data.get("entries", [])
    stats = {
        "total": len(entries),
        "by_status": {},
        "by_platform": {},
        "by_content_type": {},
        "scheduled_upcoming": 0,
        "published_this_month": 0,
    }
    today = _today_str()
    month_start = today[:7] + "-01"
    for entry in entries:
        status = entry.get("status", "idea")
        stats["by_status"][status] = stats["by_status"].get(status, 0) + 1
        platform = entry.get("platform", "unknown")
        stats["by_platform"][platform] = stats["by_platform"].get(platform, 0) + 1
        ct = entry.get("content_type", "post")
        stats["by_content_type"][ct] = stats["by_content_type"].get(ct, 0) + 1
        if status == "scheduled" and entry.get("date", "") >= today:
            stats["scheduled_upcoming"] += 1
        if status == "published" and entry.get("date", "") >= month_start:
            stats["published_this_month"] += 1
    return stats
