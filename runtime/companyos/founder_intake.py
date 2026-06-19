"""FounderIntake — turn a raw idea into a structured brief, surfacing gaps.

Anti-Polsia: never accept a blind "surprise me" and silently build. Missing
essentials (target customer, problem, monetization) are returned as
clarifying questions so the human fills them before any spend.
"""
from __future__ import annotations

import threading

# The essentials a viable build needs. Absence → a clarifying question, not a guess.
_REQUIRED = ("target_customer", "problem", "monetization")
_OPTIONAL = ("differentiation", "budget", "channels", "constraints")

_QUESTION = {
    "target_customer": "Who exactly is the customer? (role, company size, segment)",
    "problem": "What specific, painful problem does this solve for them?",
    "monetization": "How does it make money? (pricing model + who pays)",
}


def _llm(prompt: str, system: str) -> str | None:
    try:
        from engine.api import generate
        return (generate(prompt=prompt, system=system, timeout=60) or "").strip() or None
    except Exception:  # noqa: BLE001
        return None


class FounderIntake:
    def build_brief(self, idea: str, answers: dict | None = None) -> dict:
        """idea + optional answers → {brief, open_questions, ready: bool, surprise_me_warning}."""
        idea = (idea or "").strip()
        answers = answers or {}
        surprise = idea.lower() in ("", "surprise me", "anything", "you decide")

        brief: dict = {"idea": idea}
        for k in (*_REQUIRED, *_OPTIONAL):
            if answers.get(k):
                brief[k] = answers[k]

        # Optional LLM enrichment to infer fields from a rich idea (never invents
        # the required essentials — those must be answered, not guessed).
        if idea and not surprise:
            text = _llm(
                f"From this startup idea, extract any of {list(_OPTIONAL)} that are "
                f"clearly stated. Idea: {idea}. Reply as 'key: value' lines, only for "
                "fields actually present.",
                "You extract only stated facts. Never invent customer, problem, or pricing.")
            if text:
                for line in text.splitlines():
                    if ":" in line:
                        k, _, v = line.partition(":")
                        k = k.strip().lower()
                        if k in _OPTIONAL and v.strip() and k not in brief:
                            brief[k] = v.strip()

        open_questions = [_QUESTION[k] for k in _REQUIRED if not brief.get(k)]
        ready = not open_questions and not surprise
        return {
            "brief": brief,
            "open_questions": open_questions,
            "ready": ready,
            "surprise_me_warning": (
                "No concrete idea given. Building on an unvalidated 'surprise me' is the "
                "single biggest reason AI company-builders waste money — answer the "
                "essentials first." if surprise else None),
        }


_instance: FounderIntake | None = None
_instance_lock = threading.Lock()


def get_founder_intake() -> FounderIntake:
    global _instance
    with _instance_lock:
        if _instance is None:
            _instance = FounderIntake()
    return _instance
