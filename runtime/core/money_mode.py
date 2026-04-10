"""Money Mode — content pipeline orchestration.

Wires together existing agents (content_calendar, faceless_video,
social_media_manager) into an orchestrated job that:

1. Generates content ideas (affiliate or UGC)
2. Drafts the content
3. Schedules / publishes it
4. Tracks ROI

Outreach actions (cold email, follow-up) require explicit human approval
and are never fired automatically.

Usage::

    from core.money_mode import get_money_mode

    pipeline = get_money_mode()
    result = pipeline.run_content_pipeline(
        topic="best productivity apps 2025",
        platforms=["twitter", "linkedin"],
        affiliate_product="ClickFunnels",
    )
"""
from __future__ import annotations

import time
import uuid
from pathlib import Path
from typing import Any


class MoneyMode:
    """Orchestrates content-generation money pipelines."""

    # ------------------------------------------------------------------ public

    def run_content_pipeline(
        self,
        *,
        topic: str,
        platforms: list[str] | None = None,
        affiliate_product: str = "",
        dry_run: bool = False,
    ) -> dict:
        """Generate, draft, and schedule content across platforms.

        Parameters
        ----------
        topic:            Topic or keyword to generate content about.
        platforms:        Target platforms (default: ["twitter"]).
        affiliate_product: Optional product name to weave into copy.
        dry_run:          When True, no external actions are taken.
        """
        platforms = platforms or ["twitter"]
        job_id = str(uuid.uuid4())[:8]
        steps: list[dict] = []

        # Step 1 — idea generation
        steps.append(self._step_generate_idea(topic, affiliate_product))

        # Step 2 — draft content per platform
        for platform in platforms:
            steps.append(self._step_draft_content(topic, platform, affiliate_product))

        # Step 3 — schedule via ActionBus (gated by mode)
        if not dry_run:
            for platform in platforms:
                steps.append(self._step_schedule_post(topic, platform, job_id))

        # Step 4 — ROI record (token estimate, no real revenue yet)
        self._record_roi(job_id, topic, platforms)

        return {
            "job_id": job_id,
            "topic": topic,
            "platforms": platforms,
            "affiliate_product": affiliate_product,
            "steps": steps,
            "status": "dry_run" if dry_run else "queued",
            "note": (
                "Content drafted and queued. "
                "Outreach requires manual approval."
            ),
        }

    def affiliate_content_draft(
        self,
        *,
        product: str,
        niche: str,
        output_format: str = "blog_post",
    ) -> dict:
        """Draft affiliate content for a product.

        Respects robots.txt — does NOT scrape without permission.
        Returns a structured draft ready for human review before publishing.
        """
        job_id = str(uuid.uuid4())[:8]
        draft = {
            "job_id": job_id,
            "product": product,
            "niche": niche,
            "format": output_format,
            "status": "draft",
            "requires_review": True,
            "content": {
                "headline": f"Why {product} Is the Best Tool for {niche} in 2025",
                "body": (
                    f"[AI-generated draft — replace with real copy before publishing]\n\n"
                    f"If you're in {niche}, {product} can help you achieve your goals faster. "
                    f"Here's what makes it stand out…"
                ),
                "cta": f"Try {product} free — [affiliate link here]",
            },
            "disclaimer": (
                "This content contains affiliate links. Always disclose affiliate "
                "relationships per FTC guidelines."
            ),
        }

        try:
            from actions.action_bus import get_action_bus
            get_action_bus().emit(
                action_type="affiliate_draft_created",
                payload={"job_id": job_id, "product": product, "niche": niche},
                actor="money_mode",
                reason="Affiliate content draft generated for review",
            )
        except Exception:
            pass

        return draft

    # --------------------------------------------------------------- internals

    def _step_generate_idea(self, topic: str, affiliate_product: str) -> dict:
        return {
            "step": "generate_idea",
            "input": {"topic": topic, "affiliate_product": affiliate_product},
            "output": {
                "hook": f"Here's how {topic} can change your life in 2025",
                "angle": "educational + promotional" if affiliate_product else "educational",
            },
            "status": "done",
        }

    def _step_draft_content(self, topic: str, platform: str, affiliate_product: str) -> dict:
        templates = {
            "twitter": f"🔥 {topic} — thread 🧵\n\n1/ Here's what nobody tells you…",
            "linkedin": f"I learned something powerful about {topic} recently.\n\nHere's the full breakdown:",
            "tiktok": f"POV: You finally understand {topic} 👇",
            "instagram": f"Save this post 📌\n\n{topic} in 5 steps:",
        }
        body = templates.get(platform, f"[Draft for {platform}] {topic}")
        if affiliate_product:
            body += f"\n\nMy go-to tool: {affiliate_product} (link in bio)"
        return {
            "step": "draft_content",
            "platform": platform,
            "content": body,
            "status": "draft",
            "requires_review": True,
        }

    def _step_schedule_post(self, topic: str, platform: str, job_id: str) -> dict:
        result = {"step": "schedule_post", "platform": platform, "status": "unknown"}
        try:
            from actions.action_bus import get_action_bus
            bus_result = get_action_bus().emit(
                action_type="schedule_content_post",
                payload={"job_id": job_id, "platform": platform, "topic": topic},
                actor="money_mode",
                reason="Content pipeline: schedule post",
            )
            result["status"] = bus_result.get("status", "queued")
            result["action_id"] = bus_result.get("action_id", "")
        except Exception as exc:
            result["status"] = "error"
            result["error"] = str(exc)
        return result

    def _record_roi(self, job_id: str, topic: str, platforms: list[str]) -> None:
        try:
            from core.roi_tracker import get_roi_tracker
            get_roi_tracker().record(
                action_id=job_id,
                agent="money_mode",
                cost_tokens=len(topic) * len(platforms) * 5,  # rough estimate
                estimated_revenue=0.0,  # updated when clicks/conversions arrive
                notes=f"Content pipeline: {topic} → {', '.join(platforms)}",
            )
        except Exception:
            pass


# ── Singleton ─────────────────────────────────────────────────────────────────

_instance: MoneyMode | None = None
_instance_lock_obj = __import__("threading").Lock()


def get_money_mode() -> MoneyMode:
    """Return the process-wide MoneyMode singleton."""
    global _instance
    with _instance_lock_obj:
        if _instance is None:
            _instance = MoneyMode()
    return _instance
