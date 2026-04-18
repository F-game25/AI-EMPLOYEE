"""Economy and Money Mode tests.

Validates the money-making pipelines (content, lead gen, outreach)
and the audit/ROI tracking that underpins them.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_DIR = REPO_ROOT / "runtime"

if str(RUNTIME_DIR) not in sys.path:
    sys.path.insert(0, str(RUNTIME_DIR))


# ---------------------------------------------------------------------------
# Test: MoneyMode content pipeline
# ---------------------------------------------------------------------------

class TestContentPipeline:
    """Verify the content generation → publish → track pipeline."""

    def test_money_mode_importable(self) -> None:
        from core.money_mode import MoneyMode
        mm = MoneyMode()
        assert mm is not None

    def test_content_pipeline_dry_run(self) -> None:
        """Dry-run should return result without external actions."""
        from core.money_mode import MoneyMode
        mm = MoneyMode()
        result = mm.run_content_pipeline(
            topic="AI automation tips",
            platforms=["twitter"],
            dry_run=True,
        )
        assert isinstance(result, dict)
        assert result["status"] == "dry_run"
        assert result["topic"] == "AI automation tips"
        assert "steps" in result
        assert len(result["steps"]) >= 1

    def test_content_pipeline_execution(self) -> None:
        """Normal execution should mark status as 'executed'."""
        from core.money_mode import MoneyMode
        mm = MoneyMode()
        result = mm.run_content_pipeline(
            topic="startup growth hacks",
            platforms=["twitter", "linkedin"],
        )
        assert result["status"] == "executed"
        assert "twitter" in result["platforms"]
        assert "linkedin" in result["platforms"]

    def test_content_pipeline_has_roi(self) -> None:
        """Every pipeline run should calculate estimated ROI."""
        from core.money_mode import MoneyMode
        mm = MoneyMode()
        result = mm.run_content_pipeline(topic="SaaS pricing strategy", dry_run=True)
        assert "estimated_roi" in result
        assert result["estimated_roi"] > 0

    def test_content_pipeline_multiple_platforms(self) -> None:
        """Running for multiple platforms should produce steps for each."""
        from core.money_mode import MoneyMode
        mm = MoneyMode()
        result = mm.run_content_pipeline(
            topic="product launch",
            platforms=["twitter", "linkedin", "youtube"],
            dry_run=True,
        )
        # Should have at least one step per platform for content drafting
        assert len(result["steps"]) >= 3


# ---------------------------------------------------------------------------
# Test: MoneyMode lead pipeline
# ---------------------------------------------------------------------------

class TestLeadPipeline:
    """Verify the lead generation pipeline."""

    def test_lead_pipeline_dry_run(self) -> None:
        from core.money_mode import MoneyMode
        mm = MoneyMode()
        result = mm.run_lead_pipeline(
            source="linkedin_scraper",
            audience="startup founders",
            dry_run=True,
        )
        assert isinstance(result, dict)
        assert result["status"] == "dry_run"
        assert "steps" in result

    def test_lead_pipeline_has_roi(self) -> None:
        from core.money_mode import MoneyMode
        mm = MoneyMode()
        result = mm.run_lead_pipeline(
            source="web_scraper",
            audience="ecommerce owners",
            dry_run=True,
        )
        assert "estimated_roi" in result
        assert result["estimated_roi"] >= 0


# ---------------------------------------------------------------------------
# Test: MoneyMode outreach pipeline
# ---------------------------------------------------------------------------

class TestOutreachPipeline:
    """Verify the outreach → response → conversion pipeline."""

    def test_opportunity_pipeline_dry_run(self) -> None:
        from core.money_mode import MoneyMode
        mm = MoneyMode()
        result = mm.run_opportunity_pipeline(
            opportunity="Free AI audit for startups",
            budget=500.0,
            dry_run=True,
        )
        assert isinstance(result, dict)
        assert result["status"] == "dry_run"

    def test_opportunity_pipeline_has_roi(self) -> None:
        from core.money_mode import MoneyMode
        mm = MoneyMode()
        result = mm.run_opportunity_pipeline(
            opportunity="Demo call for prospects",
            budget=200.0,
            dry_run=True,
        )
        assert "estimated_roi" in result


# ---------------------------------------------------------------------------
# Test: Audit engine recording
# ---------------------------------------------------------------------------

class TestAuditEngineRecording:
    """Verify the audit engine stores and retrieves events."""

    def test_audit_engine_importable(self) -> None:
        from core.audit_engine import AuditEngine, get_audit_engine
        ae = get_audit_engine()
        assert ae is not None

    def test_record_event(self) -> None:
        from core.audit_engine import AuditEngine
        ae = AuditEngine()
        event = ae.record(
            actor="test_agent",
            action="test_action",
            input_data={"key": "value"},
            output_data={"result": "ok"},
        )
        assert isinstance(event, dict)
        assert event["actor"] == "test_agent"
        assert event["action"] == "test_action"

    def test_record_high_risk_event(self) -> None:
        from core.audit_engine import AuditEngine
        ae = AuditEngine()
        event = ae.record(
            actor="admin",
            action="forge_deploy",
            input_data={"target": "production"},
        )
        assert event["risk_score"] >= 0.6

    def test_record_low_risk_event(self) -> None:
        from core.audit_engine import AuditEngine
        ae = AuditEngine()
        event = ae.record(
            actor="viewer",
            action="dashboard_view",
        )
        assert event["risk_score"] < 0.25

    def test_recent_events(self) -> None:
        from core.audit_engine import AuditEngine
        ae = AuditEngine()
        ae.record(actor="agent-a", action="test_action_1")
        ae.record(actor="agent-b", action="test_action_2")
        recent = ae.recent(limit=10)
        assert isinstance(recent, list)
        assert len(recent) >= 2

    def test_stats_returns_expected_keys(self) -> None:
        from core.audit_engine import AuditEngine
        ae = AuditEngine()
        ae.record(actor="test", action="test_stat")
        stats = ae.stats()
        assert isinstance(stats, dict)
        for key in ("total", "by_actor", "by_action", "risk_distribution"):
            assert key in stats, f"Missing key in stats: {key}"

    def test_risk_classification(self) -> None:
        """Verify auto risk classification for known actions."""
        from core.audit_engine import _classify_risk
        assert _classify_risk("forge_deploy") >= 0.6
        assert 0.25 <= _classify_risk("forge_submit") < 0.6
        assert _classify_risk("dashboard_view") < 0.25


# ---------------------------------------------------------------------------
# Test: ROI tracker (if available)
# ---------------------------------------------------------------------------

class TestROITracker:
    """Verify ROI tracking module exists."""

    def test_roi_tracker_importable(self) -> None:
        from core.roi_tracker import RoiTracker
        assert RoiTracker is not None

    def test_roi_tracker_instantiation(self) -> None:
        from core.roi_tracker import RoiTracker
        tracker = RoiTracker()
        assert tracker is not None
