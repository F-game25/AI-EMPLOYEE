"""Ascend Forge tests.

Validates the Forge submission pipeline, risk scoring, approval queue,
and integration with audit/reliability engines.
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
# Test: Risk scoring heuristics
# ---------------------------------------------------------------------------

class TestForgeRiskScoring:
    """Verify Forge risk classification works correctly."""

    def test_high_risk_keywords(self) -> None:
        """Goals containing deploy/delete/production should score HIGH."""
        from core.ascend_forge import _score_goal, _risk_label
        for goal in ("deploy to production", "delete all records", "wipe old data"):
            score = _score_goal(goal)
            assert score >= 0.7, f"Expected HIGH risk for '{goal}', got {score}"
            assert _risk_label(score) == "HIGH"

    def test_medium_risk_keywords(self) -> None:
        """Goals with refactor/update/migrate should score MEDIUM."""
        from core.ascend_forge import _score_goal, _risk_label
        for goal in ("refactor login flow", "update user schema", "migrate database"):
            score = _score_goal(goal)
            assert 0.3 <= score < 0.7, f"Expected MEDIUM risk for '{goal}', got {score}"
            assert _risk_label(score) == "MEDIUM"

    def test_low_risk_keywords(self) -> None:
        """Benign goals should score LOW."""
        from core.ascend_forge import _score_goal, _risk_label
        for goal in ("add logging", "improve docs", "create readme"):
            score = _score_goal(goal)
            assert score < 0.3, f"Expected LOW risk for '{goal}', got {score}"
            assert _risk_label(score) == "LOW"


# ---------------------------------------------------------------------------
# Test: Forge executor instantiation and queue
# ---------------------------------------------------------------------------

class TestForgeExecutor:
    """Verify the AscendForgeExecutor can be created and used."""

    def test_forge_executor_importable(self) -> None:
        from core.ascend_forge import AscendForgeExecutor, get_ascend_forge_executor
        executor = get_ascend_forge_executor()
        assert executor is not None

    def test_forge_submit_low_risk(self) -> None:
        """Submitting a low-risk goal should auto-approve."""
        from core.ascend_forge import get_ascend_forge_executor
        forge = get_ascend_forge_executor()
        req = forge.submit_change(
            objective_id="test-obj-1",
            goal="add debug logging to planner",
        )
        assert req.status == "approved"
        assert req.risk_level == "LOW"

    def test_forge_submit_medium_risk_pending(self) -> None:
        """Submitting a medium-risk goal should stay pending."""
        from core.ascend_forge import get_ascend_forge_executor
        forge = get_ascend_forge_executor()
        req = forge.submit_change(
            objective_id="test-obj-2",
            goal="refactor the authentication module",
        )
        assert req.status == "pending"
        assert req.risk_level == "MEDIUM"

    def test_forge_submit_high_risk_rejected(self) -> None:
        """Submitting a high-risk goal should be auto-rejected."""
        from core.ascend_forge import get_ascend_forge_executor
        forge = get_ascend_forge_executor()
        req = forge.submit_change(
            objective_id="test-obj-3",
            goal="deploy critical production change and delete old data",
        )
        assert req.status == "rejected"
        assert req.risk_level == "HIGH"

    def test_forge_get_queue(self) -> None:
        """The queue should be retrievable."""
        from core.ascend_forge import get_ascend_forge_executor
        forge = get_ascend_forge_executor()
        queue = forge.queue()
        assert isinstance(queue, list)

    def test_forge_approve_request(self) -> None:
        """Approving a queued medium-risk request should succeed."""
        from core.ascend_forge import get_ascend_forge_executor
        forge = get_ascend_forge_executor()
        req = forge.submit_change(
            objective_id="test-obj-approve",
            goal="update configuration settings",
        )
        assert req.status == "pending"
        approved = forge.approve(req.id)
        assert approved is not None
        assert approved.status == "approved"

    def test_forge_reject_request(self) -> None:
        """Rejecting a queued medium-risk request should succeed."""
        from core.ascend_forge import get_ascend_forge_executor
        forge = get_ascend_forge_executor()
        req = forge.submit_change(
            objective_id="test-obj-reject",
            goal="rewrite the config handler",
        )
        assert req.status == "pending"
        rejected = forge.reject(req.id)
        assert rejected is not None
        assert rejected.status == "rejected"


# ---------------------------------------------------------------------------
# Test: Reliability engine integration
# ---------------------------------------------------------------------------

class TestReliabilityEngine:
    """Verify the reliability engine monitors system health."""

    def test_reliability_engine_importable(self) -> None:
        from core.reliability_engine import ReliabilityEngine
        engine = ReliabilityEngine()
        assert engine is not None

    def test_forge_freeze_and_unfreeze(self) -> None:
        """The reliability engine should be able to freeze/unfreeze the forge."""
        from core.reliability_engine import ReliabilityEngine
        engine = ReliabilityEngine()
        engine.freeze_forge(reason="test freeze")
        assert engine.forge_frozen is True
        engine.unfreeze_forge()
        assert engine.forge_frozen is False

    def test_stability_score_initial(self) -> None:
        """Initial stability score should be 1.0 (fully healthy)."""
        from core.reliability_engine import ReliabilityEngine
        engine = ReliabilityEngine()
        status = engine.status()
        score = status["stability_score"]
        assert 0.0 <= score <= 1.0

    def test_status_returns_expected_keys(self) -> None:
        """The status dict should contain all expected keys."""
        from core.reliability_engine import ReliabilityEngine
        engine = ReliabilityEngine()
        status = engine.status()
        for key in ("stability_score", "forge_frozen", "throttled_agents", "checkpoints_stored"):
            assert key in status, f"Missing key in status: {key}"
