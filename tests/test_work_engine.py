"""Tests for the Work Acquisition + Delivery Engine (Master Plan V3 — Module 4).

Offline-deterministic: no live LLM required (evaluate/quote/study run with
use_llm=False where LLM would otherwise be reached; the deliverable builder
degrades to an offline template). State is redirected to a temp dir via
STATE_DIR so tests never touch real state.
"""
import os
import sys
import tempfile
from pathlib import Path

import pytest

_RUNTIME = Path(__file__).resolve().parents[1] / "runtime"
if str(_RUNTIME) not in sys.path:
    sys.path.insert(0, str(_RUNTIME))

from money.work_engine import get_work_engine  # noqa: E402
from money.work_engine import opportunity_store as store  # noqa: E402
from money.work_engine import fit_evaluator, pricing_estimator  # noqa: E402


@pytest.fixture(autouse=True, scope="module")
def _isolated_state_dir():
    """Redirect canonical state dir to a temp location for this module's tests only.

    opportunity_store reads STATE_DIR lazily via canonical_state_dir() inside a
    method, not at import time, so a module-scoped fixture (set → yield →
    restore) isolates this file exactly like the old bare `os.environ[...] =`
    assignment did, but without permanently overriding every other test file's
    STATE_DIR/AI_HOME isolation for the rest of the pytest session (that exact
    unrestored-mutation pattern caused a real cross-test failure in
    test_agent_learning_profile.py — see test_conversation_runtime.py for the
    full root-cause writeup).
    """
    orig = os.environ.get("STATE_DIR")
    os.environ["STATE_DIR"] = tempfile.mkdtemp(prefix="work_engine_test_")
    try:
        yield
    finally:
        if orig is None:
            os.environ.pop("STATE_DIR", None)
        else:
            os.environ["STATE_DIR"] = orig


def _engine():
    return get_work_engine()


def _ingest(**kw):
    opp = {"title": "Write a blog article", "description": "A 1000-word SEO blog post about cold brew coffee for a cafe.", "category": "content", "budget_hint": 300, **kw}
    return _engine().ingest_opportunity(opp)


def _walk_to_accepted(oid):
    """Drive the full lifecycle through both gate-1 approval to 'accepted'."""
    from core.hitl_gate import get_hitl_gate
    e = _engine()
    e.evaluate(oid, use_llm=False)
    q = e.quote(oid)
    get_hitl_gate().approve(q["gate_id"], decided_by="tester")
    e.confirm_quote_sent(oid)
    e.accept(oid)
    return oid


# ── ingest + list ───────────────────────────────────────────────────────────────

def test_ingest_then_list_returns_it():
    res = _ingest()
    assert res["ok"] is True
    oid = res["opportunity"]["id"]
    listing = _engine().list_opportunities()
    assert listing["ok"] is True
    assert any(o["id"] == oid for o in listing["opportunities"])


def test_ingest_handles_empty_and_none():
    assert _engine().ingest_opportunity(None)["ok"] is True
    assert _engine().ingest_opportunity({})["ok"] is True


# ── evaluate ────────────────────────────────────────────────────────────────────

def test_evaluate_returns_fit_score_and_recommendation():
    oid = _ingest()["opportunity"]["id"]
    res = _engine().evaluate(oid, use_llm=False)
    assert res["ok"] is True
    ev = res["evaluation"]
    assert 0.0 <= ev["fit_score"] <= 1.0
    assert ev["recommendation"] in ("pursue", "decline", "needs_info")
    assert ev["risk_level"] in ("low", "medium", "high")


def test_evaluate_value_is_labelled_estimate():
    oid = _ingest()["opportunity"]["id"]
    ev = _engine().evaluate(oid, use_llm=False)["evaluation"]
    assert ev["value_estimate"]["is_estimate"] is True
    assert ev["effort_estimate"]["is_estimate"] is True


def test_evaluate_missing_opportunity():
    res = _engine().evaluate("does-not-exist", use_llm=False)
    assert res["ok"] is False


# ── quote — HARD HITL GATE 1 (pending, not sent) ────────────────────────────────

def test_quote_requires_approval_and_is_not_sent():
    oid = _ingest()["opportunity"]["id"]
    _engine().evaluate(oid, use_llm=False)
    res = _engine().quote(oid)
    assert res["ok"] is True
    assert res["status"] == "pending_approval"
    assert res["requires_human_approval"] is True
    assert res["gate_id"]  # a HITL gate was opened
    # Estimate is labelled, not an actual.
    assert res["quote"]["estimate"]["is_estimate"] is True
    # Opportunity parked in quote_pending — NOT 'quoted'/'sent'.
    assert store.get(oid)["status"] == "quote_pending"


def test_confirm_quote_blocked_until_approved():
    oid = _ingest()["opportunity"]["id"]
    _engine().evaluate(oid, use_llm=False)
    _engine().quote(oid)
    res = _engine().confirm_quote_sent(oid)
    assert res["ok"] is False  # not approved yet
    assert store.get(oid)["status"] == "quote_pending"


def test_confirm_quote_after_human_approval():
    from core.hitl_gate import get_hitl_gate
    oid = _ingest()["opportunity"]["id"]
    _engine().evaluate(oid, use_llm=False)
    q = _engine().quote(oid)
    get_hitl_gate().approve(q["gate_id"], decided_by="tester")
    res = _engine().confirm_quote_sent(oid)
    assert res["ok"] is True
    assert store.get(oid)["status"] == "quoted"


# ── deliver — HARD HITL GATE 2 (pending, not submitted) ─────────────────────────

def test_deliver_requires_approval_and_is_not_submitted():
    oid = _walk_to_accepted(_ingest()["opportunity"]["id"])
    _engine().execute(oid)
    res = _engine().deliver(oid)
    assert res["ok"] is True
    assert res["status"] == "pending_approval"
    assert res["requires_human_approval"] is True
    assert res["gate_id"]
    assert store.get(oid)["status"] == "delivery_pending"
    # A real artifact was produced + staged.
    assert res["deliverable"]["artifact_path"]


def test_confirm_delivered_after_human_approval():
    from core.hitl_gate import get_hitl_gate
    oid = _walk_to_accepted(_ingest()["opportunity"]["id"])
    _engine().execute(oid)
    d = _engine().deliver(oid)
    get_hitl_gate().approve(d["gate_id"], decided_by="tester")
    res = _engine().confirm_delivered(oid)
    assert res["ok"] is True
    assert store.get(oid)["status"] == "delivered"


# ── feedback + study ────────────────────────────────────────────────────────────

def test_feedback_recorded():
    oid = _ingest()["opportunity"]["id"]
    res = _engine().record_feedback(oid, {"rating": 4.5, "outcome": "accepted", "accepted": True, "paid": True})
    assert res["ok"] is True
    assert res["feedback"]["rating"] == 4.5


def test_study_session_returns_lessons_without_blocking():
    oid = _ingest()["opportunity"]["id"]
    _engine().record_feedback(oid, {"rating": 3, "accepted": True})
    res = _engine().run_study_session(use_llm=False)
    assert res["ok"] is True
    assert isinstance(res["study"]["lessons"], list)
    assert len(res["study"]["lessons"]) >= 1


# ── robustness: no method raises on bad input ───────────────────────────────────

def test_methods_never_raise_on_bad_input():
    e = _engine()
    bad = "nope-not-real-id"
    for call in (
        lambda: e.get_opportunity(bad),
        lambda: e.evaluate(bad, use_llm=False),
        lambda: e.quote(bad),
        lambda: e.accept(bad),
        lambda: e.execute(bad),
        lambda: e.deliver(bad),
        lambda: e.confirm_quote_sent(bad),
        lambda: e.confirm_delivered(bad),
        lambda: e.record_feedback(bad, None),
        lambda: e.run_study_session(bad, use_llm=False),
        lambda: e.decline(bad, "reason"),
        lambda: e.list_opportunities("garbage-status"),
    ):
        out = call()
        assert isinstance(out, dict)
        assert "ok" in out


def test_pricing_and_fit_never_raise_on_garbage():
    assert isinstance(fit_evaluator.evaluate(None, use_llm=False), dict)
    assert isinstance(fit_evaluator.evaluate({"x": 1}, use_llm=False), dict)
    assert isinstance(pricing_estimator.quote(None, None), dict)
    assert pricing_estimator.quote({}, {})["is_estimate"] is True


def test_illegal_transition_is_refused():
    oid = _ingest()["opportunity"]["id"]
    # Jumping straight to 'delivered' from 'ingested' must be refused.
    res = store.set_status(oid, "delivered")
    assert res["ok"] is False
    assert store.get(oid)["status"] == "ingested"
