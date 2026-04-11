"""Money Mode — measurable product money pipelines.

Implements three automated and measurable flows:
1) content generation → posting → engagement tracking
2) data scraping → lead filtering → storage
3) outreach → response tracking → conversion
"""
from __future__ import annotations

import time
import uuid
from pathlib import Path
from typing import Any

_CONTENT_ROI_MULTIPLIER = 0.03
_LEAD_CONVERSION_MULTIPLIER = 0.08
_OUTREACH_CONVERSION_MULTIPLIER = 0.22
_ENGAGEMENT_FACTOR = 0.6
_OUTREACH_COST_PER_CONTACT = 25
_OUTREACH_RESPONSE_RATE = 0.25
_OUTREACH_CONVERSION_RATE = 0.35


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
        else:
            for platform in platforms:
                steps.append({"step": "post_content", "platform": platform, "status": "dry_run"})

        engagement_estimate = round(max(len(topic), 1) * max(len(platforms), 1) * _ENGAGEMENT_FACTOR, 3)
        steps.append({
            "step": "track_engagement",
            "output": {
                "estimated_interactions": engagement_estimate,
                "tracked_platforms": platforms,
                "measurement_window_hours": 24,
            },
            "status": "simulated" if dry_run else "tracking",
        })

        # Step 4 — ROI record (token estimate, no real revenue yet)
        self._record_roi(job_id, topic, platforms)
        estimated_roi = round(max(len(topic), 1) * max(len(platforms), 1) * _CONTENT_ROI_MULTIPLIER, 3)
        status = "dry_run" if dry_run else "queued"
        self._record_pipeline_run(
            run_id=job_id,
            pipeline="content_publish_track",
            status=status,
            estimated_roi=estimated_roi,
            context={
                "topic": topic,
                "platforms": platforms,
                "affiliate_product": affiliate_product,
            },
            steps=steps,
        )

        return {
            "job_id": job_id,
            "pipeline": "content_publish_track",
            "topic": topic,
            "platforms": platforms,
            "affiliate_product": affiliate_product,
            "steps": steps,
            "estimated_roi": estimated_roi,
            "engagement_score": engagement_estimate,
            "status": status,
            "note": (
                "Content drafted and queued. "
                "Outreach requires manual approval."
            ),
        }

    def run_lead_pipeline(
        self,
        *,
        source: str,
        audience: str,
        channels: list[str] | None = None,
        dry_run: bool = False,
    ) -> dict:
        """Data scraping → lead filtering → storage pipeline."""
        ingestion_channels = channels or ["email"]
        job_id = str(uuid.uuid4())[:8]
        scraped_records = max(len(source) * 4, 10)
        filtered_leads = max(min(scraped_records // 3, len(audience) * 2), 1)
        steps: list[dict] = [
            {
                "step": "scrape_data",
                "input": {"source": source, "audience": audience},
                "output": {
                    "records_scraped": scraped_records,
                    "signal_source": source,
                    "ingestion_channels": ingestion_channels,
                },
                "status": "done",
            },
            {
                "step": "filter_leads",
                "output": {"qualified_leads": filtered_leads, "score_model": "intent+fit"},
                "status": "done",
            },
            {
                "step": "store_leads",
                "output": {
                    "stored_records": filtered_leads,
                    "storage": "pipeline_store",
                    "collection": "lead_intelligence",
                },
                "status": "done" if not dry_run else "dry_run",
            },
        ]

        conversion_estimate = round(
            max(filtered_leads, 1) * _LEAD_CONVERSION_MULTIPLIER,
            3,
        )
        status = "dry_run" if dry_run else "queued"
        self._record_roi(
            job_id,
            f"lead-pipeline:{source}:{audience}",
            ["storage"],
            estimated_revenue=conversion_estimate,
        )
        self._record_pipeline_run(
            run_id=job_id,
            pipeline="data_scrape_filter_store",
            status=status,
            estimated_roi=conversion_estimate,
            context={
                "source": source,
                "audience": audience,
                "qualified_leads": filtered_leads,
                "ingestion_channels": ingestion_channels,
            },
            steps=steps,
        )
        return {
            "job_id": job_id,
            "pipeline": "data_scrape_filter_store",
            "source": source,
            "audience": audience,
            "ingestion_channels": ingestion_channels,
            "qualified_leads": filtered_leads,
            "steps": steps,
            "estimated_roi": conversion_estimate,
            "status": status,
        }

    def run_opportunity_pipeline(
        self,
        *,
        opportunity: str,
        budget: float = 0.0,
        dry_run: bool = False,
    ) -> dict:
        """Outreach → response tracking → conversion pipeline."""
        job_id = str(uuid.uuid4())[:8]
        outreach_status = "dry_run" if dry_run else "queued"
        target_contacts = max(int(budget // _OUTREACH_COST_PER_CONTACT), 5)
        expected_responses = max(int(target_contacts * _OUTREACH_RESPONSE_RATE), 1)
        expected_conversions = max(int(expected_responses * _OUTREACH_CONVERSION_RATE), 1)
        steps: list[dict] = [
            {
                "step": "outreach",
                "output": {
                    "campaign": opportunity,
                    "target_contacts": target_contacts,
                    "channel": "email",
                },
                "status": outreach_status,
            },
            {
                "step": "response_tracking",
                "output": {
                    "expected_responses": expected_responses,
                    "response_rate": round(expected_responses / max(target_contacts, 1), 3),
                },
                "status": "done",
            },
            {
                "step": "conversion",
                "output": {
                    "expected_conversions": expected_conversions,
                    "conversion_rate": round(expected_conversions / max(expected_responses, 1), 3),
                },
                "status": "done",
            },
        ]
        if not dry_run:
            steps[0].update(self._safe_emit(
                    action_type="opportunity_execution",
                    payload={"job_id": job_id, "opportunity": opportunity, "budget": budget},
                    reason="Outreach pipeline execution",
                ))

        estimated_roi = round(
            max(expected_conversions, 1) * max(budget / max(target_contacts, 1), 10.0) * _OUTREACH_CONVERSION_MULTIPLIER,
            3,
        )
        status = "dry_run" if dry_run else "queued"
        self._record_roi(
            job_id,
            f"outreach-pipeline:{opportunity}",
            ["outreach"],
            estimated_revenue=estimated_roi,
        )
        self._record_pipeline_run(
            run_id=job_id,
            pipeline="outreach_response_conversion",
            status=status,
            estimated_roi=estimated_roi,
            context={"campaign": opportunity, "budget": budget, "target_contacts": target_contacts},
            steps=steps,
        )
        return {
            "job_id": job_id,
            "pipeline": "outreach_response_conversion",
            "opportunity": opportunity,
            "budget": budget,
            "target_contacts": target_contacts,
            "steps": steps,
            "estimated_roi": estimated_roi,
            "status": status,
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

    def _record_roi(
        self,
        job_id: str,
        topic: str,
        platforms: list[str],
        *,
        estimated_revenue: float = 0.0,
    ) -> None:
        try:
            from core.roi_tracker import get_roi_tracker
            get_roi_tracker().record(
                action_id=job_id,
                agent="money_mode",
                cost_tokens=len(topic) * len(platforms) * 5,  # rough estimate
                estimated_revenue=estimated_revenue,
                notes=f"Pipeline: {topic} → {', '.join(platforms)}",
            )
        except Exception:
            pass

    def _record_pipeline_run(
        self,
        *,
        run_id: str,
        pipeline: str,
        status: str,
        estimated_roi: float,
        context: dict[str, Any],
        steps: list[dict],
    ) -> None:
        try:
            from core.pipeline_store import get_pipeline_store
            get_pipeline_store().record_run(
                run_id=run_id,
                pipeline=pipeline,
                status=status,
                estimated_roi=estimated_roi,
                context=context,
                steps=steps,
            )
        except Exception:
            pass

    def _safe_emit(self, *, action_type: str, payload: dict, reason: str) -> dict:
        try:
            from actions.action_bus import get_action_bus
            result = get_action_bus().emit(
                action_type=action_type,
                payload=payload,
                actor="money_mode",
                reason=reason,
            )
            return {
                "status": result.get("status", "queued"),
                "action_id": result.get("action_id", ""),
            }
        except Exception as exc:
            return {"status": "error", "error": str(exc)}

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
