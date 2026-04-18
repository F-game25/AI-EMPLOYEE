"""Tests for the enterprise hardening modules:
  - core.audit_engine
  - core.security_layer
  - core.reliability_engine
  - core.ascend_forge (hardened)
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from unittest.mock import patch

import pytest

_RUNTIME = Path(__file__).parent.parent / "runtime"
if str(_RUNTIME) not in sys.path:
    sys.path.insert(0, str(_RUNTIME))


# ─────────────────────────────────────────────────────────────────────────────
# AuditEngine
# ─────────────────────────────────────────────────────────────────────────────

class TestAuditEngine:
    def _engine(self, tmp_path: Path):
        os.environ["AI_HOME"] = str(tmp_path)
        from core.audit_engine import AuditEngine
        return AuditEngine(db_path=tmp_path / "audit.db")

    def test_record_returns_event_with_required_fields(self, tmp_path):
        engine = self._engine(tmp_path)
        evt = engine.record(actor="agent-1", action="memory_write", input_data={"key": "x"})
        assert evt["actor"] == "agent-1"
        assert evt["action"] == "memory_write"
        assert "id" in evt and "ts" in evt
        assert 0.0 <= evt["risk_score"] <= 1.0

    def test_risk_auto_classification(self, tmp_path):
        engine = self._engine(tmp_path)
        low = engine.record(actor="sys", action="status_check")
        mid = engine.record(actor="sys", action="memory_write")
        high = engine.record(actor="sys", action="forge_deploy")
        assert low["risk_score"] < 0.3
        assert 0.3 <= mid["risk_score"] < 0.7
        assert high["risk_score"] >= 0.7

    def test_risk_score_can_be_overridden(self, tmp_path):
        engine = self._engine(tmp_path)
        evt = engine.record(actor="sys", action="custom_action", risk_score=0.99)
        assert evt["risk_score"] == pytest.approx(0.99)

    def test_recent_returns_most_recent_first(self, tmp_path):
        engine = self._engine(tmp_path)
        engine.record(actor="a", action="first_action")
        engine.record(actor="a", action="second_action")
        recent = engine.recent(10)
        assert recent[0]["action"] == "second_action"

    def test_recent_filters_by_actor(self, tmp_path):
        engine = self._engine(tmp_path)
        engine.record(actor="agent-x", action="act1")
        engine.record(actor="agent-y", action="act2")
        results = engine.recent(10, actor="agent-x")
        assert all(r["actor"] == "agent-x" for r in results)

    def test_recent_filters_by_min_risk(self, tmp_path):
        engine = self._engine(tmp_path)
        engine.record(actor="s", action="low_action", risk_score=0.1)
        engine.record(actor="s", action="high_action", risk_score=0.9)
        high_only = engine.recent(10, min_risk=0.6)
        assert all(r["risk_score"] >= 0.6 for r in high_only)

    def test_stats_returns_summary(self, tmp_path):
        engine = self._engine(tmp_path)
        engine.record(actor="a", action="act", risk_score=0.1)
        engine.record(actor="b", action="forge_deploy", risk_score=0.85)
        stats = engine.stats()
        assert stats["total"] >= 2
        assert stats["risk_distribution"]["high"] >= 1

    def test_persistence_survives_reinit(self, tmp_path):
        engine = self._engine(tmp_path)
        engine.record(actor="persist-test", action="saved_action")
        from core.audit_engine import AuditEngine
        engine2 = AuditEngine(db_path=tmp_path / "audit.db")
        results = engine2.recent(10, actor="persist-test")
        assert len(results) >= 1
        assert results[0]["action"] == "saved_action"

    def test_anomaly_flagged_on_burst_of_high_risk(self, tmp_path):
        engine = self._engine(tmp_path)
        for i in range(6):
            engine.record(actor="attacker", action="forge_deploy", risk_score=0.85)
        anomalies = engine.anomalies()
        assert len(anomalies) >= 1
        assert anomalies[0]["type"] == "high_risk_burst"


# ─────────────────────────────────────────────────────────────────────────────
# SecurityLayer
# ─────────────────────────────────────────────────────────────────────────────

class TestSecurityLayer:
    def _layer(self):
        from core.security_layer import SecurityLayer
        return SecurityLayer()

    def test_agent_is_untrusted_by_default(self):
        from core.security_layer import FORGE_ACCESS
        sl = self._layer()
        assert not sl.has_permission("new-agent", FORGE_ACCESS)

    def test_grant_and_check_permission(self):
        from core.security_layer import MEMORY_WRITE
        sl = self._layer()
        sl.grant("agent-a", {MEMORY_WRITE})
        assert sl.has_permission("agent-a", MEMORY_WRITE)

    def test_require_raises_when_permission_missing(self):
        from core.security_layer import TOOL_EXECUTION, PermissionDeniedError
        sl = self._layer()
        with pytest.raises(PermissionDeniedError):
            sl.require("untrusted", TOOL_EXECUTION, action="run_tool")

    def test_require_passes_when_permission_granted(self):
        from core.security_layer import ECONOMY_ACTIONS
        sl = self._layer()
        sl.grant("econ-agent", {ECONOMY_ACTIONS})
        sl.require("econ-agent", ECONOMY_ACTIONS, action="economy_action")  # must not raise

    def test_revoke_removes_single_permission(self):
        from core.security_layer import FORGE_ACCESS, MEMORY_WRITE
        sl = self._layer()
        sl.grant("multi", {FORGE_ACCESS, MEMORY_WRITE})
        sl.revoke("multi", {FORGE_ACCESS})
        assert not sl.has_permission("multi", FORGE_ACCESS)
        assert sl.has_permission("multi", MEMORY_WRITE)

    def test_revoke_all_removes_agent(self):
        from core.security_layer import FORGE_ACCESS
        sl = self._layer()
        sl.grant("temp-agent", {FORGE_ACCESS})
        sl.revoke("temp-agent")
        assert not sl.has_permission("temp-agent", FORGE_ACCESS)

    def test_grant_unknown_permission_raises(self):
        sl = self._layer()
        with pytest.raises(ValueError):
            sl.grant("a", {"nonexistent_perm"})

    def test_validate_input_accepts_clean_payload(self):
        sl = self._layer()
        sl.validate_input({"goal": "increase conversion"}, required_keys=["goal"])

    def test_validate_input_rejects_non_dict(self):
        sl = self._layer()
        with pytest.raises(ValueError):
            sl.validate_input("bad string")

    def test_validate_input_rejects_shell_injection(self):
        sl = self._layer()
        with pytest.raises(ValueError, match="disallowed"):
            sl.validate_input({"goal": "do it; rm -rf /"})

    def test_validate_input_rejects_missing_required_keys(self):
        sl = self._layer()
        with pytest.raises(ValueError, match="missing required"):
            sl.validate_input({"foo": "bar"}, required_keys=["goal"])

    def test_sandbox_check_flags_dangerous_code(self):
        sl = self._layer()
        result = sl.sandbox_check("import subprocess; subprocess.run(['ls'])")
        assert not result["safe"]
        assert "subprocess" in result["violations"]

    def test_sandbox_check_passes_safe_code(self):
        sl = self._layer()
        result = sl.sandbox_check("x = 1 + 1\nprint(x)")
        assert result["safe"]
        assert result["violations"] == []

    def test_validate_forge_operation_requires_permission(self):
        from core.security_layer import FORGE_ACCESS, PermissionDeniedError
        sl = self._layer()
        with pytest.raises(PermissionDeniedError):
            sl.validate_forge_operation("no-perms", {"goal": "do something"})

    def test_validate_forge_operation_passes_with_permission(self):
        from core.security_layer import FORGE_ACCESS
        sl = self._layer()
        sl.grant("forge-agent", {FORGE_ACCESS})
        sl.validate_forge_operation("forge-agent", {"goal": "update config"})  # must not raise


# ─────────────────────────────────────────────────────────────────────────────
# ReliabilityEngine
# ─────────────────────────────────────────────────────────────────────────────

class TestReliabilityEngine:
    def _engine(self):
        from core.reliability_engine import ReliabilityEngine
        return ReliabilityEngine()

    def test_initial_status_is_healthy(self):
        eng = self._engine()
        status = eng.status()
        assert status["forge_frozen"] is False
        assert status["stability_score"] == pytest.approx(1.0)

    def test_freeze_and_unfreeze_forge(self):
        eng = self._engine()
        eng.freeze_forge(reason="test")
        assert eng.forge_frozen is True
        eng.unfreeze_forge()
        assert eng.forge_frozen is False

    def test_save_and_retrieve_checkpoint(self):
        eng = self._engine()
        cid = eng.save_checkpoint({"state": "v1", "mode": "OFF"})
        assert cid.startswith("ckpt-")
        ckpt = eng.last_checkpoint()
        assert ckpt is not None
        assert ckpt["state"]["state"] == "v1"

    def test_checkpoints_limit_and_order(self):
        eng = self._engine()
        eng.save_checkpoint({"v": 1})
        eng.save_checkpoint({"v": 2})
        eng.save_checkpoint({"v": 3})
        ckpts = eng.checkpoints(3)
        assert ckpts[0]["state"]["v"] == 3  # newest first

    def test_throttle_and_unthrottle_agent(self):
        eng = self._engine()
        eng.throttle_agent("slow-agent")
        assert eng.is_throttled("slow-agent")
        eng.unthrottle_agent("slow-agent")
        assert not eng.is_throttled("slow-agent")

    def test_evaluate_freezes_forge_on_high_error_rate(self, tmp_path):
        os.environ["AI_HOME"] = str(tmp_path)
        from core.reliability_engine import ReliabilityEngine
        eng = ReliabilityEngine()
        # Patch MetricsCollector to report high error rate
        mock_snapshot = {"latest": {"errors_per_minute": 15}, "history": []}
        with patch("core.reliability_engine.ReliabilityEngine._get_metrics", return_value=mock_snapshot), \
             patch("core.reliability_engine.ReliabilityEngine._get_anomalies", return_value=[]), \
             patch("core.reliability_engine.ReliabilityEngine._get_audit_anomalies", return_value=[]):
            result = eng.evaluate()
        assert result["forge_frozen"] is True
        assert result["stability_score"] < 1.0

    def test_evaluate_does_not_freeze_on_low_error_rate(self, tmp_path):
        os.environ["AI_HOME"] = str(tmp_path)
        from core.reliability_engine import ReliabilityEngine
        eng = ReliabilityEngine()
        mock_snapshot = {"latest": {"errors_per_minute": 0}, "history": []}
        with patch("core.reliability_engine.ReliabilityEngine._get_metrics", return_value=mock_snapshot), \
             patch("core.reliability_engine.ReliabilityEngine._get_anomalies", return_value=[]), \
             patch("core.reliability_engine.ReliabilityEngine._get_audit_anomalies", return_value=[]):
            result = eng.evaluate()
        assert result["forge_frozen"] is False
        assert result["stability_score"] == pytest.approx(1.0)


# ─────────────────────────────────────────────────────────────────────────────
# AscendForge (hardened)
# ─────────────────────────────────────────────────────────────────────────────

class TestAscendForgeHardened:
    def _forge(self):
        from core.ascend_forge import AscendForgeExecutor
        return AscendForgeExecutor()

    def test_low_risk_goal_auto_approved(self):
        forge = self._forge()
        req = forge.submit_change(
            objective_id="obj-1", goal="analyze performance metrics"
        )
        assert req.risk_level == "LOW"
        assert req.status == "approved"

    def test_high_risk_goal_auto_rejected(self):
        forge = self._forge()
        req = forge.submit_change(
            objective_id="obj-2", goal="delete all data and deploy to production"
        )
        assert req.risk_level == "HIGH"
        assert req.status == "rejected"

    def test_medium_risk_goal_is_pending(self):
        forge = self._forge()
        req = forge.submit_change(
            objective_id="obj-3", goal="refactor the authentication module"
        )
        assert req.risk_level == "MEDIUM"
        assert req.status == "pending"

    def test_approve_pending_request(self):
        forge = self._forge()
        req = forge.submit_change(objective_id="obj-4", goal="update config values")
        assert req.status == "pending"
        approved = forge.approve(req.id, approved_by="operator")
        assert approved.status == "approved"
        assert approved.decided_by == "operator"

    def test_reject_pending_request(self):
        forge = self._forge()
        req = forge.submit_change(objective_id="obj-5", goal="change database schema")
        rejected = forge.reject(req.id, rejected_by="operator")
        assert rejected.status == "rejected"

    def test_approve_nonexistent_request_returns_none(self):
        forge = self._forge()
        result = forge.approve("does-not-exist")
        assert result is None

    def test_queue_returns_all_requests(self):
        forge = self._forge()
        forge.submit_change(objective_id="q1", goal="check baseline")
        forge.submit_change(objective_id="q2", goal="update metrics")
        q = forge.queue()
        assert len(q) >= 2

    def test_queue_filter_by_status(self):
        forge = self._forge()
        forge.submit_change(objective_id="f1", goal="low risk check")
        pending = forge.queue(status="pending")
        approved = forge.queue(status="approved")
        for item in pending:
            assert item["status"] == "pending"
        for item in approved:
            assert item["status"] == "approved"

    def test_execute_objective_legacy_compat(self):
        forge = self._forge()
        result = forge.execute_objective(
            objective_id="legacy-1", goal="analyze baseline performance"
        )
        assert "request_id" in result
        assert "risk_level" in result
        assert result["status"] in ("running", "approved", "pending", "rejected")

    def test_sandbox_test_marks_safe_request(self):
        forge = self._forge()
        req = forge.submit_change(objective_id="sb-1", goal="low risk analysis")
        assert req.status == "approved"
        tested = forge.sandbox_test(req.id)
        assert tested is not None
        assert tested.sandbox_result is not None
