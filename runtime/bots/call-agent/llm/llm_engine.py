"""Two-layer LLM Decision Engine for the AI call agent.

Layer 1 — FAST (rule-based):
  Pattern-matches common intents and returns pre-written templates instantly.
  Response time: < 50 ms.

Layer 2 — SLOW (Ollama / cloud AI):
  Full LLM reasoning for complex or ambiguous queries.
  Response time: 500 ms – 2 s.

If the LLM layer exceeds CALL_LLM_TIMEOUT_SECONDS or raises an exception,
the engine returns a safe fallback response.

Agent persona: car-dealership sales agent.
  - Max 2 sentences per response.
  - Always steer toward booking an appointment.
  - Never say you are an AI.

Config env vars:
    CALL_LLM_TIMEOUT_SECONDS  — max seconds for LLM response (default: 4)
    CALL_AGENT_NAME           — agent first name spoken to callers (default: Alex)
    CALL_DEALER_NAME          — dealership trading name (default: AutoPrime)
    CALL_FALLBACK_RESPONSE    — override the default fallback line
"""
import logging
import os
import re
import sys
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger("call-agent.llm")

LLM_TIMEOUT = int(os.environ.get("CALL_LLM_TIMEOUT_SECONDS", "4"))
AGENT_NAME = os.environ.get("CALL_AGENT_NAME", "Alex")
DEALER_NAME = os.environ.get("CALL_DEALER_NAME", "AutoPrime")
FALLBACK_RESPONSE = os.environ.get(
    "CALL_FALLBACK_RESPONSE",
    "Sorry, een moment — ik verbind je door met een collega.",
)

AI_HOME = Path(os.environ.get("AI_HOME", str(Path.home() / ".ai-employee")))
_ai_router_path = AI_HOME / "bots" / "ai-router"
if str(_ai_router_path) not in sys.path:
    sys.path.insert(0, str(_ai_router_path))

try:
    from ai_router import query_ai_for_agent as _query_ai_for_agent  # type: ignore
    _AI_AVAILABLE = True
except ImportError:
    _AI_AVAILABLE = False

    def _query_ai_for_agent(*a, **kw):  # type: ignore
        return {"answer": ""}


_SYSTEM_PROMPT = (
    f"Je bent {AGENT_NAME}, een vriendelijke en zelfverzekerde verkoopadviseur bij {DEALER_NAME}. "
    "Je spreekt met potentiële klanten via de telefoon. "
    "Regels: "
    "1. Maximaal 2 zinnen per antwoord. "
    "2. Stuur het gesprek altijd richting het boeken van een proefrit of afspraak. "
    "3. Geef bij prijsvragen altijd een prijsrange en nodig meteen uit voor een bezoek. "
    "4. Bij twijfel of bezwaar: creëer urgentie — 'Dit model krijgt veel interesse, dus slim om snel te komen kijken.' "
    "5. Stel bij onduidelijkheid één gerichte vraag. "
    "6. Noem nooit dat je een AI bent. "
    "7. Spreek altijd Nederlands, tenzij de klant een andere taal gebruikt. "
    "Antwoord uitsluitend met de gesproken tekst — geen uitleg, geen code."
)

_GREETING = (
    f"Goeiedag, u spreekt met {AGENT_NAME} van {DEALER_NAME}, "
    "hoe kan ik u vandaag helpen?"
)

_FAST_RULES: list[tuple[re.Pattern, str]] = [
    (
        re.compile(r"\b(openingstijden?|open|gesloten|wanneer open)\b", re.I),
        "We zijn open van maandag t/m zaterdag van 9 tot 18 uur. "
        "Wilt u meteen een afspraak inplannen zodat we u persoonlijk kunnen ontvangen?",
    ),
    (
        re.compile(r"\b(adres|locatie|waar|hoe kom ik|rijden naar)\b", re.I),
        f"U vindt ons op het adres dat op onze website staat bij {DEALER_NAME}. "
        "Zal ik een afspraak voor u inplannen zodat we klaarstaan als u aankomt?",
    ),
    (
        re.compile(r"\b(proefrit|test|uitproberen|rijden)\b", re.I),
        "Een proefrit is altijd mogelijk — dat is de beste manier om zeker te weten dat de auto bij u past. "
        "Wanneer schikt het u om langs te komen?",
    ),
    (
        re.compile(r"\b(afspraak|boeken|reserveren|inplannen|kom langs)\b", re.I),
        "Geweldig, dan plannen we dat meteen voor u in. "
        "Welke dag en tijdstip komt u het beste uit?",
    ),
    (
        re.compile(r"\b(bedankt?|dankjewel|dank u|tot ziens|dag|doei)\b", re.I),
        f"Graag gedaan! We zien u snel bij {DEALER_NAME} — een fijne dag verder.",
    ),
    (
        re.compile(r"\b(inruilen?|inruil|mijn auto|old[e]? auto)\b", re.I),
        "We nemen zeker uw huidige auto in overweging als inruil — dat regelen we ter plekke. "
        "Komt u langs voor een gratis taxatie en proefrit?",
    ),
    (
        re.compile(r"\b(financier|lening|leas[e]?|maandbed[r]?ag|betalen|betaling)\b", re.I),
        "We bieden flexibele financieringsopties aan, ook voor private lease. "
        "Kom langs voor een persoonlijk voorstel op maat — wanneer schikt dat?",
    ),
    (
        re.compile(r"\b(garantie|apk|onderhoud|service|reparatie)\b", re.I),
        "Al onze voertuigen worden geleverd met garantie en volledige APK-keuring. "
        "Wilt u dat persoonlijk bespreken? Ik plan graag een afspraak voor u in.",
    ),
]

_CACHE: dict[str, tuple[float, str]] = {}
_CACHE_TTL = 300.0


def _fast_layer(text: str) -> Optional[str]:
    """Return a template response if the input matches a known pattern."""
    for pattern, response in _FAST_RULES:
        if pattern.search(text):
            logger.debug("Fast layer matched: %s", pattern.pattern)
            return response
    return None


def _cache_key(text: str, intent: str) -> str:
    return f"{intent}::{text[:80].lower().strip()}"


def _get_cached(key: str) -> Optional[str]:
    entry = _CACHE.get(key)
    if entry and time.monotonic() - entry[0] < _CACHE_TTL:
        return entry[1]
    return None


def _set_cached(key: str, value: str) -> None:
    _CACHE[key] = (time.monotonic(), value)
    if len(_CACHE) > 200:
        oldest = min(_CACHE, key=lambda k: _CACHE[k][0])
        _CACHE.pop(oldest, None)


def _slow_layer(text: str, history: list, intent: str) -> str:
    """LLM layer — Ollama via ai_router with a timeout guard."""
    if not _AI_AVAILABLE:
        return FALLBACK_RESPONSE

    cache_key = _cache_key(text, intent)
    cached = _get_cached(cache_key)
    if cached:
        logger.debug("LLM cache hit for key: %s", cache_key[:60])
        return cached

    messages = []
    for msg in history[-6:]:
        role = msg.get("role", "user")
        if role not in ("user", "assistant"):
            continue
        messages.append({"role": role, "content": msg.get("content", "")})
    messages.append({"role": "user", "content": text})

    start = time.monotonic()
    try:
        result = _query_ai_for_agent(
            "call-agent",
            text,
            system_prompt=_SYSTEM_PROMPT,
            history=messages[:-1],
        )
        elapsed = time.monotonic() - start
        answer = (result or {}).get("answer", "").strip()
        if not answer:
            return FALLBACK_RESPONSE
        if elapsed > LLM_TIMEOUT:
            logger.warning("LLM response exceeded timeout %.1fs", elapsed)
            return FALLBACK_RESPONSE
        _set_cached(cache_key, answer)
        logger.debug("LLM answered in %.2fs", elapsed)
        return answer
    except Exception as exc:
        logger.warning("LLM error: %s — returning fallback", exc)
        return FALLBACK_RESPONSE


def get_greeting() -> str:
    return _GREETING


def generate_response(
    user_text: str,
    history: list,
    intent: str = "unknown",
    turn: int = 0,
) -> tuple[str, str]:
    """Return (response_text, updated_intent).

    Tries fast layer first; falls back to LLM layer.
    """
    if not user_text.strip():
        return (
            "Ik hoorde u niet goed — kunt u dat herhalen?",
            intent,
        )

    fast = _fast_layer(user_text)
    if fast:
        updated_intent = _detect_intent(user_text, intent)
        return fast, updated_intent

    updated_intent = _detect_intent(user_text, intent)
    response = _slow_layer(user_text, history, updated_intent)
    return response, updated_intent


def _detect_intent(text: str, current: str) -> str:
    """Simple keyword-based intent detection."""
    text_lower = text.lower()
    if re.search(r"\b(afspraak|afspraken|boek|reserveer|plannen|inplannen|proefrit)\b", text_lower):
        return "appointment"
    if re.search(r"\b(prijs|kosten|euro|duur|goedkoop|budget|betalen|financier)\b", text_lower):
        return "price_inquiry"
    if re.search(r"\b(model|type|auto|wagen|voertuig|elektrisch|hybride|benzine|diesel)\b", text_lower):
        return "product_inquiry"
    if re.search(r"\b(inruil|inruilen)\b", text_lower):
        return "trade_in"
    if re.search(r"\b(contact|terugbellen|email|whatsapp|bereiken)\b", text_lower):
        return "contact"
    return current if current != "unknown" else "general"
