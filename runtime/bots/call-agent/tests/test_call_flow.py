"""Tests for AI Call Agent — simulate local call flows without Twilio.

Run with:
    python3 tests/test_call_flow.py

Tests:
  1. Missed call callback simulation
  2. Lead qualification flow
  3. Appointment booking flow
  4. Price inquiry handling
  5. Fallback / LLM-unavailable path
"""
from __future__ import annotations

import sys
import os
from pathlib import Path
import time

_bot_dir = Path(__file__).parent.parent
for _sub in ("llm", "memory", "stt", "telephony", "tts"):
    _p = str(_bot_dir / _sub)
    if _p not in sys.path:
        sys.path.insert(0, _p)

from llm_engine import generate_response, get_greeting, _fast_layer, _detect_intent  # type: ignore
from conversation_manager import ConversationManager  # type: ignore
from twilio_handler import (  # type: ignore
    build_greeting_twiml,
    build_response_twiml,
    build_fallback_twiml,
    parse_twilio_params,
)

_GREEN = "\033[0;32m"
_RED = "\033[0;31m"
_YELLOW = "\033[1;33m"
_NC = "\033[0m"
_results: list[tuple[str, bool, str]] = []


def _ok(name: str, detail: str = "") -> None:
    print(f"  {_GREEN}✅{_NC} {name}{(' — ' + detail) if detail else ''}")
    _results.append((name, True, detail))


def _fail(name: str, detail: str = "") -> None:
    print(f"  {_RED}❌{_NC} {name}{(' — ' + detail) if detail else ''}")
    _results.append((name, False, detail))


def _section(title: str) -> None:
    print(f"\n\033[1m\033[0;36m── {title} {'─' * max(0, 44 - len(title))}\033[0m")


def test_greeting() -> None:
    greeting = get_greeting()
    if greeting and len(greeting) > 10:
        _ok("Greeting generated", repr(greeting[:60]))
    else:
        _fail("Greeting generated", f"got: {repr(greeting)}")


def test_twiml_greeting() -> None:
    twiml = build_greeting_twiml("Goeiedag, hoe kan ik u helpen?")
    if "<Response>" in twiml and "<Gather" in twiml and "<Say" in twiml:
        _ok("Greeting TwiML valid", "contains Response/Gather/Say")
    else:
        _fail("Greeting TwiML valid", repr(twiml[:120]))


def test_twiml_response() -> None:
    twiml = build_response_twiml("Wanneer schikt een afspraak?")
    if "<Response>" in twiml and "<Gather" in twiml:
        _ok("Response TwiML valid")
    else:
        _fail("Response TwiML valid", repr(twiml[:120]))


def test_twiml_fallback() -> None:
    twiml = build_fallback_twiml()
    if "<Response>" in twiml:
        _ok("Fallback TwiML valid")
    else:
        _fail("Fallback TwiML valid", repr(twiml[:120]))


def test_fast_layer_opening_hours() -> None:
    result = _fast_layer("Wanneer zijn jullie open?")
    if result and "open" in result.lower():
        _ok("Fast layer: openingstijden", repr(result[:60]))
    else:
        _fail("Fast layer: openingstijden", repr(result))


def test_fast_layer_appointment() -> None:
    result = _fast_layer("Ik wil een afspraak maken")
    if result and len(result) > 10:
        _ok("Fast layer: afspraak", repr(result[:60]))
    else:
        _fail("Fast layer: afspraak", repr(result))


def test_fast_layer_proefrit() -> None:
    result = _fast_layer("Kan ik een proefrit doen?")
    if result and "proefrit" in result.lower():
        _ok("Fast layer: proefrit", repr(result[:60]))
    else:
        _fail("Fast layer: proefrit", repr(result))


def test_intent_detection_appointment() -> None:
    intent = _detect_intent("Ik wil een afspraak boeken voor morgen", "unknown")
    if intent == "appointment":
        _ok("Intent: appointment detected")
    else:
        _fail("Intent: appointment detected", f"got {intent!r}")


def test_intent_detection_price() -> None:
    intent = _detect_intent("Wat is de prijs van een Tesla?", "unknown")
    if intent == "price_inquiry":
        _ok("Intent: price_inquiry detected")
    else:
        _fail("Intent: price_inquiry detected", f"got {intent!r}")


def test_intent_detection_product() -> None:
    intent = _detect_intent("Ik zoek een elektrische auto", "unknown")
    if intent == "product_inquiry":
        _ok("Intent: product_inquiry detected")
    else:
        _fail("Intent: product_inquiry detected", f"got {intent!r}")


def test_conversation_manager_session() -> None:
    mgr = ConversationManager()
    session = mgr.get_or_create("CA_test_001", "+31612345678")
    if session["call_sid"] == "CA_test_001" and session["caller"] == "+31612345678":
        _ok("ConversationManager: session created")
    else:
        _fail("ConversationManager: session created", repr(session))


def test_conversation_manager_messages() -> None:
    mgr = ConversationManager()
    mgr.get_or_create("CA_test_002", "+31612345678")
    mgr.add_message("CA_test_002", "user", "Goeiedag")
    mgr.add_message("CA_test_002", "assistant", "Hoe kan ik u helpen?")
    history = mgr.get_history("CA_test_002")
    if len(history) == 2 and history[0]["role"] == "user":
        _ok("ConversationManager: message history", f"{len(history)} messages")
    else:
        _fail("ConversationManager: message history", repr(history))


def test_conversation_manager_update() -> None:
    mgr = ConversationManager()
    mgr.get_or_create("CA_test_003")
    mgr.update("CA_test_003", intent="appointment", appointment_booked=True)
    session = mgr.get("CA_test_003")
    if session and session["intent"] == "appointment" and session["appointment_booked"]:
        _ok("ConversationManager: update fields")
    else:
        _fail("ConversationManager: update fields", repr(session))


def test_response_generation_fast() -> None:
    """Fast layer should respond instantly to known patterns."""
    start = time.monotonic()
    response, intent = generate_response("Ik wil een afspraak maken", [], "unknown", 0)
    elapsed = time.monotonic() - start
    if response and elapsed < 0.5:
        _ok("Response generation (fast layer)", f"{elapsed*1000:.0f}ms  {repr(response[:60])}")
    else:
        _fail("Response generation (fast layer)", f"{elapsed*1000:.0f}ms  {repr(response[:60])}")


def test_response_empty_input() -> None:
    response, _ = generate_response("", [], "unknown", 0)
    if response and "herhalen" in response.lower():
        _ok("Response: empty input handled", repr(response[:60]))
    else:
        _fail("Response: empty input handled", repr(response))


def test_parse_twilio_params() -> None:
    raw = b"CallSid=CA1234&From=%2B31612345678&SpeechResult=Hallo+wereld"
    params = parse_twilio_params(raw)
    if params.get("CallSid") == "CA1234" and params.get("From") == "+31612345678":
        _ok("parse_twilio_params: decodes URL-encoded body")
    else:
        _fail("parse_twilio_params", repr(params))


def _simulate_call_flow(label: str, turns: list[str]) -> None:
    """Run a multi-turn conversation and verify we always get a response."""
    mgr = ConversationManager()
    sid = f"CA_sim_{label}"
    mgr.get_or_create(sid, "+31699999999")
    greeting = get_greeting()
    mgr.add_message(sid, "assistant", greeting)

    ok = True
    for user_text in turns:
        history = mgr.get_history(sid)
        session = mgr.get(sid)
        intent = session.get("intent", "unknown") if session else "unknown"
        turn = session.get("turn", 0) if session else 0
        response, new_intent = generate_response(user_text, history, intent, turn)
        mgr.add_message(sid, "user", user_text)
        mgr.add_message(sid, "assistant", response)
        mgr.update(sid, intent=new_intent)
        if not response or len(response) < 5:
            ok = False
            break

    final_history = mgr.get_history(sid)
    if ok and len(final_history) >= len(turns) * 2 + 1:
        _ok(f"Call flow: {label}", f"{len(final_history)} messages")
    else:
        _fail(f"Call flow: {label}", f"history={len(final_history)} ok={ok}")


def test_missed_call_callback_flow() -> None:
    _simulate_call_flow("missed_call_callback", [
        "Ik belde net maar niemand nam op",
        "Ik ben geïnteresseerd in een nieuwe auto",
        "Wanneer kan ik langskomen?",
    ])


def test_lead_qualification_flow() -> None:
    _simulate_call_flow("lead_qualification", [
        "Ik zoek een betrouwbare gezinsauto",
        "Budget rond de twintigduizend euro",
        "Kan ik inruilen?",
        "Oké, wanneer kunnen we een afspraak maken?",
    ])


def test_appointment_booking_flow() -> None:
    _simulate_call_flow("appointment_booking", [
        "Ik wil een afspraak maken voor een proefrit",
        "Zaterdag om 11 uur",
        "Super, bedankt!",
    ])


def main() -> None:
    print("\n\033[1m" + "=" * 52 + "\033[0m")
    print("\033[1m  🧪 AI Call Agent — Call Flow Tests\033[0m")
    print("\033[1m" + "=" * 52 + "\033[0m")

    _section("TwiML Generation")
    test_twiml_greeting()
    test_twiml_response()
    test_twiml_fallback()

    _section("Greeting")
    test_greeting()

    _section("Fast Layer (rule-based)")
    test_fast_layer_opening_hours()
    test_fast_layer_appointment()
    test_fast_layer_proefrit()

    _section("Intent Detection")
    test_intent_detection_appointment()
    test_intent_detection_price()
    test_intent_detection_product()

    _section("Conversation Manager")
    test_conversation_manager_session()
    test_conversation_manager_messages()
    test_conversation_manager_update()

    _section("Response Generation")
    test_response_generation_fast()
    test_response_empty_input()

    _section("Twilio Utilities")
    test_parse_twilio_params()

    _section("End-to-End Call Flows")
    test_missed_call_callback_flow()
    test_lead_qualification_flow()
    test_appointment_booking_flow()

    total = len(_results)
    passed = sum(1 for _, ok, _ in _results if ok)
    failed = total - passed

    print(f"\n\033[1m{'=' * 52}\033[0m")
    print(f"\033[1m  Result: {passed}/{total} tests passed\033[0m")
    if failed:
        print(f"  \033[0;31m❌ {failed} test(s) FAILED\033[0m")
    else:
        print(f"  \033[0;32m✅ All tests passed!\033[0m")
    print(f"\033[1m{'=' * 52}\033[0m\n")

    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
