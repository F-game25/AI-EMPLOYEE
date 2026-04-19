"""Tests for the new regulatory compliance safeguards.

Covers:
  - data_subject_rights_api (GDPR export, delete, summary)
  - hitl_gate (human-in-the-loop approval gate)
  - server.py: REQUIRE_AUTH default, financial-agents gate, blacklight lockdown
  - blacklight.py: legal_review_required enforcement
"""
from __future__ import annotations

import json
import sys
import tempfile
import threading
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_DIR = REPO_ROOT / "runtime"

if str(RUNTIME_DIR) not in sys.path:
    sys.path.insert(0, str(RUNTIME_DIR))


# ═══════════════════════════════════════════════════════════════════════════════
# Data Subject Rights (GDPR)
# ═══════════════════════════════════════════════════════════════════════════════

class TestDataSubjectRights:
    """Verify GDPR export / summary / erase logic against a temporary AI_HOME."""

    def _make_home(self, tmp_path: Path) -> Path:
        """Create a minimal AI_HOME structure with fixture data."""
        state = tmp_path / "state"
        state.mkdir(parents=True)
        # Chat log — two entries for 'user:alice', one for 'user:bob'
        chatlog = state / "chatlog.jsonl"
        chatlog.write_text(
            json.dumps({"user_id": "user:alice", "msg": "hello"}) + "\n"
            + json.dumps({"user_id": "user:alice", "msg": "world"}) + "\n"
            + json.dumps({"user_id": "user:bob",   "msg": "other"}) + "\n",
        )
        # Memory file
        (state / "memory.json").write_text(json.dumps({"clients": [{"id": "c1"}]}))
        # Learning engine state
        (state / "learning_engine.json").write_text(json.dumps({"strategy_weights": {}}))
        return tmp_path

    def test_summary_returns_store_info(self, tmp_path, monkeypatch):
        import core.data_subject_rights_api as dsr
        monkeypatch.setenv("AI_HOME", str(self._make_home(tmp_path)))
        # reload to pick up new AI_HOME
        import importlib
        importlib.reload(dsr)
        result = dsr.summary("user:alice")
        assert result["user_id"] == "user:alice"
        assert "stores" in result
        assert result["stores"]["chatlog"]["records_for_user"] == 2

    def test_export_contains_chatlog_entries(self, tmp_path, monkeypatch):
        import core.data_subject_rights_api as dsr
        monkeypatch.setenv("AI_HOME", str(self._make_home(tmp_path)))
        import importlib
        importlib.reload(dsr)
        result = dsr.export("user:alice")
        assert result["user_id"] == "user:alice"
        chats = result["data"]["chatlog"]
        assert len(chats) == 2
        assert all(e["user_id"] == "user:alice" for e in chats)

    def test_export_excludes_other_users(self, tmp_path, monkeypatch):
        import core.data_subject_rights_api as dsr
        monkeypatch.setenv("AI_HOME", str(self._make_home(tmp_path)))
        import importlib
        importlib.reload(dsr)
        result = dsr.export("user:alice")
        for entry in result["data"]["chatlog"]:
            assert entry.get("user_id") != "user:bob"

    def test_erase_removes_chatlog_entries_for_user(self, tmp_path, monkeypatch):
        import core.data_subject_rights_api as dsr
        home = self._make_home(tmp_path)
        monkeypatch.setenv("AI_HOME", str(home))
        import importlib
        importlib.reload(dsr)
        result = dsr.erase("user:alice", erase_chatlog=True, erase_memory=False, erase_audit=False)
        assert not result["errors"]
        # Bob's entry must survive
        chatlog_path = home / "state" / "chatlog.jsonl"
        lines = [json.loads(l) for l in chatlog_path.read_text().splitlines() if l.strip()]
        assert all(e.get("user_id") != "user:alice" for e in lines)
        assert any(e.get("user_id") == "user:bob" for e in lines)

    def test_erase_deletes_memory_and_learning_files(self, tmp_path, monkeypatch):
        import core.data_subject_rights_api as dsr
        home = self._make_home(tmp_path)
        monkeypatch.setenv("AI_HOME", str(home))
        import importlib
        importlib.reload(dsr)
        result = dsr.erase("user:alice", erase_chatlog=False, erase_memory=True, erase_audit=False)
        assert not result["errors"]
        assert not (home / "state" / "memory.json").exists()
        assert not (home / "state" / "learning_engine.json").exists()

    def test_erase_returns_legal_basis(self, tmp_path, monkeypatch):
        import core.data_subject_rights_api as dsr
        home = self._make_home(tmp_path)
        monkeypatch.setenv("AI_HOME", str(home))
        import importlib
        importlib.reload(dsr)
        result = dsr.erase("user:alice")
        assert "GDPR Article 17" in result["legal_basis"]

    def test_summary_legal_basis_article_15(self, tmp_path, monkeypatch):
        import core.data_subject_rights_api as dsr
        home = self._make_home(tmp_path)
        monkeypatch.setenv("AI_HOME", str(home))
        import importlib
        importlib.reload(dsr)
        result = dsr.summary("user:alice")
        assert "Article 15" in result["legal_basis"]

    def test_export_legal_basis_article_20(self, tmp_path, monkeypatch):
        import core.data_subject_rights_api as dsr
        home = self._make_home(tmp_path)
        monkeypatch.setenv("AI_HOME", str(home))
        import importlib
        importlib.reload(dsr)
        result = dsr.export("user:alice")
        assert "Article 20" in result["legal_basis"]


# ═══════════════════════════════════════════════════════════════════════════════
# HITL Gate
# ═══════════════════════════════════════════════════════════════════════════════

class TestHITLGate:
    """Verify the human-in-the-loop approval gate."""

    def _gate(self):
        from core.hitl_gate import HITLGate
        return HITLGate()  # fresh instance per test

    def test_is_required_for_hitl_agents(self):
        gate = self._gate()
        assert gate.is_required("hr-manager") is True
        assert gate.is_required("recruiter") is True
        assert gate.is_required("lead-scorer") is True
        assert gate.is_required("qualification-agent") is True

    def test_is_not_required_for_normal_agents(self):
        gate = self._gate()
        assert gate.is_required("brand-strategist") is False
        assert gate.is_required("task-orchestrator") is False
        assert gate.is_required("newsletter-bot") is False

    def test_is_required_for_trigger_action_keywords(self):
        gate = self._gate()
        assert gate.is_required("some-agent", action="hire candidate") is True
        assert gate.is_required("some-agent", action="score_lead for company X") is True
        assert gate.is_required("some-agent", action="profile user data") is True

    def test_pending_request_non_blocking(self):
        gate = self._gate()
        result = gate.require_approval(
            agent="recruiter",
            action="send_offer",
            payload={"candidate": "Alice"},
            submitted_by="recruiter-agent",
            blocking=False,
        )
        assert result["status"] == "pending"
        assert result["approved"] is False
        assert "request_id" in result

    def test_approve_resolves_pending(self):
        gate = self._gate()
        result = gate.require_approval(
            agent="hr-manager",
            action="rank_candidate",
            payload={"candidates": ["A", "B"]},
            submitted_by="hr-agent",
            blocking=False,
        )
        rid = result["request_id"]
        assert len(gate.pending_requests()) == 1

        approval = gate.approve(rid, decided_by="operator", reason="Looks good")
        assert approval["ok"] is True
        assert approval["status"] == "approved"

        # Should no longer be pending
        assert len(gate.pending_requests()) == 0

    def test_reject_resolves_pending(self):
        gate = self._gate()
        result = gate.require_approval(
            agent="lead-scorer",
            action="disqualify",
            payload={"lead_id": "l-99"},
            submitted_by="lead-agent",
            blocking=False,
        )
        rid = result["request_id"]
        rejection = gate.reject(rid, decided_by="supervisor", reason="Missing data")
        assert rejection["ok"] is True
        assert rejection["status"] == "rejected"

    def test_double_approve_fails(self):
        gate = self._gate()
        result = gate.require_approval(
            agent="recruiter",
            action="send_offer",
            payload={},
            submitted_by="recruiter",
            blocking=False,
        )
        rid = result["request_id"]
        gate.approve(rid, decided_by="op1")
        second = gate.approve(rid, decided_by="op2")
        assert second["ok"] is False
        assert "already" in second["error"]

    def test_blocking_approval_resolves_in_thread(self):
        gate = self._gate()
        approved_flag = []

        def _approve_after_delay():
            time.sleep(0.05)
            pending = gate.pending_requests()
            if pending:
                gate.approve(pending[0]["id"], decided_by="operator")

        t = threading.Thread(target=_approve_after_delay, daemon=True)
        t.start()

        result = gate.require_approval(
            agent="hr-manager",
            action="hire",
            payload={"candidate": "Bob"},
            submitted_by="hr-agent",
            blocking=True,
            timeout_s=5,
        )
        assert result["approved"] is True
        approved_flag.append(True)
        t.join(timeout=2)
        assert approved_flag

    def test_blocking_timeout_returns_not_approved(self):
        gate = self._gate()
        result = gate.require_approval(
            agent="hr-manager",
            action="hire",
            payload={},
            submitted_by="hr-agent",
            blocking=True,
            timeout_s=1,  # very short — will time out
        )
        assert result["approved"] is False
        assert result["status"] == "timeout"

    def test_get_request_returns_none_for_unknown_id(self):
        gate = self._gate()
        assert gate.get_request("nonexistent-id") is None

    def test_all_requests_returns_all_statuses(self):
        gate = self._gate()
        r1 = gate.require_approval(agent="recruiter", action="hire", payload={},
                                   submitted_by="s", blocking=False)
        r2 = gate.require_approval(agent="lead-scorer", action="score_lead", payload={},
                                   submitted_by="s", blocking=False)
        gate.approve(r1["request_id"], decided_by="op")
        all_reqs = gate.all_requests()
        assert len(all_reqs) == 2


# ═══════════════════════════════════════════════════════════════════════════════
# Blacklight governance lockdown
# ═══════════════════════════════════════════════════════════════════════════════

class TestBlacklightGovernance:
    """Verify that blacklight.start() respects the legal_review_required gate."""

    def test_legal_review_flag_defaults_to_required(self, monkeypatch):
        """Without BLACKLIGHT_LEGAL_REVIEW=1, the flag should be True (review required)."""
        monkeypatch.delenv("BLACKLIGHT_LEGAL_REVIEW", raising=False)
        import importlib
        bl_path = REPO_ROOT / "runtime" / "agents" / "blacklight"
        if str(bl_path) not in sys.path:
            sys.path.insert(0, str(bl_path))
        import blacklight as bl
        importlib.reload(bl)
        assert bl.LEGAL_REVIEW_REQUIRED is True

    def test_start_raises_without_legal_review(self, monkeypatch):
        monkeypatch.delenv("BLACKLIGHT_LEGAL_REVIEW", raising=False)
        import importlib
        bl_path = REPO_ROOT / "runtime" / "agents" / "blacklight"
        if str(bl_path) not in sys.path:
            sys.path.insert(0, str(bl_path))
        import blacklight as bl
        importlib.reload(bl)
        with pytest.raises(RuntimeError, match="BLACKLIGHT_LEGAL_REVIEW"):
            bl.start("test goal")

    def test_legal_review_flag_clears_with_env(self, monkeypatch):
        monkeypatch.setenv("BLACKLIGHT_LEGAL_REVIEW", "1")
        import importlib
        bl_path = REPO_ROOT / "runtime" / "agents" / "blacklight"
        if str(bl_path) not in sys.path:
            sys.path.insert(0, str(bl_path))
        import blacklight as bl
        importlib.reload(bl)
        assert bl.LEGAL_REVIEW_REQUIRED is False

    def test_max_cycles_defaults_to_safe_value(self, monkeypatch):
        """MAX_CYCLES=0 (unlimited) must be overridden to a safe default."""
        monkeypatch.delenv("BLACKLIGHT_MAX_CYCLES", raising=False)
        import importlib
        bl_path = REPO_ROOT / "runtime" / "agents" / "blacklight"
        if str(bl_path) not in sys.path:
            sys.path.insert(0, str(bl_path))
        import blacklight as bl
        importlib.reload(bl)
        assert bl.MAX_CYCLES > 0, "Unlimited autonomous cycles must be prohibited"

    def test_audit_action_function_exists(self):
        bl_path = REPO_ROOT / "runtime" / "agents" / "blacklight"
        if str(bl_path) not in sys.path:
            sys.path.insert(0, str(bl_path))
        import blacklight as bl
        assert callable(getattr(bl, "_audit_action", None))


# ═══════════════════════════════════════════════════════════════════════════════
# Server.py compliance settings
# ═══════════════════════════════════════════════════════════════════════════════

class TestServerComplianceSettings:
    """Verify server.py compliance defaults without starting the server."""

    def test_require_auth_default_is_one(self, monkeypatch):
        """REQUIRE_AUTH should default to enabled (1) if not set."""
        monkeypatch.delenv("REQUIRE_AUTH", raising=False)
        server_path = REPO_ROOT / "runtime" / "agents" / "problem-solver-ui" / "server.py"
        src = server_path.read_text()
        # The default fallback in os.environ.get must be "1", not "0"
        assert 'os.environ.get("REQUIRE_AUTH", "1")' in src, (
            "REQUIRE_AUTH default must be '1' (auth enforced by default)"
        )

    def test_financial_agents_disabled_by_default(self, monkeypatch):
        """ENABLE_FINANCIAL_AGENTS must default to disabled."""
        server_path = REPO_ROOT / "runtime" / "agents" / "problem-solver-ui" / "server.py"
        src = server_path.read_text()
        assert 'ENABLE_FINANCIAL_AGENTS", "0"' in src, (
            "Financial agents must be DISABLED (0) by default"
        )

    def test_financial_agent_ids_list_is_defined(self):
        server_path = REPO_ROOT / "runtime" / "agents" / "problem-solver-ui" / "server.py"
        src = server_path.read_text()
        for agent_id in ("turbo-quant", "arbitrage-bot", "polymarket-trader"):
            assert agent_id in src

    def test_financial_disclaimer_text_present(self):
        server_path = REPO_ROOT / "runtime" / "agents" / "problem-solver-ui" / "server.py"
        src = server_path.read_text()
        assert "FINANCIAL DISCLAIMER" in src
        assert "does NOT constitute financial advice" in src

    def test_gdpr_endpoints_registered(self):
        server_path = REPO_ROOT / "runtime" / "agents" / "problem-solver-ui" / "server.py"
        src = server_path.read_text()
        assert '"/data/summary"' in src
        assert '"/data/export"' in src
        assert '"/data/delete"' in src

    def test_hitl_endpoints_registered(self):
        server_path = REPO_ROOT / "runtime" / "agents" / "problem-solver-ui" / "server.py"
        src = server_path.read_text()
        assert '"/api/hitl/pending"' in src
        assert '"/api/hitl/requests"' in src
        assert "/approve" in src
        assert "/reject" in src

    def test_blacklight_legal_review_enforced_in_start(self):
        server_path = REPO_ROOT / "runtime" / "agents" / "problem-solver-ui" / "server.py"
        src = server_path.read_text()
        assert "BLACKLIGHT_LEGAL_REVIEW" in src
        assert "403" in src  # must return HTTP 403 when gate blocks

    def test_hitl_gate_triggered_for_high_risk_agents(self):
        server_path = REPO_ROOT / "runtime" / "agents" / "problem-solver-ui" / "server.py"
        src = server_path.read_text()
        assert "_get_hitl_gate" in src
        assert "hitl_gate_triggered" in src

    def test_core_compliance_modules_created(self):
        assert (RUNTIME_DIR / "core" / "data_subject_rights_api.py").exists()
        assert (RUNTIME_DIR / "core" / "hitl_gate.py").exists()
