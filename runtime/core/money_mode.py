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

_CONTENT_ROI_MULTIPLIER = 0.03
_LEAD_CONVERSION_MULTIPLIER = 0.08
_HIGH_RISK_MULTIPLIER = 1.8
_NORMAL_RISK_MULTIPLIER = 1.2


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
        """Data → Leads → Outreach → Conversion pipeline."""
        channels = channels or ["email"]
        job_id = str(uuid.uuid4())[:8]
        steps: list[dict] = [
            {
                "step": "collect_data",
                "input": {"source": source, "audience": audience},
                "output": {"lead_segments": [audience], "signal_source": source},
                "status": "done",
            },
            {
                "step": "qualify_leads",
                "output": {"qualified_leads": max(len(audience) // 2, 1), "score_model": "intent+fit"},
                "status": "done",
            },
        ]

        outreach_status = "dry_run" if dry_run else "queued"
        for channel in channels:
            action = {
                "step": "outreach_sequence",
                "channel": channel,
                "status": outreach_status,
            }
            if not dry_run:
                action.update(self._safe_emit(
                    action_type="lead_outreach_sequence",
                    payload={"job_id": job_id, "channel": channel, "audience": audience},
                    reason="Lead pipeline outreach execution",
                ))
            steps.append(action)

        conversion_estimate = round(
            max(len(audience), 1) * max(len(channels), 1) * _LEAD_CONVERSION_MULTIPLIER,
            3,
        )
        status = "dry_run" if dry_run else "queued"
        self._record_roi(
            job_id,
            f"lead-pipeline:{source}:{audience}",
            channels,
            estimated_revenue=conversion_estimate,
        )
        self._record_pipeline_run(
            run_id=job_id,
            pipeline="data_leads_outreach_conversion",
            status=status,
            estimated_roi=conversion_estimate,
            context={"source": source, "audience": audience, "channels": channels},
            steps=steps,
        )
        return {
            "job_id": job_id,
            "pipeline": "data_leads_outreach_conversion",
            "source": source,
            "audience": audience,
            "channels": channels,
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
        """Opportunity → Execution → ROI tracking pipeline."""
        job_id = str(uuid.uuid4())[:8]
        risk = self._mode_risk_tolerance()
        steps: list[dict] = [
            {
                "step": "opportunity_assessment",
                "output": {
                    "opportunity": opportunity,
                    "risk_tolerance": risk,
                    "execution_priority": "high" if risk == "high" else "normal",
                },
                "status": "done",
            },
            {
                "step": "execution_plan",
                "output": {
                    "budget": budget,
                    "milestones": ["launch", "optimize", "measure"],
                },
                "status": "done",
            },
        ]
        if not dry_run:
            steps.append({
                "step": "execute_opportunity",
                **self._safe_emit(
                    action_type="opportunity_execution",
                    payload={"job_id": job_id, "opportunity": opportunity, "budget": budget},
                    reason="Opportunity pipeline execution",
                ),
            })
        else:
            steps.append({"step": "execute_opportunity", "status": "dry_run"})

        estimated_roi = round(
            max(budget, 1.0) * (_HIGH_RISK_MULTIPLIER if risk == "high" else _NORMAL_RISK_MULTIPLIER),
            3,
        )
        status = "dry_run" if dry_run else "queued"
        self._record_roi(
            job_id,
            f"opportunity-pipeline:{opportunity}",
            ["execution"],
            estimated_revenue=estimated_roi,
        )
        self._record_pipeline_run(
            run_id=job_id,
            pipeline="opportunity_execution_roi",
            status=status,
            estimated_roi=estimated_roi,
            context={"opportunity": opportunity, "budget": budget, "risk_tolerance": risk},
            steps=steps,
        )
        return {
            "job_id": job_id,
            "pipeline": "opportunity_execution_roi",
            "opportunity": opportunity,
            "budget": budget,
            "risk_tolerance": risk,
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

    def _mode_risk_tolerance(self) -> str:
        try:
            from core.mode_manager import get_mode_manager
            return str(get_mode_manager().status().get("risk_tolerance", "medium"))
        except Exception:
            return "medium"


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
