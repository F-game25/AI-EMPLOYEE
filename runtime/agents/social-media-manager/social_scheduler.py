"""Social Media Scheduler — Post scheduling, auto-posting simulation, and content generation.

Extends the social media manager with scheduling capabilities:
  - Post scheduling: platform, content, scheduled_at, status
  - Auto-posting simulation (marks as posted when scheduled_at passes)
  - AI-powered content generation via ai_router
  - Multi-platform support: Twitter/X, Instagram, LinkedIn, TikTok, Facebook, YouTube

Commands (via chat / WhatsApp / Dashboard):
  social schedule <platform> <content> <datetime>  — schedule a post
  social posts                                      — list scheduled posts
  social publish <id>                               — mark a post as published
  social generate <platform> <topic>               — AI-generate post content
  social auto-post                                  — process due scheduled posts
  social status                                     — scheduler overview

State files:
  ~/.ai-employee/state/social-schedule.json
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
SCHEDULE_FILE = AI_HOME / "state" / "social-schedule.json"

logging.basicConfig(
    level=getattr(logging, os.environ.get("LOG_LEVEL", "WARNING").upper(), logging.WARNING),
    format="%(message)s",
)
logger = logging.getLogger("social-scheduler")

_ai_router_path = AI_HOME / "agents" / "ai-router"
if str(_ai_router_path) not in sys.path:
    sys.path.insert(0, str(_ai_router_path))

try:
    from ai_router import query_ai_for_agent as _query_ai_for_agent  # type: ignore
    _AI_AVAILABLE = True
except ImportError:
    _AI_AVAILABLE = False

SUPPORTED_PLATFORMS = ["twitter", "instagram", "linkedin", "tiktok", "facebook", "youtube"]
POST_STATUSES = ["scheduled", "posted", "failed", "draft"]

__all__ = [
    "list_posts",
    "get_post",
    "schedule_post",
    "update_post",
    "delete_post",
    "publish_post",
    "generate_post_content",
    "process_due_posts",
    "get_schedule_stats",
]


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_iso(ts: str) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return None


def _load_schedule() -> dict:
    if not SCHEDULE_FILE.exists():
        return {"posts": []}
    try:
        return json.loads(SCHEDULE_FILE.read_text())
    except Exception:
        return {"posts": []}


def _save_schedule(data: dict) -> None:
    SCHEDULE_FILE.parent.mkdir(parents=True, exist_ok=True)
    SCHEDULE_FILE.write_text(json.dumps(data, indent=2))


def list_posts(
    platform: Optional[str] = None,
    status: Optional[str] = None,
) -> list:
    """Return all scheduled posts, optionally filtered."""
    data = _load_schedule()
    posts = data.get("posts", [])
    if platform:
        posts = [p for p in posts if p.get("platform") == platform]
    if status:
        posts = [p for p in posts if p.get("status") == status]
    return sorted(posts, key=lambda x: x.get("scheduled_at", ""), reverse=False)


def get_post(post_id: str) -> Optional[dict]:
    """Return a single post by ID."""
    data = _load_schedule()
    return next((p for p in data["posts"] if p["id"] == post_id), None)


def schedule_post(
    platform: str,
    content: str,
    scheduled_at: str,
    media_urls: Optional[list] = None,
    hashtags: Optional[list] = None,
    campaign: str = "",
    status: str = "scheduled",
) -> dict:
    """Schedule a new post."""
    normalized = platform.lower().strip()
    if normalized not in SUPPORTED_PLATFORMS:
        raise ValueError(f"Unsupported platform '{platform}'. Must be one of: {SUPPORTED_PLATFORMS}")
    data = _load_schedule()
    post = {
        "id": str(uuid.uuid4()),
        "platform": normalized,
        "content": content,
        "scheduled_at": scheduled_at,
        "media_urls": media_urls or [],
        "hashtags": hashtags or [],
        "campaign": campaign,
        "status": status,
        "published_at": None,
        "error": None,
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }
    data["posts"].append(post)
    _save_schedule(data)
    logger.info("Post scheduled: %s on %s", post["id"], platform)
    return post


def update_post(post_id: str, updates: dict) -> Optional[dict]:
    """Update post fields."""
    data = _load_schedule()
    for i, post in enumerate(data["posts"]):
        if post["id"] == post_id:
            updates.pop("id", None)
            updates.pop("created_at", None)
            data["posts"][i].update(updates)
            data["posts"][i]["updated_at"] = _now_iso()
            _save_schedule(data)
            return data["posts"][i]
    return None


def delete_post(post_id: str) -> bool:
    """Delete a post. Returns True if deleted."""
    data = _load_schedule()
    before = len(data["posts"])
    data["posts"] = [p for p in data["posts"] if p["id"] != post_id]
    if len(data["posts"]) < before:
        _save_schedule(data)
        return True
    return False


def publish_post(post_id: str) -> Optional[dict]:
    """Mark a post as published."""
    return update_post(post_id, {"status": "posted", "published_at": _now_iso()})


def generate_post_content(
    platform: str,
    topic: str,
    tone: str = "engaging",
    include_hashtags: bool = True,
) -> dict:
    """AI-generate post content for a given platform and topic."""
    platform_guides = {
        "twitter": "280 chars max, punchy, use 1-2 hashtags",
        "instagram": "engaging caption, emojis welcome, 5-10 hashtags",
        "linkedin": "professional tone, 1-3 paragraphs, 3-5 hashtags",
        "tiktok": "trendy hook, short sentences, 5-8 hashtags",
        "facebook": "conversational, 1-2 paragraphs, 2-3 hashtags",
        "youtube": "compelling description, 100-200 words, keywords",
    }

    if _AI_AVAILABLE:
        guide = platform_guides.get(platform.lower(), "concise and engaging")
        prompt = (
            f"Write a social media post for {platform} about: {topic}\n\n"
            f"Platform guidance: {guide}\n"
            f"Tone: {tone}\n"
            f"Include hashtags: {include_hashtags}\n\n"
            f"Respond ONLY with valid JSON:\n"
            f'{{"content": "...", "hashtags": ["tag1", "tag2"], "char_count": 0}}'
        )
        try:
            result = _query_ai_for_agent("social-scheduler", prompt)
            content_str = result.get("content", result.get("text", ""))
            start = content_str.find("{")
            end = content_str.rfind("}") + 1
            if start >= 0 and end > start:
                parsed = json.loads(content_str[start:end])
                return {
                    "content": parsed.get("content", ""),
                    "hashtags": parsed.get("hashtags", []),
                    "platform": platform,
                    "ai_generated": True,
                }
        except Exception:
            pass

    hashtag_defaults = {
        "twitter": ["#AI", "#business"],
        "instagram": ["#content", "#marketing", "#business", "#growth"],
        "linkedin": ["#professional", "#business", "#leadership"],
        "tiktok": ["#fyp", "#viral", "#content"],
        "facebook": ["#business", "#community"],
        "youtube": ["#youtube", "#content"],
    }
    return {
        "content": f"Exciting update on {topic}! Stay tuned for more. 🚀",
        "hashtags": hashtag_defaults.get(platform.lower(), ["#business"]),
        "platform": platform,
        "ai_generated": False,
    }


def process_due_posts() -> list:
    """Auto-post: mark all scheduled posts whose scheduled_at has passed as 'posted'."""
    now = datetime.now(timezone.utc)
    data = _load_schedule()
    published = []
    for i, post in enumerate(data["posts"]):
        if post.get("status") != "scheduled":
            continue
        scheduled_at = _parse_iso(post.get("scheduled_at", ""))
        if scheduled_at and scheduled_at <= now:
            data["posts"][i]["status"] = "posted"
            data["posts"][i]["published_at"] = _now_iso()
            data["posts"][i]["updated_at"] = _now_iso()
            published.append(data["posts"][i])
    if published:
        _save_schedule(data)
    return published


def get_schedule_stats() -> dict:
    """Return summary statistics for the post schedule."""
    data = _load_schedule()
    posts = data.get("posts", [])
    stats = {"total": len(posts), "scheduled": 0, "posted": 0, "draft": 0, "failed": 0}
    platform_counts: dict = {}
    for post in posts:
        status = post.get("status", "scheduled")
        if status in stats:
            stats[status] += 1
        plat = post.get("platform", "unknown")
        platform_counts[plat] = platform_counts.get(plat, 0) + 1
    stats["by_platform"] = platform_counts
    return stats
