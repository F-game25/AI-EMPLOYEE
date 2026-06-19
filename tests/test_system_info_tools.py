"""Phase 7.1.3/7.1.4 — system-info tools + intent routing.

Proves the teammate ANSWERS system questions with a real OS value instead of
explaining how the user could check manually (the reported failure).
"""
import os
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "runtime"))

from tools.system_info import system_local_time, system_hardware, system_cwd  # noqa: E402
from companion.intent_classifier import get_intent_classifier  # noqa: E402
from companion.execution_broker import get_execution_broker  # noqa: E402
from companion.conversation_runtime import ConversationRuntime  # noqa: E402


# ── Tools return real, measured values ────────────────────────────────────────

def test_local_time_real():
    out = system_local_time()
    assert out["status"] == "ok"
    assert re.fullmatch(r"\d{2}:\d{2}", out["hhmm"])  # real clock value


def test_hardware_real():
    out = system_hardware()
    assert out["status"] == "ok"
    assert out["cpu"]["available"] and out["cpu"]["cores_logical"]
    # RAM section is present (available True with a total, or an honest reason)
    assert "available" in out["ram"]


def test_cwd_real():
    out = system_cwd()
    assert out["status"] == "ok"
    assert os.path.isdir(out["cwd"])


# ── Intent classification (Regression B) ──────────────────────────────────────

@pytest.mark.parametrize("q", [
    "what time is it on my pc?",
    "hoe laat is het?",
    "tell me the local time",
])
def test_time_question_classified_as_system_info(q):
    intent = get_intent_classifier().classify(q)
    assert intent["task_type"] == "system_info.local_time"


def test_hardware_and_cwd_classified():
    ic = get_intent_classifier()
    assert ic.classify("what is my cpu?")["task_type"] == "system_info.hardware"
    assert ic.classify("which folder am i in?")["task_type"] == "system_info.cwd"


# ── Broker routes the intent to the tool and returns the real value ───────────

def test_broker_routes_local_time_to_tool():
    intent = get_intent_classifier().classify("what time is it on my pc?")
    out = get_execution_broker().execute(intent, {}, {})
    assert out["executed"] == ["system_local_time"]
    result = out["results"][0]["result"]
    assert re.fullmatch(r"\d{2}:\d{2}", result["hhmm"])


# ── End-to-end: a short answer, never a manual tutorial ───────────────────────

def test_answer_is_short_and_not_a_tutorial():
    intent = get_intent_classifier().classify("what time is it on my pc?")
    out = get_execution_broker().execute(intent, {}, {})
    reply = ConversationRuntime._summarize_monitoring(out)
    assert "local time on this PC" in reply
    # Must NOT explain how to check manually:
    assert "right" not in reply.lower() and "you can" not in reply.lower()
    assert len(reply) < 120  # one short sentence
