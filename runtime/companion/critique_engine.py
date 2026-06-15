"""Critique engine — the "teammate, not yes-man" advisory layer.

Before the companion commits to a CONSEQUENTIAL request, this engine genuinely
CHALLENGES it: surfaces weak assumptions, real risks, a better/cheaper path, and
explicit push-back when warranted — instead of just complying. It is the
behavioral layer on top of the honest data substrate.

This is ADVISORY reasoning, separate and distinct from the safety/approval gate
(``safety_gate`` / ``execution_broker``). The safety gate decides what is *allowed
to run*; the critique engine decides whether the request is *a good idea* and
whether the teammate should disagree. They are orthogonal — a request can be
safe-to-run yet still deserve push-back, and vice versa.

Design — two-tier, hot-path-cheap (mirrors ``intent_classifier``):
  1. FAST heuristic pass (deterministic, no I/O): detect high-stakes/irreversible
     verbs and weak-premise signals; produce a baseline stance + an
     assumptions/risks skeleton with NO LLM. This is the only path tests
     exercise.
  2. OPTIONAL LLM deepening (env ``COMPANION_CRITIQUE_LLM=1``, default ON):
     a tight JSON-returning prompt with a candid senior-teammate system prompt.
     Validated against the schema; ANY failure → the heuristic result.

Honesty invariant — calibrated BOTH ways:
  - It MUST be able to challenge hard/irreversible requests (don't silently
    comply with "delete all production data").
  - It MUST be able to say "this is sound, proceed" for clear, low-stakes
    requests (don't nag on "summarize this page"). Always-objecting is the
    opposite failure mode and is treated as noise.

Failure invariant
-----------------
``critique`` NEVER throws. On any internal failure it returns a valid, neutral
``proceed`` dict so the turn pipeline is never blocked.
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
from typing import Any, Optional

logger = logging.getLogger("companion.critique_engine")

# ── Stance taxonomy (exact strings — do not rename) ────────────────────────────
STANCE_PROCEED = "proceed"
STANCE_CAUTION = "proceed_with_caution"
STANCE_AGAINST = "recommend_against"
STANCE_NEED_INFO = "need_info"

ALL_STANCES = (STANCE_PROCEED, STANCE_CAUTION, STANCE_AGAINST, STANCE_NEED_INFO)

# ── High-stakes / irreversible verbs (FAST pass). Weighted by severity. ────────
# Word-boundary matched so "deletion" / "spending" still hit but "undelete"
# style false-positives stay bounded. Higher weight ⇒ more severe.
_HIGH_STAKES_TERMS: dict[str, float] = {
    # destructive / irreversible
    "delete": 0.5, "drop": 0.45, "truncate": 0.5, "wipe": 0.6, "destroy": 0.6,
    "purge": 0.45, "rm ": 0.5, "rm -rf": 0.8, "format": 0.4, "erase": 0.5,
    # deploy / ship / mutate prod
    "deploy": 0.4, "release": 0.3, "ship": 0.3, "rollback": 0.35, "roll back": 0.35,
    "migrate": 0.35, "overwrite": 0.4, "force push": 0.5, "force-push": 0.5,
    # money / outreach side effects (hard to take back once sent)
    "spend": 0.45, "pay": 0.4, "charge": 0.4, "purchase": 0.4, "transfer": 0.45,
    "wire": 0.4, "send": 0.25, "email": 0.25, "publish": 0.3, "post": 0.2,
    "broadcast": 0.35, "blast": 0.4,
    # scale / provision (cost + blast radius)
    "scale": 0.3, "provision": 0.3, "spin up": 0.25,
    # secrets / access
    "credential": 0.4, "secret": 0.35, "rotate keys": 0.4, "revoke": 0.35,
}

# Scope amplifiers — multiply blast radius when present alongside a stakes verb.
_SCOPE_AMPLIFIERS: dict[str, float] = {
    "production": 0.3, "prod": 0.25, "all ": 0.2, "everything": 0.25,
    "every ": 0.2, "entire": 0.2, "whole": 0.15, "database": 0.2,
    "customers": 0.2, "users": 0.15, "live": 0.2, "main branch": 0.2,
    "master branch": 0.2,
}

# Bulk-quantity signal (e.g. "email 5000 leads") — large N + outreach = high stakes.
_BULK_RE = re.compile(r"\b(\d[\d,]{2,})\b")  # 100+ (3+ digits)

# Weak-premise signals — vague intent, no success criteria, superlatives that
# hand-wave away the hard part. These push toward 'need_info'.
_WEAK_SUPERLATIVES = (
    "just ", "simply ", "quickly", "obviously", "easy", "trivial",
    "real quick", "asap", "right now", "somehow", "magically",
)
_VAGUE_GOALS = (
    "make it better", "fix everything", "fix it all", "improve everything",
    "clean it up", "sort it out", "handle it", "do the needful",
    "make it work", "optimize everything", "optimise everything",
    "fix all the bugs", "make it good", "make it nice",
)
# Words that, when present, signal a CONCRETE success criterion exists.
_SUCCESS_CRITERIA_CUES = (
    "so that", "until", "target", "goal is", "metric", "by ", "under ",
    "within", "to handle", "to support", "p99", "latency", "pass", "tests",
    "%", "increase", "decrease", "reduce to", "less than", "greater than",
)

_WS = re.compile(r"\s+")
_WORD = re.compile(r"[a-z0-9]+")


def _norm(text: str) -> str:
    return _WS.sub(" ", (text or "").strip().lower())


def _clamp01(v: float) -> float:
    return round(min(1.0, max(0.0, v)), 3)


class CritiqueEngine:
    """Candid senior-teammate critique: challenge hard requests, not easy ones."""

    # Consequential modes the runtime asks us to critique. (Advisory only.)
    CONSEQUENTIAL_MODES = frozenset({"execution", "planning", "debugging"})

    # ── Public surface ──────────────────────────────────────────────────────────
    def critique(self, goal: str, intent: Optional[dict] = None,
                 context: Optional[dict] = None) -> dict:
        """Critique a goal. NEVER raises — returns a valid stance dict always."""
        try:
            intent = intent or {}
            context = context or {}
            base = self._heuristic(goal, intent, context)
            if self._llm_enabled():
                deep = self._llm_deepen(goal, intent, context, base)
                if deep is not None:
                    return deep
            return base
        except Exception as exc:  # noqa: BLE001 — advisory layer must never break a turn
            logger.debug("critique failed, defaulting to proceed: %s", exc)
            return self._result(STANCE_PROCEED, has_concerns=False,
                                confidence=0.3, source="error_fallback")

    # ── Tier 1: fast heuristic (deterministic, no I/O) ──────────────────────────
    def _heuristic(self, goal: str, intent: dict, context: dict) -> dict:
        t = _norm(goal)
        if not t:
            # Empty goal on a command path is itself a need-info case.
            if intent.get("is_command"):
                return self._result(
                    STANCE_NEED_INFO, has_concerns=True, confidence=0.5,
                    clarifying_question="What exactly would you like me to do?",
                    assumptions=["the request is empty/unclear"],
                    source="heuristic")
            return self._result(STANCE_PROCEED, has_concerns=False,
                                confidence=0.5, source="heuristic")

        stakes, stakes_reasons = self._stakes_score(t)
        weak, weak_reasons, vague = self._weak_premise(t)

        assumptions: list[str] = []
        risks: list[str] = []
        alternative: Optional[str] = None
        pushback: Optional[str] = None
        clarifying: Optional[str] = None

        # 1) Vague/weak premise with no concrete success criterion → ask first.
        #    A vague goal on a low-stakes path still warrants a clarifying ask,
        #    but we don't block — we surface the question.
        if vague or (weak and not self._has_success_criteria(t)):
            clarifying = self._clarifying_for(t, vague)
            assumptions.append(
                "the goal is under-specified — success criteria are not stated")
            if weak_reasons:
                assumptions.append(
                    "request implies it's trivial (" + ", ".join(
                        f"'{w}'" for w in weak_reasons[:3]) + ") — that's a premise to check")
            # Need-info dominates only when there's no clear high-stakes action to
            # caution about; otherwise caution + a clarifying question coexist.
            if stakes < 0.3:
                return self._result(
                    STANCE_NEED_INFO, has_concerns=True,
                    confidence=0.6, assumptions=assumptions,
                    clarifying_question=clarifying, source="heuristic")

        # 2) High-stakes / irreversible action → challenge it.
        if stakes >= 0.3:
            risks.extend(self._risks_for(t, stakes_reasons))
            assumptions.append(
                "the action is intended and the blast radius is understood")
            alternative = self._alternative_for(t, stakes_reasons)
            if stakes >= 0.6:
                pushback = (
                    "This is hard to undo. Before I run it, confirm the scope is "
                    "exactly what you intend.")
                stance = STANCE_AGAINST if self._irreversible_no_safeguard(t) \
                    else STANCE_CAUTION
            else:
                pushback = ("This has real side effects. Worth a quick sanity "
                            "check before I proceed.")
                stance = STANCE_CAUTION
            return self._result(
                stance, has_concerns=True,
                confidence=_clamp01(0.55 + stakes * 0.4),
                assumptions=assumptions, risks=risks,
                alternative=alternative, pushback=pushback,
                clarifying_question=clarifying, source="heuristic")

        # 3) Clear, low-stakes request → proceed plainly (NO nagging).
        return self._result(STANCE_PROCEED, has_concerns=False,
                            confidence=0.7, source="heuristic")

    # ── Stakes scoring ──────────────────────────────────────────────────────────
    @staticmethod
    def _stakes_score(t: str) -> tuple[float, list[str]]:
        score = 0.0
        reasons: list[str] = []
        for term, weight in _HIGH_STAKES_TERMS.items():
            if term in t:
                score += weight
                reasons.append(term.strip())
        amp = 0.0
        for term, weight in _SCOPE_AMPLIFIERS.items():
            if term in t:
                amp += weight
                reasons.append(term.strip())
        if reasons:
            score += amp
        # Bulk quantity alongside an outreach/send verb amplifies stakes.
        m = _BULK_RE.search(t)
        if m and any(v in t for v in ("email", "send", "message", "blast",
                                      "post", "publish", "outreach", "contact")):
            n = int(m.group(1).replace(",", ""))
            if n >= 100:
                score += 0.35
                reasons.append(f"bulk volume ({n})")
        return _clamp01(score), reasons

    @staticmethod
    def _irreversible_no_safeguard(t: str) -> bool:
        """True when the action is destructive AND scoped wide with no hedge."""
        destructive = any(k in t for k in (
            "delete", "drop", "wipe", "destroy", "purge", "truncate",
            "rm -rf", "erase", "format"))
        wide = any(k in t for k in (
            "all ", "everything", "entire", "whole", "production", "prod",
            "every ", "database"))
        hedged = any(k in t for k in (
            "dry run", "dry-run", "test", "staging", "backup", "first",
            "preview", "simulate"))
        return destructive and wide and not hedged

    # ── Weak-premise detection ──────────────────────────────────────────────────
    # Contentless 1-2 word imperatives with no concrete object ("fix it",
    # "do that"). A short command that names a real target ("apply patch",
    # "run tests", "restart server") is NOT vague — only pure filler objects are.
    _FILLER_OBJECTS = frozenset({
        "it", "that", "this", "everything", "things", "stuff", "all",
        "them", "those", "these",
    })

    @classmethod
    def _weak_premise(cls, t: str) -> tuple[bool, list[str], bool]:
        vague = any(v in t for v in _VAGUE_GOALS)
        weak_reasons = [w.strip() for w in _WEAK_SUPERLATIVES if w in t]
        # Very short imperative whose ONLY object is filler ("fix it", "do that").
        words = t.split()
        if not vague and len(words) <= 2 and any(
                w in cls._FILLER_OBJECTS for w in words):
            vague = True
        return (bool(weak_reasons) or vague), weak_reasons, vague

    @staticmethod
    def _has_success_criteria(t: str) -> bool:
        return any(c in t for c in _SUCCESS_CRITERIA_CUES)

    @staticmethod
    def _clarifying_for(t: str, vague: bool) -> str:
        if vague:
            return ("Before I dive in — what does 'done' look like here? "
                    "What's the specific outcome and scope you want?")
        return ("What's the success criterion for this — how will we know it "
                "worked, and what's in/out of scope?")

    # ── Risk / alternative phrasing (specific, not boilerplate) ─────────────────
    @staticmethod
    def _risks_for(t: str, reasons: list[str]) -> list[str]:
        risks: list[str] = []
        if any(k in reasons for k in ("delete", "drop", "wipe", "destroy",
                                      "purge", "truncate", "erase", "format",
                                      "rm", "rm -rf")):
            risks.append("Data loss is irreversible without a verified backup.")
        if any(k in reasons for k in ("production", "prod", "live")):
            risks.append("Touching production risks live user impact / downtime.")
        if any(k in reasons for k in ("deploy", "release", "ship", "migrate")):
            risks.append("A bad deploy/migration can be hard to roll back cleanly.")
        if any(k in reasons for k in ("spend", "pay", "charge", "purchase",
                                      "transfer", "wire")):
            risks.append("Spending money is not reversible — confirm the amount "
                         "and recipient.")
        if any(k in reasons for k in ("email", "send", "publish", "post",
                                      "broadcast", "blast")) or any(
                r.startswith("bulk volume") for r in reasons):
            risks.append("Outreach/publish can't be unsent — reputation and "
                         "deliverability are on the line.")
        if any(k in reasons for k in ("secret", "credential", "rotate keys",
                                      "revoke")):
            risks.append("Credential changes can lock out services if mistimed.")
        if not risks:
            risks.append("This action has side effects that are hard to undo.")
        return risks

    @staticmethod
    def _alternative_for(t: str, reasons: list[str]) -> Optional[str]:
        if any(k in reasons for k in ("delete", "drop", "wipe", "destroy",
                                      "purge", "truncate", "erase", "format")):
            return ("Take a backup (or soft-delete / archive) first, then run a "
                    "dry-run on a scoped subset before the real deletion.")
        if any(k in reasons for k in ("deploy", "release", "ship", "migrate")):
            return ("Stage it: deploy to staging, run smoke tests, then a "
                    "canary/gradual rollout with a rollback ready.")
        if any(k in reasons for k in ("email", "send", "publish", "post",
                                      "broadcast", "blast")) or any(
                r.startswith("bulk volume") for r in reasons):
            return ("Send to a small test segment first, verify rendering and "
                    "opt-out handling, then ramp the full send.")
        if any(k in reasons for k in ("spend", "pay", "charge", "purchase",
                                      "transfer", "wire")):
            return ("Start with the smallest viable amount to validate the "
                    "outcome before committing the full spend.")
        if any(k in reasons for k in ("production", "prod", "live")):
            return "Reproduce on staging first so production stays untouched."
        return None

    # ── Tier 2: optional LLM deepening (guarded, schema-validated) ──────────────
    @staticmethod
    def _llm_enabled() -> bool:
        # Default ON in prod; the function still works (heuristic) when off OR
        # when generate() is unavailable. Tests leave the var UNSET to stay on
        # the heuristic path because generate() is offline there.
        return os.getenv("COMPANION_CRITIQUE_LLM", "1").strip() != "0"

    def _llm_deepen(self, goal: str, intent: dict, context: dict,
                    base: dict) -> Optional[dict]:
        """Ask the engine LLM for a candid critique JSON. None on any failure."""
        try:
            from engine.api import generate
        except Exception as exc:  # engine import unavailable → heuristic
            logger.debug("engine.api unavailable for critique: %s", exc)
            return None

        system = (
            "You are a senior teammate, NOT a people-pleaser. Your job is to "
            "improve the outcome, which often means disagreeing. Surface the "
            "strongest objection, the riskiest assumption, and a better path. "
            "Be concise and specific. If the request is sound, say so plainly "
            "and set stance to 'proceed' — do NOT invent concerns. Never invent "
            "facts; reason about risk and alternatives only."
        )
        page = context.get("current_page")
        prompt = (
            "Critique this request before it is executed.\n"
            f"Request: {goal!r}\n"
            f"Mode: {intent.get('mode', '?')}; is_command: "
            f"{bool(intent.get('is_command'))}\n"
            + (f"User is on page: {page}\n" if page else "")
            + "Reply with ONLY a JSON object of this exact shape:\n"
            '{"has_concerns": false, "stance": "proceed", "assumptions": [], '
            '"risks": [], "alternative": null, "pushback": null, '
            '"clarifying_question": null, "confidence": 0.0}\n'
            "stance must be one of: proceed, proceed_with_caution, "
            "recommend_against, need_info."
        )
        try:
            raw = generate(prompt=prompt, system=system,
                           context=None, timeout=30)
        except Exception as exc:  # noqa: BLE001 — LLM down → heuristic
            logger.debug("critique LLM generate failed: %s", exc)
            return None
        parsed = self._parse_llm(raw)
        if parsed is None:
            return None
        parsed["source"] = "llm"
        # Safety net: never let the LLM downgrade a clearly high-stakes heuristic
        # into a bare 'proceed'. If the heuristic flagged concerns, keep at least
        # 'proceed_with_caution' and carry its risks forward.
        if base.get("has_concerns") and parsed.get("stance") == STANCE_PROCEED:
            parsed["stance"] = STANCE_CAUTION
            parsed["has_concerns"] = True
            if not parsed.get("risks"):
                parsed["risks"] = list(base.get("risks") or [])
            if not parsed.get("assumptions"):
                parsed["assumptions"] = list(base.get("assumptions") or [])
        return parsed

    def _parse_llm(self, raw: str) -> Optional[dict]:
        m = re.search(r"\{.*\}", raw or "", re.DOTALL)
        if not m:
            return None
        try:
            data = json.loads(m.group(0))
        except (ValueError, TypeError):
            return None
        if not isinstance(data, dict):
            return None
        stance = str(data.get("stance", "")).strip().lower()
        if stance not in ALL_STANCES:
            return None
        try:
            conf = float(data.get("confidence", 0.6))
        except (ValueError, TypeError):
            conf = 0.6

        def _str_list(v: Any) -> list[str]:
            if isinstance(v, str):
                return [v] if v.strip() else []
            if isinstance(v, (list, tuple)):
                return [str(x).strip() for x in v if str(x).strip()]
            return []

        def _opt_str(v: Any) -> Optional[str]:
            if v is None:
                return None
            s = str(v).strip()
            return s or None

        return self._result(
            stance,
            has_concerns=bool(data.get("has_concerns", stance != STANCE_PROCEED)),
            confidence=conf,
            assumptions=_str_list(data.get("assumptions")),
            risks=_str_list(data.get("risks")),
            alternative=_opt_str(data.get("alternative")),
            pushback=_opt_str(data.get("pushback")),
            clarifying_question=_opt_str(data.get("clarifying_question")),
            source="llm",
        )

    # ── Result shaping ──────────────────────────────────────────────────────────
    @staticmethod
    def _result(stance: str, *, has_concerns: bool, confidence: float,
                assumptions: Optional[list[str]] = None,
                risks: Optional[list[str]] = None,
                alternative: Optional[str] = None,
                pushback: Optional[str] = None,
                clarifying_question: Optional[str] = None,
                source: str = "heuristic") -> dict:
        if stance not in ALL_STANCES:
            stance = STANCE_PROCEED
        return {
            "has_concerns": bool(has_concerns),
            "stance": stance,
            "assumptions": list(assumptions or []),
            "risks": list(risks or []),
            "alternative": alternative,
            "pushback": pushback,
            "clarifying_question": clarifying_question,
            "confidence": _clamp01(confidence),
            "source": source,
        }


# ── Singleton ──────────────────────────────────────────────────────────────────
_instance: Optional[CritiqueEngine] = None
_instance_lock = threading.Lock()


def get_critique_engine() -> CritiqueEngine:
    """Return the process-wide ``CritiqueEngine`` singleton."""
    global _instance
    with _instance_lock:
        if _instance is None:
            _instance = CritiqueEngine()
    return _instance
