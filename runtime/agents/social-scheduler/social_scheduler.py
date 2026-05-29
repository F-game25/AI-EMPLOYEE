"""Social Scheduler Agent — schedules and manages social media post queues.

Maintains a queue of scheduled posts with timestamps, tracks posting status,
generates AI content drafts, and manages multi-platform queues.

Commands (via chat):
  schedule add     <platform> <content> <datetime>  — schedule a post
  schedule list                                      — show upcoming queue
  schedule generate <platform> <topic>               — AI-generate post content
  schedule queue                                     — show all pending posts
  schedule post    <id>                              — mark a post as posted
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from agents.base import BaseAgent

AI_HOME = Path(os.environ.get("AI_HOME", str(Path.home() / ".ai-employee")))
SCHEDULE_FILE = AI_HOME / "state" / "social-schedule.json"

PLATFORMS = ["instagram", "linkedin", "twitter", "tiktok", "facebook", "youtube"]

SYSTEM = """You are a Social Media Content Strategist. Generate platform-optimized social media posts.

Output JSON with this structure:
{
  "platform": "instagram|linkedin|twitter|tiktok|facebook|youtube",
  "content": "Full post text ready to copy-paste",
  "hashtags": ["#tag1", "#tag2"],
  "best_time": "Recommended posting time (e.g. Tuesday 9AM EST)",
  "content_type": "text|carousel|video|reel|story|thread",
  "hook": "First line that stops the scroll",
  "cta": "Call to action",
  "estimated_reach": "low|medium|high",
  "engagement_tips": ["tip 1", "tip 2"]
}

Platform rules:
- Instagram: 125-150 chars before fold, 20-30 hashtags, visual description
- LinkedIn: professional tone, 1300 chars max for full display, 3-5 hashtags
- Twitter/X: under 280 chars, 1-2 hashtags, punchy
- TikTok: hook in first 3 words, trend-aware, 4-6 hashtags"""


class SocialSchedulerAgent(BaseAgent):
    agent_id = "social-scheduler"
    required_fields = ("task",)

    def execute(self, payload: dict) -> dict:
        action = payload.get("action", "generate")
        platform = payload.get("platform", "linkedin").lower()
        topic = payload.get("topic") or payload.get("task", "")
        scheduled_at = payload.get("scheduled_at", "")

        if action == "list":
            posts = self._load_schedule()
            pending = [p for p in posts if p.get("status") == "scheduled"]
            return {"posts": pending, "total": len(pending), "tokens_used": 0}

        prompt = (
            f"Generate a {platform} post about: {topic}\n"
            f"Tone: {payload.get('tone', 'professional but engaging')}\n"
            f"Goal: {payload.get('goal', 'engagement and reach')}"
        )
        data, tokens = self._ask_json(prompt=prompt, system=SYSTEM)

        if isinstance(data, dict):
            post = {
                "id": str(uuid.uuid4())[:8],
                "platform": platform,
                "content": data.get("content", ""),
                "hashtags": data.get("hashtags", []),
                "scheduled_at": scheduled_at or data.get("best_time", ""),
                "status": "scheduled" if scheduled_at else "draft",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "topic": topic,
            }
            self._save_post(post)
            data["post_id"] = post["id"]

        data["tokens_used"] = tokens
        return data

    def _load_schedule(self) -> list:
        if not SCHEDULE_FILE.exists():
            return []
        try:
            return json.loads(SCHEDULE_FILE.read_text())
        except Exception:
            return []

    def _save_post(self, post: dict) -> None:
        posts = self._load_schedule()
        posts.append(post)
        SCHEDULE_FILE.parent.mkdir(parents=True, exist_ok=True)
        SCHEDULE_FILE.write_text(json.dumps(posts[-1000:], indent=2))
