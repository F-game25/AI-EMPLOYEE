"""Coherence C1.b — process_user_input is the genuine single entry: the former
server.py chat bypass (utility direct-reply + structured-goal real engine) now runs
INSIDE the pipeline as Phase 0, not as a pre-pipeline return. See
docs/SYSTEM_COHERENCE_PLAN.md (C1)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "runtime"))

from core import unified_pipeline as up  # noqa: E402


def test_fast_path_short_circuits_utility_turns():
    """Greeting / empty resolve to a direct reply (no LLM/pipeline needed)."""
    assert isinstance(up._intent_fast_path("hi"), str)
    assert isinstance(up._intent_fast_path(""), str)


def test_fast_path_passes_through_normal_questions():
    """A real question returns None → continue to the full pipeline."""
    assert up._intent_fast_path("what is the capital of France?") is None


def test_process_user_input_short_circuits_before_llm():
    """The integration: a greeting must short-circuit in Phase 0 WITHOUT ever
    invoking the injected LLM fn — proving the fast-path is wired into the single
    entry, not bypassing it from server.py."""
    called = {"llm": False}

    def _spy_llm(msg, agent, mode, *, model_route=None, user_id="default", graph_context=""):
        called["llm"] = True
        return "LLM WAS CALLED"

    reply = up.process_user_input("hello", generate_llm_response_fn=_spy_llm)
    assert isinstance(reply, str) and reply
    assert called["llm"] is False  # short-circuited before the LLM phase


def test_process_user_input_runs_pipeline_for_questions():
    """A normal question is NOT short-circuited — it reaches the LLM phase (the
    injected fn is invoked), confirming Phase 0 only intercepts the fast-path."""
    called = {"llm": False}

    def _spy_llm(msg, agent, mode, *, model_route=None, user_id="default", graph_context=""):
        called["llm"] = True
        return "answer from llm"

    reply = up.process_user_input("explain how TCP congestion control works",
                                  generate_llm_response_fn=_spy_llm)
    assert isinstance(reply, str)
    assert called["llm"] is True
