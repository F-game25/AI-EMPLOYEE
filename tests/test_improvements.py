"""Tests for the 5 system improvements:

1. Agent Governor  – /api/agents/governor
2. Dashboard Cache – /api/status TTL caching
3. Email Deliverability Audit – /api/email/deliverability-audit
4. Circuit Breaker – /api/agents/circuit-breakers
5. Lead Gen Pilot  – /api/lead-pilot
"""
from __future__ import annotations

import importlib
import importlib.util
import json
import sys
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# ── Path setup ────────────────────────────────────────────────────────────────

_SERVER_PATH = (
    Path(__file__).parent.parent
    / "runtime" / "agents" / "problem-solver-ui" / "server.py"
)


def _load_server(tmp_path: Path):
    """Load server.py with AI_HOME redirected to tmp_path."""
    import os

    fake_home = tmp_path / "ai-employee"
    fake_home.mkdir(parents=True, exist_ok=True)
    (fake_home / "state").mkdir(exist_ok=True)
    (fake_home / "run").mkdir(exist_ok=True)
    (fake_home / "agents").mkdir(exist_ok=True)
    os.environ["AI_HOME"] = str(fake_home)

    # Force a fresh import so module-level constants use the new AI_HOME
    spec = importlib.util.spec_from_file_location("server_test", _SERVER_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ─────────────────────────────────────────────────────────────────────────────
# Shared fixture
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture()
def server(tmp_path):
    """Load server module and return (module, TestClient)."""
    mod = _load_server(tmp_path)
    client = TestClient(mod.app, raise_server_exceptions=True)
    return mod, client


# ═══════════════════════════════════════════════════════════════════════════
# 1. Agent Governor
# ═══════════════════════════════════════════════════════════════════════════

class TestAgentGovernor:
    def test_get_governor_defaults(self, server):
        mod, client = server
        r = client.get("/api/agents/governor")
        assert r.status_code == 200
        body = r.json()
        assert body["enabled"] is True
        assert body["max_agents"] == 56
        assert "running" in body
        assert "headroom" in body

    def test_set_governor_max_agents(self, server):
        mod, client = server
        r = client.post(
            "/api/agents/governor",
            json={"max_agents": 10},
            headers={"Authorization": "Bearer skip"},
        )
        # Auth may reject or pass depending on env; accept 200 or 401
        if r.status_code == 200:
            assert r.json()["max_agents"] == 10
        else:
            assert r.status_code in (401, 403)

    def test_governor_enforced_in_count_running(self, server):
        mod, _ = server
        # No PID files exist → 0 agents running
        count = mod._count_running_agents()
        assert count == 0

    def test_set_governor_invalid_cap(self, server):
        mod, client = server
        # Bypass auth by patching require_auth
        with patch.object(mod, "require_auth", return_value=None):
            r = client.post(
                "/api/agents/governor",
                json={"max_agents": 0},
            )
        assert r.status_code == 400

    def test_set_governor_disable(self, server):
        mod, client = server
        with patch.object(mod, "require_auth", return_value=None):
            r = client.post(
                "/api/agents/governor",
                json={"enabled": False},
            )
        assert r.status_code == 200
        assert r.json()["enabled"] is False
        assert r.json()["headroom"] is None  # headroom is None when disabled


class TestEnterpriseLifecycle:
    def test_start_all_blocked_during_shutdown(self, server):
        mod, client = server
        mod._SHUTDOWN_IN_PROGRESS.set()
        try:
            r = client.post("/api/agents/start-all")
            assert r.status_code == 409
            body = r.json()
            assert body["ok"] is False
            assert "Shutdown is in progress" in body["error"]
        finally:
            mod._SHUTDOWN_IN_PROGRESS.clear()

    def test_start_bot_prevents_duplicate_instance(self, server):
        mod, client = server
        with patch.object(mod, "_agent_has_live_process", return_value=True), patch.object(mod, "ai_employee") as ai_cmd:
            r = client.post("/api/agents/start", json={"bot": "lead-generator"})
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True
        assert body["already_running"] is True
        ai_cmd.assert_not_called()

    def test_stop_agents_enterprise_batch_report(self, server):
        mod, _ = server
        with patch.object(
            mod,
            "_discover_agent_pids",
            side_effect=[{101, 102}, {201}],
        ), patch.object(
            mod,
            "_signal_pid_and_group",
            return_value=True,
        ), patch.object(
            mod,
            "_pid_alive",
            return_value=False,
        ), patch.object(
            mod,
            "_cleanup_agent_runtime_files",
            return_value=None,
        ), patch.object(
            mod,
            "_write_stopped_state",
            return_value=None,
        ):
            result = mod._stop_agents_enterprise(["lead-generator", "offer-agent"])

        assert result["failed"] == []
        assert result["stopped"] == 2
        assert result["graceful_signaled"] == 3
        assert result["force_signaled"] == 0
        assert result["remaining_pids"] == []


# ═══════════════════════════════════════════════════════════════════════════
# 2. Dashboard Status Cache
# ═══════════════════════════════════════════════════════════════════════════

class TestDashboardCache:
    def test_cache_miss_then_hit(self, server):
        mod, _ = server
        mod._invalidate_status_cache()
        assert mod._get_cached_status() is None
        mod._set_cached_status({"running": 3, "ts": "2026-01-01T00:00:00Z"})
        cached = mod._get_cached_status()
        assert cached is not None
        assert cached["running"] == 3

    def test_cache_expires(self, server):
        mod, _ = server
        # Temporarily set TTL to 0 to force expiry
        original_ttl = mod._STATUS_CACHE_TTL
        mod._STATUS_CACHE_TTL = 0.0
        mod._set_cached_status({"running": 5})
        time.sleep(0.01)
        assert mod._get_cached_status() is None
        mod._STATUS_CACHE_TTL = original_ttl

    def test_invalidate_clears_cache(self, server):
        mod, _ = server
        mod._set_cached_status({"running": 7})
        mod._invalidate_status_cache()
        assert mod._get_cached_status() is None

    def test_status_endpoint_includes_governor(self, server):
        mod, client = server
        mod._invalidate_status_cache()
        r = client.get("/api/status")
        assert r.status_code == 200
        body = r.json()
        assert "governor" in body
        assert "max_agents" in body["governor"]
        assert "enabled" in body["governor"]

    def test_status_cache_thread_safety(self, server):
        """Multiple threads should not corrupt the cache."""
        mod, _ = server
        errors = []

        def writer():
            for _ in range(50):
                mod._set_cached_status({"running": 1})

        def reader():
            for _ in range(50):
                val = mod._get_cached_status()
                if val is not None and not isinstance(val, dict):
                    errors.append("bad type")

        threads = [threading.Thread(target=writer) for _ in range(3)]
        threads += [threading.Thread(target=reader) for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors


# ═══════════════════════════════════════════════════════════════════════════
# 3. Email Deliverability Audit
# ═══════════════════════════════════════════════════════════════════════════

class TestDeliverabilityAudit:
    def test_audit_campaign_clean(self, server):
        mod, _ = server
        campaign = {
            "id": "c1",
            "name": "Good Campaign",
            "subject": "Hey, wanted to share something",
            "body": "Hi there! Click the link below to unsubscribe.",
        }
        result = mod._audit_campaign(campaign)
        assert result["id"] == "c1"
        assert result["score"] >= 75
        assert result["rating"] in ("good", "needs_work", "poor")

    def test_audit_campaign_spam_triggers(self, server):
        mod, _ = server
        campaign = {
            "id": "c2",
            "name": "Spammy",
            "subject": "FREE MONEY click here guaranteed",
            "body": "Act now! Limited time! No risk! Winner! Unsubscribe below.",
        }
        result = mod._audit_campaign(campaign)
        assert result["score"] < 100
        issue_types = [i["type"] for i in result["issues"]]
        assert "spam_trigger" in issue_types

    def test_audit_campaign_missing_unsubscribe(self, server):
        mod, _ = server
        campaign = {
            "id": "c3",
            "name": "No Unsub",
            "subject": "Hello",
            "body": "Buy our product now.",
        }
        result = mod._audit_campaign(campaign)
        issue_types = [i["type"] for i in result["issues"]]
        assert "missing_unsubscribe" in issue_types

    def test_audit_campaign_empty_subject(self, server):
        mod, _ = server
        campaign = {"id": "c4", "name": "No Subject", "subject": "", "body": "Some body unsubscribe"}
        result = mod._audit_campaign(campaign)
        issue_types = [i["type"] for i in result["issues"]]
        assert "empty_subject" in issue_types

    def test_audit_campaign_long_subject(self, server):
        mod, _ = server
        campaign = {
            "id": "c5",
            "name": "Long Subject",
            "subject": "A" * 65,
            "body": "body text here unsubscribe",
        }
        result = mod._audit_campaign(campaign)
        issue_types = [i["type"] for i in result["issues"]]
        assert "long_subject" in issue_types

    def test_audit_endpoint_returns_structure(self, server):
        mod, client = server
        # Mock out _email_mktg to avoid the real module dependency
        mock_email = MagicMock()
        mock_email.list_campaigns.return_value = [
            {"id": "x1", "name": "T", "subject": "Hello", "body": "hi unsubscribe"},
        ]
        with patch.object(mod, "_email_mktg", return_value=mock_email):
            r = client.get("/api/email/deliverability-audit")
        assert r.status_code == 200
        body = r.json()
        assert "overall_score" in body
        assert "campaigns_audited" in body
        assert "dns_checklist" in body
        assert "campaigns" in body
        assert "sender_reputation_tools" in body

    def test_audit_endpoint_empty_campaigns(self, server):
        mod, client = server
        mock_email = MagicMock()
        mock_email.list_campaigns.return_value = []
        with patch.object(mod, "_email_mktg", return_value=mock_email):
            r = client.get("/api/email/deliverability-audit")
        assert r.status_code == 200
        body = r.json()
        assert body["campaigns_audited"] == 0
        assert body["overall_score"] is None  # no data — not misleadingly perfect


# ═══════════════════════════════════════════════════════════════════════════
# 4. Circuit Breaker
# ═══════════════════════════════════════════════════════════════════════════

class TestCircuitBreaker:
    def test_initial_state_closed(self, server):
        mod, _ = server
        mod._CIRCUIT_BREAKERS.clear()
        state = mod._cb_get("test-agent")
        assert state["state"] == "closed"
        assert state["failures"] == 0

    def test_record_failure_increments(self, server):
        mod, _ = server
        mod._CIRCUIT_BREAKERS.clear()
        mod.circuit_breaker_record_failure("agent-a")
        mod.circuit_breaker_record_failure("agent-a")
        state = mod._cb_get("agent-a")
        assert state["failures"] == 2
        assert state["state"] == "closed"

    def test_breaker_opens_at_threshold(self, server):
        mod, _ = server
        mod._CIRCUIT_BREAKERS.clear()
        for _ in range(mod._CB_FAILURE_THRESHOLD):
            mod.circuit_breaker_record_failure("agent-b")
        state = mod._cb_get("agent-b")
        assert state["state"] == "open"

    def test_is_open_returns_true_when_open(self, server):
        mod, _ = server
        mod._CIRCUIT_BREAKERS.clear()
        for _ in range(mod._CB_FAILURE_THRESHOLD):
            mod.circuit_breaker_record_failure("agent-c")
        assert mod.circuit_breaker_is_open("agent-c") is True

    def test_success_resets_failures(self, server):
        mod, _ = server
        mod._CIRCUIT_BREAKERS.clear()
        mod.circuit_breaker_record_failure("agent-d")
        mod.circuit_breaker_record_success("agent-d")
        state = mod._cb_get("agent-d")
        assert state["failures"] == 0

    def test_half_open_closes_after_successes(self, server):
        mod, _ = server
        mod._CIRCUIT_BREAKERS.clear()
        # Open the breaker
        for _ in range(mod._CB_FAILURE_THRESHOLD):
            mod.circuit_breaker_record_failure("agent-e")
        # Manually set to half_open (simulating elapsed cooldown)
        mod._CIRCUIT_BREAKERS["agent-e"]["state"] = "half_open"
        # Record enough successes to close
        for _ in range(mod._CB_SUCCESS_TO_CLOSE):
            mod.circuit_breaker_record_success("agent-e")
        assert mod._cb_get("agent-e")["state"] == "closed"

    def test_get_circuit_breakers_endpoint(self, server):
        mod, client = server
        mod._CIRCUIT_BREAKERS.clear()
        mod.circuit_breaker_record_failure("test-agent-1")
        r = client.get("/api/agents/circuit-breakers")
        assert r.status_code == 200
        body = r.json()
        assert "circuit_breakers" in body
        assert "thresholds" in body
        assert "summary" in body
        assert "test-agent-1" in body["circuit_breakers"]

    def test_reset_endpoint(self, server):
        mod, client = server
        mod._CIRCUIT_BREAKERS.clear()
        for _ in range(mod._CB_FAILURE_THRESHOLD):
            mod.circuit_breaker_record_failure("reset-agent")
        assert mod._cb_get("reset-agent")["state"] == "open"
        with patch.object(mod, "require_auth", return_value=None):
            r = client.post("/api/agents/circuit-breakers/reset-agent/reset")
        assert r.status_code == 200
        assert r.json()["state"] == "closed"

    def test_reset_endpoint_invalid_agent_id(self, server):
        mod, client = server
        with patch.object(mod, "require_auth", return_value=None):
            r = client.post("/api/agents/circuit-breakers/../../evil/reset")
        assert r.status_code in (400, 404, 422)

    def test_record_failure_endpoint(self, server):
        mod, client = server
        mod._CIRCUIT_BREAKERS.clear()
        with patch.object(mod, "require_auth", return_value=None):
            r = client.post("/api/agents/circuit-breakers/my-agent/record-failure")
        assert r.status_code == 200
        assert r.json()["failures"] == 1

    def test_record_success_endpoint(self, server):
        mod, client = server
        mod._CIRCUIT_BREAKERS.clear()
        with patch.object(mod, "require_auth", return_value=None):
            r = client.post("/api/agents/circuit-breakers/my-agent/record-success")
        assert r.status_code == 200
        assert r.json()["success_streak"] == 1

    def test_unknown_agent_is_not_open(self, server):
        mod, _ = server
        mod._CIRCUIT_BREAKERS.clear()
        assert mod.circuit_breaker_is_open("never-seen-agent") is False

    def test_subtask_complete_endpoint_done(self, server):
        mod, client = server
        # Create a plan with a subtask
        import uuid
        task_id = uuid.uuid4().hex[:12]
        plan = {
            "id": task_id,
            "title": "Test task",
            "status": "running",
            "subtasks": [{"subtask_id": "st1", "agent_id": "test-agent", "status": "pending"}],
            "created_at": "2026-01-01T00:00:00Z",
        }
        mod._save_task_plans([plan])
        mod._CIRCUIT_BREAKERS.clear()
        r = client.post(
            "/api/task/subtask-complete",
            json={"task_id": task_id, "subtask_id": "st1", "status": "done"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True
        assert body["status"] == "done"
        assert "circuit_breaker" in body

    def test_subtask_complete_endpoint_failed(self, server):
        mod, client = server
        import uuid
        task_id = uuid.uuid4().hex[:12]
        plan = {
            "id": task_id,
            "title": "Test task 2",
            "status": "running",
            "subtasks": [{"subtask_id": "st2", "agent_id": "failing-agent", "status": "pending"}],
            "created_at": "2026-01-01T00:00:00Z",
        }
        mod._save_task_plans([plan])
        mod._CIRCUIT_BREAKERS.clear()
        r = client.post(
            "/api/task/subtask-complete",
            json={"task_id": task_id, "subtask_id": "st2", "status": "failed"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True
        assert body["circuit_breaker"]["failures"] == 1


# ═══════════════════════════════════════════════════════════════════════════
# 5. Lead Gen Pilot
# ═══════════════════════════════════════════════════════════════════════════

class TestLeadPilot:
    def test_get_pilot_defaults(self, server):
        mod, client = server
        # Reset to defaults
        mod._LEAD_PILOT.update({"enabled": False, "max_leads": 5, "niche": "web design agencies"})
        r = client.get("/api/lead-pilot")
        assert r.status_code == 200
        body = r.json()
        assert body["enabled"] is False
        assert body["max_leads"] == 5
        assert "web design" in body["niche"]

    def test_enable_pilot(self, server):
        mod, client = server
        with patch.object(mod, "require_auth", return_value=None):
            r = client.post("/api/lead-pilot", json={"enabled": True})
        assert r.status_code == 200
        assert r.json()["enabled"] is True

    def test_set_niche(self, server):
        mod, client = server
        with patch.object(mod, "require_auth", return_value=None):
            r = client.post("/api/lead-pilot", json={"niche": "e-commerce brands"})
        assert r.status_code == 200
        assert r.json()["niche"] == "e-commerce brands"

    def test_set_max_leads_valid(self, server):
        mod, client = server
        with patch.object(mod, "require_auth", return_value=None):
            r = client.post("/api/lead-pilot", json={"max_leads": 3})
        assert r.status_code == 200
        assert r.json()["max_leads"] == 3

    def test_set_max_leads_too_high(self, server):
        mod, client = server
        with patch.object(mod, "require_auth", return_value=None):
            r = client.post("/api/lead-pilot", json={"max_leads": 100})
        assert r.status_code == 400

    def test_set_max_leads_zero(self, server):
        mod, client = server
        with patch.object(mod, "require_auth", return_value=None):
            r = client.post("/api/lead-pilot", json={"max_leads": 0})
        assert r.status_code == 400

    def test_set_empty_niche_rejected(self, server):
        mod, client = server
        with patch.object(mod, "require_auth", return_value=None):
            r = client.post("/api/lead-pilot", json={"niche": "   "})
        assert r.status_code == 400

    def test_pilot_updated_at_set(self, server):
        mod, client = server
        with patch.object(mod, "require_auth", return_value=None):
            r = client.post("/api/lead-pilot", json={"enabled": True})
        assert r.status_code == 200
        assert r.json()["updated_at"] is not None

    def test_pilot_state_persists_in_module(self, server):
        mod, client = server
        with patch.object(mod, "require_auth", return_value=None):
            client.post("/api/lead-pilot", json={"niche": "SaaS startups", "max_leads": 4})
        r = client.get("/api/lead-pilot")
        body = r.json()
        assert body["niche"] == "SaaS startups"
        assert body["max_leads"] == 4
