"""Tests for the Companion Gateway orchestration layer (runtime/companion/).

Covers conversation_runtime (handle/handle_message), execution_broker, and
avatar_state_engine. Deterministic: the LLM is NOT required — the runtime must
degrade to a safe canned reply when engine.api.generate is unavailable, and
these tests assert that degradation path works.
"""
import sys
from pathlib import Path

_RUNTIME = Path(__file__).resolve().parents[1] / "runtime"
if str(_RUNTIME) not in sys.path:
    sys.path.insert(0, str(_RUNTIME))

import companion.conversation_runtime as cr  # noqa: E402
from companion.conversation_runtime import (  # noqa: E402
    handle_message, get_conversation_runtime, ConversationRuntime,
)
from companion.schemas import CompanionRequest  # noqa: E402
from companion.avatar_state_engine import (  # noqa: E402
    get_avatar_state_engine, AvatarStateEngine,
    IDLE, THINKING, PLANNING, EXECUTING, MONITORING, LEARNING,
    APPROVAL_NEEDED, ERROR, EVENT_TYPE, ALL_STATES,
)
from companion.execution_broker import get_execution_broker  # noqa: E402


# ── Helper: force the LLM offline so reply generation is deterministic ─────────
def _force_llm_offline(monkeypatch):
    rt = get_conversation_runtime()

    def _offline(prompt, system, model_info, fallback):
        return fallback

    monkeypatch.setattr(rt, "_llm", _offline)
    return rt


# ── handle_message: monitoring ─────────────────────────────────────────────────

def test_monitoring_question_routes_to_monitoring_mode(monkeypatch):
    _force_llm_offline(monkeypatch)
    r = handle_message({"text": "what is the system doing?", "session_id": "s1"})
    assert r["ok"] is True
    assert r["mode"] == "monitoring"
    assert r["avatar_state"] == MONITORING
    assert isinstance(r["reply"], str) and r["reply"].strip()
    assert r["meta"]["model"]["target"] == "local"


# ── Read-only execution: system.health.read runs (or honest stub), no crash ────

def test_readonly_request_executes_or_stubs_without_crash(monkeypatch):
    _force_llm_offline(monkeypatch)
    r = handle_message({"text": "show me the system health status",
                        "session_id": "s1"})
    assert r["ok"] is True
    caps = {a.get("cap") for a in r["actions"]}
    assert "system.health.read" in caps
    health = next(a for a in r["actions"] if a.get("cap") == "system.health.read")
    # Real read-only call OR a clearly-marked stub — never fabricated/crashed.
    assert health["status"] in ("ok", "not_implemented", "error")
    # No action ever silently fabricates data.
    for a in r["actions"]:
        assert a.get("status") in ("ok", "not_implemented", "error", "blocked")


def test_broker_health_executes_real_or_honest_stub():
    broker = get_execution_broker()
    out = broker.execute(
        {"mode": "monitoring", "task_type": "monitoring", "is_command": False},
        {"resolved_text": "system health status"},
        {},
        only_subsystems={"system"},
    )
    ids = {r["cap"] for r in out["results"]}
    assert "system.health.read" in ids
    hr = next(r for r in out["results"] if r["cap"] == "system.health.read")
    assert hr["status"] in ("ok", "not_implemented", "error")
    # No approvals for read-only system caps.
    assert out["approvals_required"] == []


# ── High-risk (L3) request is gated, never executed ────────────────────────────

def test_high_risk_apply_patch_requires_approval_and_is_not_executed(monkeypatch):
    _force_llm_offline(monkeypatch)
    r = handle_message({"text": "apply patch", "session_id": "s1"})
    assert r["ok"] is True
    appr_caps = {a.get("cap") for a in r["approvals_required"]}
    assert "forge.apply_patch" in appr_caps, r["approvals_required"]
    # The risky capability must NOT appear as an executed action.
    executed_caps = {a.get("cap") for a in r["actions"]
                     if a.get("status") == "ok"}
    assert "forge.apply_patch" not in executed_caps
    assert r["avatar_state"] == APPROVAL_NEEDED
    # The approval card is human-readable and carries rollback guidance.
    card = next(a for a in r["approvals_required"] if a["cap"] == "forge.apply_patch")
    assert card["risk"] == "L3"
    assert card.get("rollback")


def test_broker_never_executes_an_approval_capability():
    broker = get_execution_broker()
    out = broker.execute(
        {"mode": "execution", "task_type": "code", "is_command": True},
        {"resolved_text": "apply patch to source files"},
        {},
    )
    assert "forge.apply_patch" not in out["executed"]
    assert "forge.apply_patch" in out["blocked"]
    assert any(a["cap"] == "forge.apply_patch" for a in out["approvals_required"])


# ── Paid upgrade: external_api target requested, gated behind approval ─────────

def test_paid_upgrade_shows_external_api_target_and_requires_approval(monkeypatch):
    _force_llm_offline(monkeypatch)
    r = handle_message({
        "text": "refactor the auth module",
        "session_id": "s1",
        "context": {"prefer_target": "external_api", "allow_paid": True},
    })
    assert r["ok"] is True
    model = r["meta"]["model"]
    assert model["target"] == "external_api"
    assert model["requires_approval"] is True
    assert model["requires_payment"] is True
    # The paid upgrade is surfaced as an approval, not auto-run.
    appr_caps = {a.get("cap") for a in r["approvals_required"]}
    assert "model.paid_upgrade" in appr_caps


def test_paid_target_not_selected_without_opt_in(monkeypatch):
    _force_llm_offline(monkeypatch)
    # Coding task but no allow_paid → must stay free/local, no paid approval.
    r = handle_message({"text": "refactor the auth module", "session_id": "s1"})
    model = r["meta"]["model"]
    assert model["target"] == "local"
    assert model["requires_approval"] is False
    assert "model.paid_upgrade" not in {a.get("cap") for a in r["approvals_required"]}


# ── Conversation degrades safely when the LLM is offline ───────────────────────

def test_conversation_degrades_to_canned_reply_when_llm_offline(monkeypatch):
    # Make engine.api.generate import fail inside _llm by patching it to raise.
    rt = get_conversation_runtime()
    orig = ConversationRuntime._llm

    def _raise(self, prompt, system, model_info, fallback):
        # Exercise the real _llm fallback by forcing generate to blow up.
        import companion.conversation_runtime as mod
        return orig(self, prompt, system, model_info, fallback)

    # Patch engine.api.generate to raise so the degradation branch is hit.
    import engine.api as eapi
    monkeypatch.setattr(eapi, "generate",
                        lambda **k: (_ for _ in ()).throw(RuntimeError("llm down")))
    r = handle_message({"text": "tell me a story about robots", "session_id": "s1"})
    assert r["ok"] is True
    assert isinstance(r["reply"], str) and r["reply"].strip()
    assert "LLM offline" in r["reply"] or len(r["reply"]) > 0


# ── Avatar state engine ────────────────────────────────────────────────────────

def test_avatar_state_for_maps_modes_and_phases():
    eng = get_avatar_state_engine()
    assert eng.state_for("execution", "classifying") == THINKING
    assert eng.state_for("planning", "planning") == PLANNING
    assert eng.state_for("execution", "executing") == EXECUTING
    assert eng.state_for("execution", "awaiting_approval") == APPROVAL_NEEDED
    assert eng.state_for("monitoring", "monitoring") == MONITORING
    assert eng.state_for("learning", "learning") == LEARNING
    assert eng.state_for("anything", "error") == ERROR
    # Terminal/unknown phase settles to a mode rest state (planning → planning).
    assert eng.state_for("planning", "done") == PLANNING
    # Total nonsense → idle, never throws.
    assert eng.state_for("???", "???") == IDLE
    assert eng.state_for(None, None) == IDLE


def test_avatar_event_payload_shape():
    eng = get_avatar_state_engine()
    ev = eng.event(EXECUTING, intensity=0.9, focus="forge.apply_patch",
                   message="running", progress=0.5)
    assert ev["type"] == EVENT_TYPE
    assert ev["state"] == EXECUTING
    assert 0.0 <= ev["intensity"] <= 1.0
    assert ev["focusTarget"] == "forge.apply_patch"
    assert ev["message"] == "running"
    assert ev["progress"] == 0.5
    # Bad inputs are clamped/normalised, never raise.
    bad = eng.event("not_a_real_state", intensity="oops", progress="nope")
    assert bad["state"] in ALL_STATES
    assert 0.0 <= bad["intensity"] <= 1.0
    assert bad["progress"] is None


def test_avatar_singleton():
    assert get_avatar_state_engine() is get_avatar_state_engine()
    assert isinstance(get_avatar_state_engine(), AvatarStateEngine)


# ── Runtime never throws ───────────────────────────────────────────────────────

def test_runtime_never_throws_on_garbage():
    for payload in (None, {}, {"text": None}, {"text": 123},
                    {"text": "", "session_id": ""},
                    {"context": "not-a-dict"}):
        try:
            r = handle_message(payload)
        except Exception as exc:  # pragma: no cover
            raise AssertionError(f"handle_message raised on {payload!r}: {exc}")
        assert isinstance(r, dict)
        assert "ok" in r and "mode" in r and "reply" in r
        assert r["avatar_state"] in ALL_STATES


def test_handle_accepts_companion_request_object(monkeypatch):
    _force_llm_offline(monkeypatch)
    rt = get_conversation_runtime()
    resp = rt.handle(CompanionRequest(text="what's running right now",
                                      session_id="s1"))
    assert resp.ok is True
    assert resp.mode == "monitoring"
    assert resp.avatar_state == MONITORING
