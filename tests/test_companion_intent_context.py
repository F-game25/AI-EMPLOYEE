"""Tests for the Companion Gateway intent classifier + context resolver.

Heuristic/deterministic only — COMPANION_LLM_INTENT is deliberately left unset
so the fast path is exercised and tests don't touch the LLM.
"""
import os
import sys
from pathlib import Path

_RUNTIME = Path(__file__).resolve().parents[1] / "runtime"
if str(_RUNTIME) not in sys.path:
    sys.path.insert(0, str(_RUNTIME))

# Ensure deterministic heuristic path regardless of ambient env.
os.environ.pop("COMPANION_LLM_INTENT", None)

from companion.intent_classifier import (  # noqa: E402
    IntentClassifier, get_intent_classifier,
    MODE_MONITORING, MODE_EXECUTION, MODE_APPROVAL, MODE_DEBUGGING,
    MODE_CONVERSATION, MODE_ANALYSIS, ALL_MODES,
)
from companion.context_resolver import (  # noqa: E402
    ContextResolver, get_context_resolver,
)


# ── Intent classifier ──────────────────────────────────────────────────────────

def _clf():
    return get_intent_classifier()


def test_monitoring_question():
    out = _clf().classify("what is the system doing?")
    assert out["mode"] == MODE_MONITORING
    assert out["is_command"] is False
    assert out["task_type"] == "monitoring"


def test_execution_command_is_command():
    out = _clf().classify("fix the avatar lag")
    assert out["mode"] == MODE_EXECUTION
    assert out["is_command"] is True
    assert out["task_type"] == "code"


def test_browser_intent_routes_to_execution_browser():
    """Web phrasings → execution/browser so the runtime drives browser.* caps."""
    for phrase in ("open example.com and read the page title",
                   "browse to example.com and click login",
                   "go to https://news.com and screenshot the page"):
        out = _clf().classify(phrase)
        assert out["mode"] == MODE_EXECUTION, phrase
        assert out["task_type"] == "browser", phrase
        assert out["is_command"] is True, phrase


def test_non_browser_open_is_not_browser():
    """'open the file' / 'read the report' must NOT be misrouted to browser."""
    assert _clf().classify("open the file config.py")["task_type"] != "browser"
    assert _clf().classify("read the quarterly report")["task_type"] != "browser"


def test_approval():
    out = _clf().classify("approve")
    assert out["mode"] == MODE_APPROVAL
    assert out["is_command"] is False


def test_rejection_is_approval_mode():
    out = _clf().classify("no don't")
    assert out["mode"] == MODE_APPROVAL


def test_debugging_question():
    out = _clf().classify("why did that fail?")
    assert out["mode"] == MODE_DEBUGGING
    assert out["is_command"] is False


def test_discussion_is_conversation_or_analysis():
    out = _clf().classify("let's discuss pricing")
    assert out["mode"] in (MODE_CONVERSATION, MODE_ANALYSIS)
    assert out["is_command"] is False


def test_why_did_deploy_fail_is_debugging_not_execution():
    """A 'why did the deploy fail' must not be misread as a deploy command."""
    out = _clf().classify("why did the deploy fail")
    assert out["mode"] == MODE_DEBUGGING
    assert out["is_command"] is False


def test_build_command_is_execution():
    out = _clf().classify("build the new dashboard")
    assert out["mode"] == MODE_EXECUTION
    assert out["is_command"] is True


def test_classifier_always_returns_valid_mode_and_shape():
    for msg in ("hello", "deploy now", "summarize this report",
                "plan the migration", "remember I prefer dark mode", ""):
        out = _clf().classify(msg)
        assert set(out.keys()) == {"mode", "task_type", "confidence",
                                   "is_command", "reason"}
        assert out["mode"] in ALL_MODES
        assert isinstance(out["is_command"], bool)
        assert 0.0 <= out["confidence"] <= 1.0


def test_singleton_identity():
    assert get_intent_classifier() is get_intent_classifier()
    assert isinstance(get_intent_classifier(), IntentClassifier)


# ── Context resolver ────────────────────────────────────────────────────────────

def _res():
    return get_context_resolver()


def test_fix_it_binds_to_failing_active_task():
    ctx = {
        "current_page": "Orders",
        "selected_item": None,
        "recent_events": [],
        "active_task": {"id": "task-42", "title": "Sync orders",
                        "status": "failed", "error": "timeout"},
        "recent_messages": [],
    }
    out = _res().resolve("fix it", ctx)
    assert out["focus"] is not None
    assert out["focus"]["source"] == "active_task"
    assert out["focus"]["failing"] is True
    assert out["referents"]
    assert out["confidence"] >= 0.7
    # Resolved text carries a factual preamble naming the real task.
    assert "Sync orders" in out["resolved_text"]
    assert out["resolved_text"].startswith("fix it")


def test_fix_it_empty_context_no_fabrication():
    ctx = {
        "current_page": None,
        "selected_item": None,
        "recent_events": [],
        "active_task": None,
        "recent_messages": [],
    }
    out = _res().resolve("fix it", ctx)
    assert out["focus"] is None
    assert out["referents"] == []
    assert out["confidence"] < 0.4
    # Text returned unchanged — nothing invented.
    assert out["resolved_text"] == "fix it"


def test_selected_item_takes_priority_over_active_task():
    ctx = {
        "current_page": "Orders",
        "selected_item": {"id": "order-7", "name": "Order #7"},
        "recent_events": [],
        "active_task": {"id": "task-42", "title": "Sync orders",
                        "status": "failed"},
        "recent_messages": [],
    }
    out = _res().resolve("fix it", ctx)
    assert out["focus"]["source"] == "selected_item"
    assert "Order #7" in out["resolved_text"]


def test_error_event_binding_when_no_task_or_selection():
    ctx = {
        "current_page": "System",
        "selected_item": None,
        "recent_events": [
            {"type": "info", "message": "boot ok"},
            {"type": "task_failed", "level": "error",
             "message": "avatar render crashed"},
        ],
        "active_task": None,
        "recent_messages": [],
    }
    out = _res().resolve("what happened", ctx)
    assert out["focus"]["source"] == "recent_event"
    assert "avatar render crashed" in out["resolved_text"]


def test_empty_text_low_confidence():
    out = _res().resolve("", {"current_page": "Orders"})
    assert out["confidence"] < 0.4
    assert out["focus"] is None


def test_resolver_singleton_identity():
    assert get_context_resolver() is get_context_resolver()
    assert isinstance(get_context_resolver(), ContextResolver)
