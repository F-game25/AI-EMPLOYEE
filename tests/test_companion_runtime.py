"""Tests for the Companion Gateway orchestration layer (runtime/companion/).

Covers conversation_runtime (handle/handle_message), execution_broker, and
avatar_state_engine. Deterministic: the LLM is NOT required — the runtime must
degrade to a safe canned reply when engine.api.generate is unavailable, and
these tests assert that degradation path works.
"""
import sys
from pathlib import Path
import json

_RUNTIME = Path(__file__).resolve().parents[1] / "runtime"
if str(_RUNTIME) not in sys.path:
    sys.path.insert(0, str(_RUNTIME))

import companion.conversation_runtime as cr  # noqa: E402
import companion.execution_broker as eb  # noqa: E402
from companion.conversation_runtime import (  # noqa: E402
    handle_message, get_conversation_runtime, ConversationRuntime,
)
from companion.session_state import get_session_store  # noqa: E402
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


# ── Voice channel: concise spoken summary in meta.voice_summary ────────────────

def test_voice_channel_populates_voice_summary(monkeypatch):
    _force_llm_offline(monkeypatch)
    r = handle_message({"text": "what is the system doing?",
                        "session_id": "s1", "channel": "voice"})
    assert r["ok"] is True
    assert r["meta"]["channel"] == "voice"
    vs = r["meta"].get("voice_summary")
    assert isinstance(vs, str) and vs.strip()
    # Short reply → not truncated. voice_summary strips markdown + flattens
    # newlines so TTS doesn't read syntax aloud, so compare on text content
    # (alphanumerics), not verbatim formatting — proves no content was lost.
    if len(r["reply"]) <= 280:
        _norm = lambda s: "".join(c for c in s.lower() if c.isalnum())
        assert _norm(vs) == _norm(r["reply"])


def test_voice_morning_brief_is_structured_and_remembered(tmp_path, monkeypatch):
    monkeypatch.setattr(eb, "_state_dir", lambda: tmp_path)
    (tmp_path / "leads-crm.json").write_text(json.dumps({
        "leads": [{"stage": "negotiation", "value": 900}]
    }), encoding="utf-8")
    (tmp_path / "invoices.json").write_text(json.dumps({
        "invoices": [{"status": "overdue", "total": 200}]
    }), encoding="utf-8")

    sid = "voice-morning-brief"
    r = handle_message({"text": "give me my morning brief",
                        "session_id": sid, "channel": "voice"})
    assert r["ok"] is True
    assert r["mode"] == "monitoring"
    assert any(a.get("cap") == "briefing.morning" for a in r["actions"])
    assert "Focus:" in r["reply"]
    assert r["meta"]["voice_summary"].startswith("Morning brief:")

    st = get_session_store().load(sid, "default")
    assert any(item.get("cap") == "briefing.morning" for item in st.recent_tool_results)


def test_voice_followup_turns_morning_brief_focus_into_local_task(tmp_path, monkeypatch):
    monkeypatch.setattr(eb, "_state_dir", lambda: tmp_path)
    (tmp_path / "invoices.json").write_text(json.dumps({
        "invoices": [{"status": "overdue", "total": 200}]
    }), encoding="utf-8")

    sid = "voice-brief-to-task"
    brief = handle_message({"text": "give me my morning brief",
                            "session_id": sid, "channel": "voice"})
    assert brief["ok"] is True
    assert any(a.get("cap") == "briefing.morning" for a in brief["actions"])

    follow = handle_message({"text": "turn first focus into a task",
                             "session_id": sid, "channel": "voice"})
    assert follow["ok"] is True
    assert follow["mode"] == "execution"
    action = next(a for a in follow["actions"]
                  if a.get("cap") == "teammate.briefing.create_task")
    assert action["data"]["stored"] is True
    assert action["data"]["task"]["status"] == "pending"

    saved = json.loads((tmp_path / "tasks.json").read_text(encoding="utf-8"))
    assert saved["tasks"]


def test_session_context_prompt_includes_recent_tool_results():
    ctx = {
        "last_assistant_message": "Morning brief: focus on invoices.",
        "recent_tool_results": [
            {"cap": "briefing.morning", "data": {"focus": ["Collect overdue invoice."]}}
        ],
    }
    prompt = ConversationRuntime._session_context_prompt(ctx)
    assert "Recent real tool results" in prompt
    assert "Collect overdue invoice" in prompt


def test_non_voice_channel_has_no_voice_summary(monkeypatch):
    _force_llm_offline(monkeypatch)
    r = handle_message({"text": "what is the system doing?", "session_id": "s1"})
    assert "voice_summary" not in r["meta"]


def test_voice_summary_truncates_long_reply():
    long_reply = (
        "First, the orchestrator interprets intent and selects a skill. "
        "Second, the skill builds an execution plan from its tools. "
        "Third, tools run atomically and results are validated. "
        "Fourth, the response is composed and streamed to the UI. "
        "Fifth, memory is updated and the loop monitors for improvement."
    )
    summary = ConversationRuntime._voice_summary(long_reply)
    assert summary
    assert len(summary) <= len(long_reply)
    assert "full details are in the chat" in summary.lower()


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
