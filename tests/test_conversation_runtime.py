"""Phase 7 — conversation runtime layer (session memory, option resolver, policy).

Regression coverage for the reported teammate failures:
  A — "option 2" resolves to the assistant's offered option (no context question)
  D — "do that" resolves the single pending/offered action
  E — a simple operational question gets a short, value-shaped answer
  + session option-memory is captured from an assistant reply across turns.
"""
import os
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "runtime"))

from companion.session_state import get_session_store, extract_options  # noqa: E402
from companion.context_resolver import resolve_option_selection  # noqa: E402
from companion.response_policy import policy_for  # noqa: E402
from companion.conversation_runtime import ConversationRuntime, _render_dialogue  # noqa: E402
from companion.schemas import CompanionRequest  # noqa: E402


@pytest.fixture(autouse=True, scope="module")
def _isolated_state_dir():
    """Isolate session persistence to a throwaway state dir for this module's tests.

    STATE_DIR is read lazily per-call by core.state_paths.canonical_state_dir()
    (SessionStore._path() calls it fresh on every load/save — nothing caches it
    at import time), so scoping the env var to a fixture instead of a bare
    module-level `os.environ[...] =` assignment keeps the isolation local to
    this file. The previous bare assignment ran at collection time (before any
    test anywhere executes) and was never restored, permanently overriding
    every other test file's own STATE_DIR/AI_HOME isolation for the rest of the
    pytest session — STATE_DIR outranks AI_HOME in canonical_state_dir(), so it
    silently defeated AI_HOME-based isolation too. Root cause of an unrelated
    CI failure: test_agent_learning_profile.py's grade-distribution count came
    out as the accumulated total across every test that touched
    AgentLearningProfile that session, not just its own two agents.
    """
    orig = os.environ.get("STATE_DIR")
    os.environ["STATE_DIR"] = tempfile.mkdtemp(prefix="conv-rt-test-")
    try:
        yield
    finally:
        if orig is None:
            os.environ.pop("STATE_DIR", None)
        else:
            os.environ["STATE_DIR"] = orig


def _seed_options(session_id, options):
    store = get_session_store()
    st = store.load(session_id, "default")
    st.last_options_given = options
    store.save(st)


# ── A: option selection binds to the offered option ───────────────────────────

def test_option_two_resolves_without_asking_for_context():
    sid = "sess-A"
    _seed_options(sid, [
        {"id": "1", "summary": "explain how to check the time manually"},
        {"id": "2", "summary": "fetch the local PC time automatically"},
    ])
    resp = ConversationRuntime().handle(
        CompanionRequest(text="option 2", session_id=sid, tenant_id="default"))
    assert resp.meta.get("selected_option", {}).get("id") == "2"
    low = resp.reply.lower()
    assert "what do you mean" not in low and "which option" not in low


def test_dutch_ordinal_selection_resolves():
    sid = "sess-A-nl"
    _seed_options(sid, [{"id": "1", "summary": "optie een"},
                        {"id": "2", "summary": "optie twee"}])
    out = resolve_option_selection("de tweede", [{"id": "1", "summary": "a"},
                                                 {"id": "2", "summary": "b"}])
    assert out and out["ordinal"] == 2


# ── D: "do that" binds to the single offered option ───────────────────────────

def test_do_that_resolves_single_option():
    out = resolve_option_selection("doe dat", [{"id": "1", "summary": "restart the worker"}])
    assert out and out["ordinal"] == 1
    # With several options, an unqualified "do that" must NOT guess.
    assert resolve_option_selection("do that", [{"id": "1", "summary": "a"},
                                                {"id": "2", "summary": "b"}]) is None


# ── E: simple operational question → short value answer ───────────────────────

def test_simple_question_short_value_answer():
    resp = ConversationRuntime().handle(
        CompanionRequest(text="what time is it on my pc?", session_id="sess-E",
                         tenant_id="default"))
    assert resp.meta["response_policy"]["style"] == "value"
    assert "local time on this PC" in resp.reply
    assert len(resp.reply) < 120  # one short sentence, not a tutorial


# ── Session option-memory capture from a reply ────────────────────────────────

def test_options_captured_from_reply_then_resolved_next_turn():
    sid = "sess-mem"
    store = get_session_store()
    st = store.load(sid, "default")
    st.note_assistant("Here are your choices:\n1) keep the cache\n2) clear the cache")
    store.save(st)
    assert [o["id"] for o in store.load(sid, "default").last_options_given] == ["1", "2"]


def test_extract_options_ignores_single_bullet():
    assert extract_options("- just one point") == []
    assert len(extract_options("1) alpha\n2) beta\n3) gamma")) == 3


# ── Policy mapping sanity ─────────────────────────────────────────────────────

def test_policy_value_is_short_and_no_tutorial():
    p = policy_for({"mode": "monitoring", "task_type": "system_info.local_time"})
    assert p.style == "value" and p.max_sentences <= 2
    assert not p.allow_tutorial and not p.allow_options


def test_policy_relaxes_when_user_asks_for_detail():
    p = policy_for({"mode": "conversation"}, user_text="explain in detail step by step")
    assert p.allow_tutorial


# ── Conversation depth: the whole running dialogue reaches the model ───────────

def test_as_context_exposes_running_dialogue():
    store = get_session_store()
    st = store.load("sess-depth-1", "default")
    st.note_user("we are launching a SaaS for dentists")
    st.note_assistant("Got it — a SaaS for dental clinics. What's the pricing model?")
    st.note_user("monthly subscription, 49 euro")
    store.save(st)
    ctx = store.load("sess-depth-1", "default").as_context()
    msgs = ctx.get("recent_messages")
    assert isinstance(msgs, list) and len(msgs) == 3
    # earliest turn is still present — not just the last exchange
    assert any("dentists" in m["content"] for m in msgs)


def test_render_dialogue_formats_and_bounds():
    msgs = [
        {"role": "user", "content": "first thing"},
        {"role": "assistant", "content": "noted first"},
        {"role": "user", "content": "second thing"},
    ]
    rendered = _render_dialogue(msgs)
    assert "User: first thing" in rendered
    assert "Assistant: noted first" in rendered
    # role labels, oldest first
    assert rendered.index("first thing") < rendered.index("second thing")
    # char budget keeps the transcript bounded as the session grows
    os.environ["COMPANION_DIALOGUE_CHAR_BUDGET"] = "40"
    try:
        long_msgs = [{"role": "user", "content": "x" * 100} for _ in range(10)]
        bounded = _render_dialogue(long_msgs)
        assert len(bounded) <= 200  # at most one clipped line survives the 40-char budget
    finally:
        del os.environ["COMPANION_DIALOGUE_CHAR_BUDGET"]
    assert _render_dialogue([]) == "" and _render_dialogue(None) == ""


def test_session_context_prompt_includes_multiturn_history():
    ctx = {
        "current_topic": "saas_launch",
        "recent_messages": [
            {"role": "user", "content": "we sell to dentists"},
            {"role": "assistant", "content": "understood, dental clinics"},
            {"role": "user", "content": "what channel should we use first?"},
        ],
    }
    block = ConversationRuntime._session_context_prompt(ctx)
    assert "Recent conversation" in block
    assert "dentists" in block and "dental clinics" in block
    assert "Conversation topic so far: saas_launch" in block
