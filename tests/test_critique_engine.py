"""Tests for the teammate critique layer (runtime/companion/critique_engine.py)
and its wiring into the conversation runtime.

Deterministic: the LLM is NOT exercised. COMPANION_CRITIQUE_LLM is left UNSET so
the heuristic path runs (generate() is offline in CI anyway). These tests assert
the critique CHALLENGES hard/irreversible requests, does NOT nag easy ones, and
never raises on garbage input.
"""
import os
import sys
from pathlib import Path

import pytest

_RUNTIME = Path(__file__).resolve().parents[1] / "runtime"
if str(_RUNTIME) not in sys.path:
    sys.path.insert(0, str(_RUNTIME))


@pytest.fixture(autouse=True, scope="module")
def _critique_llm_off():
    """Belt-and-suspenders: keep the LLM deepening off so the heuristic is asserted.

    CritiqueEngine reads COMPANION_CRITIQUE_LLM lazily via os.getenv() inside a
    method, not at import time, so this can be a restoring fixture instead of a
    bare unrestored `os.environ[...] =` assignment (that pattern silently
    overrides every other test file's env for the rest of the pytest session —
    see test_conversation_runtime.py for a case where the equivalent mistake
    with STATE_DIR caused a real cross-test CI failure).
    """
    orig = os.environ.get("COMPANION_CRITIQUE_LLM")
    os.environ["COMPANION_CRITIQUE_LLM"] = "0"
    try:
        yield
    finally:
        if orig is None:
            os.environ.pop("COMPANION_CRITIQUE_LLM", None)
        else:
            os.environ["COMPANION_CRITIQUE_LLM"] = orig


from companion.critique_engine import (  # noqa: E402
    get_critique_engine, CritiqueEngine,
    STANCE_PROCEED, STANCE_CAUTION, STANCE_AGAINST, STANCE_NEED_INFO, ALL_STANCES,
)
import companion.conversation_runtime as cr  # noqa: E402
from companion.conversation_runtime import (  # noqa: E402
    handle_message, get_conversation_runtime,
)


def _exec_intent(conf=0.85):
    return {"mode": "execution", "task_type": "code", "is_command": True,
            "confidence": conf}


# ── Schema validity ─────────────────────────────────────────────────────────────

def _assert_schema(out):
    assert isinstance(out, dict)
    assert set(out.keys()) >= {
        "has_concerns", "stance", "assumptions", "risks", "alternative",
        "pushback", "clarifying_question", "confidence",
    }
    assert isinstance(out["has_concerns"], bool)
    assert out["stance"] in ALL_STANCES
    assert isinstance(out["assumptions"], list)
    assert isinstance(out["risks"], list)
    assert 0.0 <= out["confidence"] <= 1.0


# ── High-stakes requests are challenged ─────────────────────────────────────────

def test_delete_all_production_is_challenged():
    eng = get_critique_engine()
    out = eng.critique("delete all production data", _exec_intent(), {})
    _assert_schema(out)
    assert out["has_concerns"] is True
    assert out["stance"] in (STANCE_CAUTION, STANCE_AGAINST)
    assert out["risks"], "high-stakes deletion must surface risks"


def test_destructive_wide_scope_recommends_against():
    eng = get_critique_engine()
    out = eng.critique("wipe the entire production database now", _exec_intent(), {})
    _assert_schema(out)
    assert out["stance"] == STANCE_AGAINST
    assert out["pushback"]


def test_deploy_to_prod_now_is_challenged():
    eng = get_critique_engine()
    out = eng.critique("deploy to prod now", _exec_intent(), {})
    _assert_schema(out)
    assert out["has_concerns"] is True
    assert out["stance"] in (STANCE_CAUTION, STANCE_AGAINST)
    assert out["risks"]
    assert out["alternative"]  # better/cheaper path offered


def test_bulk_email_is_challenged():
    eng = get_critique_engine()
    out = eng.critique("email 5000 leads", _exec_intent(), {})
    _assert_schema(out)
    assert out["has_concerns"] is True
    assert out["stance"] in (STANCE_CAUTION, STANCE_AGAINST)
    assert any("unsent" in r.lower() or "outreach" in r.lower()
               for r in out["risks"])


# ── Vague / weak premises ask for info ──────────────────────────────────────────

def test_vague_goal_needs_info():
    eng = get_critique_engine()
    out = eng.critique("just make it better", _exec_intent(), {})
    _assert_schema(out)
    assert out["stance"] == STANCE_NEED_INFO or out["clarifying_question"]
    assert out["clarifying_question"]


def test_fix_everything_quickly_asks_clarifying():
    eng = get_critique_engine()
    out = eng.critique("fix everything quickly", _exec_intent(), {})
    _assert_schema(out)
    assert out["has_concerns"] is True
    assert out["clarifying_question"]


# ── Clear, low-stakes requests proceed (NO nagging) ─────────────────────────────

def test_summarize_page_proceeds():
    eng = get_critique_engine()
    out = eng.critique("summarize this page", {"mode": "analysis"}, {})
    _assert_schema(out)
    assert out["stance"] == STANCE_PROCEED
    assert out["has_concerns"] is False


def test_system_status_proceeds():
    eng = get_critique_engine()
    out = eng.critique("what's the system status", {"mode": "monitoring"}, {})
    _assert_schema(out)
    assert out["stance"] == STANCE_PROCEED
    assert out["has_concerns"] is False


def test_scoped_clear_code_task_proceeds():
    eng = get_critique_engine()
    out = eng.critique(
        "add a unit test for the parse_date function so tests pass",
        _exec_intent(), {})
    _assert_schema(out)
    assert out["stance"] == STANCE_PROCEED
    assert out["has_concerns"] is False


# ── Never raises on garbage ─────────────────────────────────────────────────────

def test_critique_never_raises_on_garbage():
    eng = get_critique_engine()
    for bad in (None, "", "   ", 123, {"x": 1}, ["a"], "\n\t"):
        try:
            out = eng.critique(bad, None, None)  # type: ignore[arg-type]
        except Exception as exc:  # pragma: no cover
            raise AssertionError(f"critique raised on {bad!r}: {exc}")
        _assert_schema(out)


def test_singleton():
    assert get_critique_engine() is get_critique_engine()
    assert isinstance(get_critique_engine(), CritiqueEngine)


# ── Conversation runtime wiring ─────────────────────────────────────────────────

def _force_llm_offline(monkeypatch):
    rt = get_conversation_runtime()
    monkeypatch.setattr(rt, "_llm",
                        lambda prompt, system, model_info, fallback: fallback)
    return rt


def test_execution_turn_includes_critique_meta(monkeypatch):
    _force_llm_offline(monkeypatch)
    monkeypatch.setenv("COMPANION_CRITIQUE", "1")
    r = handle_message({"text": "deploy to prod now", "session_id": "s1"})
    assert r["ok"] is True
    assert "critique" in r["meta"]
    assert r["meta"]["critique"]["stance"] in ALL_STANCES


def test_need_info_does_not_execute_broker(monkeypatch):
    _force_llm_offline(monkeypatch)
    monkeypatch.setenv("COMPANION_CRITIQUE", "1")
    # "fix ..." classifies as an execution command, so the critique runs; the
    # vague + superlative goal yields a need_info stance that short-circuits.
    r = handle_message({"text": "fix everything quickly", "session_id": "s1"})
    assert r["ok"] is True
    crit = r["meta"].get("critique") or {}
    assert crit.get("stance") == STANCE_NEED_INFO
    # need_info short-circuits: nothing executed, clarifying question surfaced.
    executed = [a for a in r["actions"] if a.get("status") == "ok"]
    assert executed == []
    assert r["meta"].get("awaiting_clarification") is True
    assert r["reply"].strip()


def test_recommend_against_surfaces_override_not_silent(monkeypatch):
    _force_llm_offline(monkeypatch)
    monkeypatch.setenv("COMPANION_CRITIQUE", "1")
    # "delete ..." classifies as an execution command; wide-scope destruction
    # with no safeguard yields a recommend_against stance.
    r = handle_message({"text": "delete all production data now",
                        "session_id": "s1"})
    assert r["ok"] is True
    crit = r["meta"].get("critique") or {}
    assert crit.get("stance") == STANCE_AGAINST
    # Recommendation must be explicit in the reply (not silent compliance).
    assert "recommend against" in r["reply"].lower()
    caps = {a.get("cap") for a in r["approvals_required"]}
    assert "companion.critique_override" in caps


def test_critique_disabled_path(monkeypatch):
    _force_llm_offline(monkeypatch)
    monkeypatch.setenv("COMPANION_CRITIQUE", "0")
    r = handle_message({"text": "deploy to prod now", "session_id": "s1"})
    assert r["ok"] is True
    assert "critique" not in r["meta"]


def test_conversation_mode_not_critiqued(monkeypatch):
    _force_llm_offline(monkeypatch)
    monkeypatch.setenv("COMPANION_CRITIQUE", "1")
    # Plain chit-chat should not be nagged with a critique.
    r = handle_message({"text": "tell me a story about robots", "session_id": "s1"})
    assert r["ok"] is True
    assert "critique" not in r["meta"]
