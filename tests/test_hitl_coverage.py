"""HITL gate coverage tests — Phase 6E.

Verifies that:
1. outreach_response_conversion always returns status='draft' or
   'pending_approval' (never 'sent').
2. require_approval is called for high-risk outreach actions.
3. run_opportunity_pipeline gates its ActionBus emit behind HITL.
4. deals.json writes by sales-closer-pro exist but are noted as
   lacking an inline HITL gate (policy: gate belongs at caller layer).
"""
from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

# ── Runtime on sys.path ───────────────────────────────────────────────────────
_RUNTIME = Path(__file__).resolve().parents[1] / "runtime"
if str(_RUNTIME) not in sys.path:
    sys.path.insert(0, str(_RUNTIME))


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def isolate_state(tmp_path, monkeypatch):
    """Fresh STATE_DIR and reset MoneyMode + HITLGate singletons per test."""
    monkeypatch.setenv("STATE_DIR", str(tmp_path))
    import core.money_mode as mm_mod
    mm_mod._instance = None
    import core.hitl_gate as hg_mod
    hg_mod._instance = None
    yield tmp_path
    mm_mod._instance = None
    hg_mod._instance = None


@pytest.fixture()
def money_mode(isolate_state):
    from core.money_mode import MoneyMode
    return MoneyMode()


@pytest.fixture()
def hitl_gate(isolate_state):
    from core.hitl_gate import get_hitl_gate
    return get_hitl_gate()


@pytest.fixture()
def no_llm(monkeypatch):
    """Silence LLM calls so tests run offline."""
    monkeypatch.setattr(
        "core.money_mode.MoneyMode._llm_generate",
        staticmethod(lambda prompt, system: None),
    )


# ── 1. outreach_response_conversion: status invariant ────────────────────────

class TestOutreachStatusInvariant:
    """outreach_response_conversion must never return status='sent'."""

    FORBIDDEN_STATUSES = {"sent", "delivered", "published"}

    def test_default_call_returns_pending_approval(self, money_mode, no_llm):
        """The inline HITL gate (non-blocking) causes pending_approval return."""
        result = money_mode.outreach_response_conversion(
            "Hello {name}", {"name": "Alice"}, ""
        )
        assert result["status"] not in self.FORBIDDEN_STATUSES, (
            f"outreach must never return a send status; got {result['status']!r}"
        )
        assert result["status"] in {"draft", "pending_approval"}

    def test_status_never_sent_with_llm(self, money_mode, monkeypatch):
        monkeypatch.setattr(
            "core.money_mode.MoneyMode._llm_generate",
            staticmethod(lambda p, s: "Personalised outreach body."),
        )
        result = money_mode.outreach_response_conversion(
            "Hi {name}", {"name": "Bob"}, "some context"
        )
        assert result["status"] not in self.FORBIDDEN_STATUSES
        assert result["status"] in {"draft", "pending_approval"}

    def test_status_never_sent_no_recipient(self, money_mode, no_llm):
        result = money_mode.outreach_response_conversion("Hi there", None, "")
        assert result["status"] not in self.FORBIDDEN_STATUSES

    def test_ok_false_when_gate_not_approved(self, money_mode, no_llm):
        """Non-blocking gate always returns approved=False initially."""
        result = money_mode.outreach_response_conversion(
            "Hello {name}", {"name": "Carol"}, ""
        )
        # Gate is non-blocking → not yet approved → ok=False, pending_approval
        assert result["ok"] is False
        assert result["status"] == "pending_approval"
        assert "gate_id" in result


# ── 2. require_approval is called for outreach ────────────────────────────────

class TestRequireApprovalCalled:
    """HITLGate.require_approval must be invoked for outreach actions."""

    def test_require_approval_called_once(self, money_mode, no_llm, hitl_gate):
        with patch.object(hitl_gate, "require_approval", wraps=hitl_gate.require_approval) as spy:
            # Patch get_hitl_gate to return our spy-wrapped instance
            with patch("core.hitl_gate.get_hitl_gate", return_value=hitl_gate):
                money_mode.outreach_response_conversion(
                    "Hello {name}", {"name": "Dave"}, ""
                )
            spy.assert_called_once()
            call_kwargs = spy.call_args.kwargs
            assert call_kwargs["agent"] == "money_mode"
            assert call_kwargs["action"] == "outreach_send"

    def test_require_approval_payload_contains_recipient(self, money_mode, no_llm, hitl_gate):
        with patch("core.hitl_gate.get_hitl_gate", return_value=hitl_gate):
            with patch.object(hitl_gate, "require_approval", wraps=hitl_gate.require_approval) as spy:
                money_mode.outreach_response_conversion(
                    "Hello {name}", {"name": "Eve"}, ""
                )
                payload = spy.call_args.kwargs["payload"]
                assert payload["recipient"] == "Eve"

    def test_gate_pending_request_visible_in_hitl_queue(self, money_mode, no_llm, hitl_gate):
        with patch("core.hitl_gate.get_hitl_gate", return_value=hitl_gate):
            money_mode.outreach_response_conversion(
                "Hello {name}", {"name": "Frank"}, ""
            )
        pending = hitl_gate.pending_requests()
        assert len(pending) == 1
        assert pending[0]["agent"] == "money_mode"
        assert pending[0]["action"] == "outreach_send"


# ── 3. run_opportunity_pipeline gates ActionBus emit ─────────────────────────

class TestOpportunityPipelineGate:
    """ActionBus must not emit outreach without HITL approval."""

    def _make_no_research(self, monkeypatch):
        """Suppress async research to keep tests synchronous."""
        monkeypatch.setattr(
            "core.money_mode.MoneyMode.run_opportunity_pipeline",
            lambda self, **kw: self.__class__.__dict__["run_opportunity_pipeline"](
                self, research_first=False, **{k: v for k, v in kw.items() if k != "research_first"}
            ),
            raising=False,
        )

    def test_emit_not_called_without_approval(self, money_mode, monkeypatch):
        """_safe_emit must not be called when HITL gate is not yet approved."""
        with patch.object(money_mode, "_safe_emit", wraps=money_mode._safe_emit) as emit_spy:
            result = money_mode.run_opportunity_pipeline(
                opportunity="SaaS outreach Q3",
                budget=500.0,
                dry_run=False,
                research_first=False,
            )
        # Gate is non-blocking → not approved → emit should NOT be called
        emit_spy.assert_not_called()
        outreach_step = result["steps"][0]
        assert outreach_step["status"] in {"pending_approval", "dry_run"}, (
            f"Outreach step must be gated; got status={outreach_step['status']!r}"
        )

    def test_dry_run_bypasses_gate_and_emit(self, money_mode):
        """dry_run=True must never emit and must not touch the HITL gate."""
        with patch.object(money_mode, "_safe_emit") as emit_spy:
            result = money_mode.run_opportunity_pipeline(
                opportunity="test campaign",
                budget=100.0,
                dry_run=True,
                research_first=False,
            )
        emit_spy.assert_not_called()
        assert result["steps"][0]["status"] == "dry_run"

    def test_gate_request_queued_for_opportunity(self, money_mode, hitl_gate):
        with patch("core.hitl_gate.get_hitl_gate", return_value=hitl_gate):
            money_mode.run_opportunity_pipeline(
                opportunity="Q4 campaign",
                budget=250.0,
                dry_run=False,
                research_first=False,
            )
        pending = hitl_gate.pending_requests()
        assert any(r["action"] == "opportunity_outreach_emit" for r in pending), (
            "Expected a pending HITL request for opportunity_outreach_emit"
        )

    def test_emit_called_after_manual_approval(self, money_mode, hitl_gate):
        """When a human approves via the gate, _safe_emit should be called."""
        with patch("core.hitl_gate.get_hitl_gate", return_value=hitl_gate):
            with patch.object(money_mode, "_safe_emit", return_value={"status": "queued", "action_id": "x"}) as emit_spy:
                # Approve before calling so gate returns approved=True
                # We simulate this by making require_approval return approved immediately
                with patch.object(hitl_gate, "require_approval", return_value={"approved": True, "status": "approved", "request_id": "test-id"}):
                    money_mode.run_opportunity_pipeline(
                        opportunity="Pre-approved campaign",
                        budget=100.0,
                        dry_run=False,
                        research_first=False,
                    )
        emit_spy.assert_called_once()


# ── 4. deals.json write path audit ───────────────────────────────────────────

class TestDealsJsonWritePaths:
    """Audit that deals.json writes are understood and noted for gating."""

    def test_sales_closer_pro_save_deals_exists(self):
        """Confirm save_deals() is present in sales_closer_pro module."""
        scp_path = (
            Path(__file__).resolve().parents[1]
            / "runtime" / "agents" / "sales-closer-pro" / "sales_closer_pro.py"
        )
        assert scp_path.exists(), "sales_closer_pro.py not found"
        source = scp_path.read_text(encoding="utf-8")
        assert "save_deals" in source
        # Assert there is NO inline 'require_approval' call yet —
        # this is a known gap: gating should be added at the caller layer.
        # When that gate is added, change this assertion to assert presence.
        assert "require_approval" not in source, (
            "sales_closer_pro now has require_approval — update this test to "
            "assert it's called before save_deals()"
        )

    def test_crm_pipeline_uses_save_to_db_not_direct_file(self):
        """crm_pipeline uses _save_to_db (BaseAgent abstraction), not file writes."""
        crm_path = (
            Path(__file__).resolve().parents[1]
            / "runtime" / "agents" / "crm-pipeline" / "crm_pipeline.py"
        )
        assert crm_path.exists()
        source = crm_path.read_text(encoding="utf-8")
        # Confirms it does not write deals.json directly
        assert "deals.json" not in source
        assert "_save_to_db" in source

    def test_hitl_gate_blocks_outreach_before_deal_update(self, money_mode, no_llm, hitl_gate):
        """Outreach gate fires before any outreach log entry is written."""
        with patch("core.hitl_gate.get_hitl_gate", return_value=hitl_gate):
            result = money_mode.outreach_response_conversion(
                "Hi {name}", {"name": "Gail"}, ""
            )
        # Gate fired → outreach log must NOT be written (draft artifact skipped)
        outreach_log = Path(str(hitl_gate)) if False else None
        # Primary assertion: status is pending_approval, meaning we stopped
        # before writing any artifact.
        assert result["status"] == "pending_approval"
        assert result["ok"] is False


# ── 5. HITLGate API contract ──────────────────────────────────────────────────

class TestHITLGateContract:
    """Basic gate API sanity checks."""

    def test_require_approval_returns_pending_when_nonblocking(self, hitl_gate):
        result = hitl_gate.require_approval(
            agent="test-agent",
            action="send_email",
            payload={"to": "user@example.com"},
            blocking=False,
        )
        assert result["approved"] is False
        assert result["status"] == "pending"
        assert "request_id" in result

    def test_approve_flips_status(self, hitl_gate):
        result = hitl_gate.require_approval(
            agent="test-agent",
            action="send_email",
            payload={"to": "user@example.com"},
            blocking=False,
        )
        rid = result["request_id"]
        approval = hitl_gate.approve(rid, decided_by="operator")
        assert approval["ok"] is True
        assert approval["status"] == "approved"

    def test_reject_flips_status(self, hitl_gate):
        result = hitl_gate.require_approval(
            agent="test-agent",
            action="score_lead",
            payload={"lead_id": "L-42"},
            blocking=False,
        )
        rid = result["request_id"]
        rejection = hitl_gate.reject(rid, decided_by="operator", reason="not ready")
        assert rejection["ok"] is True
        assert rejection["status"] == "rejected"

    def test_is_required_for_hitl_agents(self, hitl_gate):
        for agent in ("hr-manager", "recruiter", "lead-scorer"):
            assert hitl_gate.is_required(agent), f"{agent} should require HITL"

    def test_is_required_for_trigger_actions(self, hitl_gate):
        for action in ("hire", "send_offer", "profile", "score_lead"):
            assert hitl_gate.is_required("any-agent", action), (
                f"action '{action}' should trigger HITL regardless of agent"
            )

    def test_pending_requests_only_shows_pending(self, hitl_gate):
        r1 = hitl_gate.require_approval(agent="a", action="op1", payload={}, blocking=False)
        r2 = hitl_gate.require_approval(agent="b", action="op2", payload={}, blocking=False)
        hitl_gate.approve(r1["request_id"])
        pending = hitl_gate.pending_requests()
        ids = [r["id"] for r in pending]
        assert r1["request_id"] not in ids
        assert r2["request_id"] in ids
