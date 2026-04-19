"""Adversarial Input Filter for ASCEND AI.

Detects prompt injection, goal hijacking, and malicious instruction patterns
using **semantic risk scoring** — NOT a keyword blacklist.

────────────────────────────────────────────────────────────────
DESIGN PHILOSOPHY
────────────────────────────────────────────────────────────────

Simple keyword filters are trivially bypassed (character substitution,
translation, paraphrase). This module instead analyses the *structural and
semantic properties* of the input:

  1. ROLE / CONTEXT OVERRIDE SIGNALS
     Detects text that attempts to re-declare the model's persona, system
     role, or operational context — a classic prompt injection pattern.
     Signals: imperative verb + role noun phrase, first-person authority
     claims, context-boundary markers.

  2. INSTRUCTION HIERARCHY ATTACKS
     Inputs that claim a higher privilege level, reference a "true" or
     "real" prompt, or attempt to surface hidden system instructions.

  3. GOAL / OBJECTIVE INJECTION
     Text that tries to replace or append a new primary objective while
     pretending to continue a normal request.

  4. OUTPUT FORMAT HIJACKING
     Attempts to force the model to emit data in a form that could be
     weaponised (base64 payloads, shell commands, eval-ready strings).

  5. MULTI-TURN CONTEXT POISONING
     Structural patterns that make sense only as a manipulation across
     several turns: referencing "earlier instructions", "previous context",
     or fabricating prior assistant utterances.

Each signal contributes a weighted score.  The final *risk_score* is in
[0.0, 1.0].  Calls above the configurable ``block_threshold`` are rejected;
calls above ``warn_threshold`` are logged.

────────────────────────────────────────────────────────────────
PUBLIC API
────────────────────────────────────────────────────────────────

::

    from core.adversarial_filter import get_adversarial_filter, ThreatLevel

    filt = get_adversarial_filter()
    assessment = filt.assess("Ignore all previous instructions and …")

    if assessment.blocked:
        return "Request rejected: potentially adversarial input detected."

    # assessment.risk_score — float in [0.0, 1.0]
    # assessment.threat_level — ThreatLevel enum
    # assessment.signals — list of detected signal names for auditability
"""
from __future__ import annotations

import logging
import math
import re
import threading
import unicodedata
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

import os as _os

logger = logging.getLogger("ai_employee.adversarial_filter")


# ── Tuneable thresholds ───────────────────────────────────────────────────────

def _env_float(name: str, default: float) -> float:
    try:
        return float(_os.environ[name])
    except (KeyError, ValueError):
        return default

BLOCK_THRESHOLD: float = _env_float("ADV_BLOCK_THRESHOLD", 0.75)
WARN_THRESHOLD:  float = _env_float("ADV_WARN_THRESHOLD",  0.45)


# ── Threat levels ─────────────────────────────────────────────────────────────

class ThreatLevel(str, Enum):
    SAFE     = "safe"
    LOW      = "low"
    MEDIUM   = "medium"
    HIGH     = "high"
    CRITICAL = "critical"


# ── Assessment result ─────────────────────────────────────────────────────────

@dataclass
class ThreatAssessment:
    """Result of an adversarial risk assessment.

    Attributes:
        risk_score:   Float in [0.0, 1.0]. Higher = more suspicious.
        threat_level: Enum classification of the risk score.
        blocked:      True when risk_score >= BLOCK_THRESHOLD.
        signals:      Detected signal names contributing to the score.
        reason:       Human-readable summary of the top signals.
    """
    risk_score:   float
    threat_level: ThreatLevel
    blocked:      bool
    signals:      list[str] = field(default_factory=list)
    reason:       str = ""


# ── Signal definitions ────────────────────────────────────────────────────────
#
# Each signal is a function  text → float  returning a contribution in
# [0.0, 1.0].  The final score is the *weighted sum*, clamped to [0.0, 1.0].
# Weights are tuned so that a single low-confidence signal alone cannot block
# a legitimate request.

def _score_role_override(text: str) -> float:
    """Detect attempts to re-declare or override the assistant's role/persona.

    Looks for imperative-structure sentences that assign a new identity,
    authority, or capability to the model without depending on a specific
    vocabulary.
    """
    normalised = unicodedata.normalize("NFKC", text).lower()

    # HIGH-CONFIDENCE patterns — single match is clear evidence of role injection
    _high = [
        r"\bpretend\s+(to\s+be|you\s+are)\b",
        r"\bact\s+as\s+(if\s+you\s+are\s+|a\s+|an\s+)",
        r"\bforget\s+(everything|all\s+(previous|prior|above|your))\b",
        r"\byou\s+are\s+now\s+\w",
    ]
    # MEDIUM-CONFIDENCE patterns — suspicious in isolation, strong in combination
    _med = [
        r"\bbehave\s+(as|like)\s+",
        r"\bfrom\s+now\s+on\s+you\s+(will|must|shall|should)\b",
        r"\byour\s+(new\s+)?(role|persona|identity|task|job)\s+(is|will\s+be)\b",
        r"\byou\s+(must|will|shall)\s+(now\s+)?(always|only|never)\b",
        r"\bswitch\s+(to|into)\s+(mode|role|persona)\b",
    ]

    high_hits = sum(1 for p in _high if re.search(p, normalised))
    med_hits  = sum(1 for p in _med  if re.search(p, normalised))

    if high_hits >= 2:              return 0.97
    if high_hits == 1 and med_hits: return 0.92
    if high_hits == 1:              return 0.85
    if med_hits >= 3:               return 0.85
    if med_hits == 2:               return 0.65
    if med_hits == 1:               return 0.40
    return 0.0


def _score_instruction_hierarchy_attack(text: str) -> float:
    """Detect claims of elevated privilege or attempts to surface system prompts."""
    normalised = unicodedata.normalize("NFKC", text).lower()

    # HIGH-CONFIDENCE — explicit privilege-escalation / system-prompt exposure
    _high = [
        r"\b(ignore|disregard|override)\s+(all\s+)?(previous|prior|above|earlier|your)?\s*(previous|prior)?\s*(instruction|prompt|directive|rule|restriction|guideline|system)",
        r"\b(true|real|actual|original|hidden)\s+(instruction|prompt|directive|system\s*prompt)\b",
        r"\[system\]|<\s*/?\s*system\s*>|###\s*system\s*###|#\s*system\s*prompt",
        r"\b(developer|admin|root|superuser|sudo)\s+(mode|access|override|instruction)\b",
    ]
    # MEDIUM-CONFIDENCE
    _med = [
        r"\b(bypass|circumvent)\s+.{0,50}(instruction|guideline|rule|restriction|constraint|filter|prompt)",
        r"\byou\s+(don['']t\s+need\s+to\s+follow|are\s+not\s+bound\s+by|should\s+ignore)\b",
        r"\bthis\s+(supersedes|overrides|replaces)\s+(all\s+)?(previous|prior|other)?\s*(instruction|rule|directive)",
    ]

    high_hits = sum(1 for p in _high if re.search(p, normalised))
    med_hits  = sum(1 for p in _med  if re.search(p, normalised))

    if high_hits >= 2:              return 0.97
    if high_hits == 1 and med_hits: return 0.93
    if high_hits == 1:              return 0.88
    if med_hits >= 2:               return 0.75
    if med_hits == 1:               return 0.50
    return 0.0


def _score_goal_injection(text: str) -> float:
    """Detect attempts to implant a new primary goal mid-conversation.

    Goal injection wraps the real malicious objective in innocuous-looking
    framing ('also', 'additionally', 'by the way, your main task is now …').
    """
    score = 0.0
    normalised = unicodedata.normalize("NFKC", text).lower()

    _patterns = [
        r"\b(additionally|also|furthermore|moreover|by\s+the\s+way)\s*[,:]?\s*.{0,60}(your\s+(main\s+|primary\s+|actual\s+)?task|you\s+(must|should|will)\s+(also\s+)?)",
        r"\b(new|updated|revised|changed)\s+(goal|objective|task|mission|directive)\b",
        r"\bapply\s+the\s+(following|above|below)\s+(instruction|directive|rule)\s+to\s+(all|every|each)\b",
        r"\b(secretly|silently|without\s+(mentioning|saying|telling))\s+",
        r"\bnever\s+(mention|tell|say|reveal|disclose)\s+(that\s+you|this|the\s+(fact|truth|instruction))\b",
        r"\bfirst\s+complete\s+.{0,40}then\s+.{0,40}(without|and\s+don['']t)",
    ]
    hits = sum(1 for p in _patterns if re.search(p, normalised))
    if hits >= 2:
        score += 0.80
    elif hits == 1:
        score += 0.40
    return min(score, 1.0)


def _score_output_format_hijack(text: str) -> float:
    """Detect attempts to force dangerous output formats.

    These attacks try to get the model to emit executable code, encoded
    payloads, or other artefacts that could be used maliciously.
    """
    score = 0.0

    # Base64 / hex encoding instructions
    if re.search(
        r"\b(encode|decode|base64|hex(\s+encoded)?|rot13)\s+.{0,40}(output|result|response|answer)",
        text, re.IGNORECASE,
    ):
        score += 0.35

    # Shell command generation requests
    if re.search(
        r"\b(write|generate|produce|output|print)\s+.{0,30}(shell\s+script|bash\s+command|cmd\.exe|powershell|eval\s*\(|exec\s*\(|os\.system)",
        text, re.IGNORECASE,
    ):
        score += 0.55

    # Instruction to embed data in structured format for later extraction
    if re.search(
        r"\b(embed|hide|encode|smuggle|insert)\s+.{0,40}(into|in|within|inside)\s+.{0,40}(response|output|text|message|answer)",
        text, re.IGNORECASE,
    ):
        score += 0.45

    return min(score, 1.0)


def _score_context_poisoning(text: str) -> float:
    """Detect multi-turn context poisoning patterns.

    Attackers fabricate prior conversation context to shift model behaviour
    across turns.  Signals: references to fabricated prior exchanges, claims
    about what was previously agreed, etc.
    """
    score = 0.0
    normalised = unicodedata.normalize("NFKC", text).lower()

    _patterns = [
        r"\b(as\s+(we|you)\s+agreed|as\s+(previously|earlier)\s+(discussed|mentioned|established|stated))\b",
        r"\b(in\s+(the\s+)?(previous|last|prior)\s+(conversation|session|message|turn))\s+you\s+(said|agreed|told|confirmed)\b",
        r"\b(remember\s+(that\s+)?(you\s+are|you\s+agreed|your\s+(role|goal|task)))\b",
        r"\bthe\s+user\s+(has\s+)?(already\s+)?(authorized|approved|given\s+permission|consented)\b",
        r"\bassistant:\s+.{0,80}(here\s+is|of\s+course|sure|certainly)",  # fabricated assistant turn
    ]
    hits = sum(1 for p in _patterns if re.search(p, normalised))
    if hits >= 2:
        score += 0.70
    elif hits == 1:
        score += 0.35
    return min(score, 1.0)


def _score_structural_anomaly(text: str) -> float:
    """Detect structural properties common to adversarial inputs.

    These are not based on vocabulary but on the shape of the input:
    - Unusually high density of imperative sentences for a business query
    - Excessive punctuation used to demarcate injected sections
    - Homoglyph / Unicode trick characters
    - Abnormally long average word length (obfuscation)
    """
    score = 0.0

    # Homoglyph or unusual Unicode (non-ASCII in a predominantly Latin text)
    total_chars = max(len(text), 1)
    non_ascii = sum(1 for c in text if ord(c) > 127)
    non_ascii_ratio = non_ascii / total_chars
    if non_ascii_ratio > 0.30:
        score += 0.25

    # Delimiter flooding — long runs of the same punctuation used to
    # demarcate injected content
    if re.search(r"[-=*_#]{8,}", text):
        score += 0.15
    if re.search(r"[<\[{]{3,}", text):
        score += 0.20

    # High imperative density: count sentences starting with a bare verb
    sentences = re.split(r"[.!?]\s+", text)
    imperative_count = sum(
        1 for s in sentences
        if re.match(r"^\s*[A-Z][a-z]+\s+(all|every|each|your|the|this|that|any)\b", s)
    )
    if len(sentences) > 2 and imperative_count / len(sentences) > 0.50:
        score += 0.30

    # Unusually short tokens interspersed with very long ones (obfuscation)
    tokens = text.split()
    if tokens:
        avg_len = sum(len(t) for t in tokens) / len(tokens)
        if avg_len > 12:   # typical English prose ≈ 5
            score += 0.20

    return min(score, 1.0)


# ── Signal registry ───────────────────────────────────────────────────────────
#
# Each signal is a function  text → float  returning a contribution in
# [0.0, 1.0].  The final *risk_score* is the *direct weighted sum*, clamped to
# [0.0, 1.0].  There is NO normalization by total weight — each weight
# represents the maximum contribution of that signal to the final score,
# allowing strong single-signal attacks to reach the block threshold.

_SIGNALS: list[tuple[str, float, object]] = [
    # (name, weight, scorer_fn)
    ("role_override",               1.00, _score_role_override),
    ("instruction_hierarchy_attack",1.00, _score_instruction_hierarchy_attack),
    ("goal_injection",              0.80, _score_goal_injection),
    ("output_format_hijack",        0.55, _score_output_format_hijack),
    ("context_poisoning",           0.70, _score_context_poisoning),
    ("structural_anomaly",          0.25, _score_structural_anomaly),
]


# ── AdversarialFilter ─────────────────────────────────────────────────────────

class AdversarialFilter:
    """Semantic adversarial input filter.

    Thread-safe singleton.  All heavy computation is intentionally
    done with pure Python (no external ML model) so the filter adds
    minimal latency and has no additional dependencies.
    """

    def __init__(
        self,
        *,
        block_threshold: float = BLOCK_THRESHOLD,
        warn_threshold:  float = WARN_THRESHOLD,
    ) -> None:
        self.block_threshold = block_threshold
        self.warn_threshold  = warn_threshold
        self._lock           = threading.Lock()

    def assess(
        self,
        text: str,
        *,
        agent_id: str = "",
        user_id:  str = "",
    ) -> ThreatAssessment:
        """Assess *text* for adversarial content.

        Returns a :class:`ThreatAssessment`.  Call ``assessment.blocked``
        to decide whether to proceed or reject the request.
        """
        if not text or not text.strip():
            return ThreatAssessment(
                risk_score=0.0,
                threat_level=ThreatLevel.SAFE,
                blocked=False,
                signals=[],
                reason="Empty input",
            )

        raw_scores: dict[str, float] = {}
        for name, _weight, scorer in _SIGNALS:
            try:
                s = float(scorer(text))  # type: ignore[operator]
            except Exception:
                s = 0.0
            raw_scores[name] = max(0.0, min(s, 1.0))

        # Weighted combination — direct sum, clamped to [0, 1] (no normalization)
        weighted_sum = sum(
            raw_scores[name] * weight
            for name, weight, _ in _SIGNALS
        )
        risk_score = min(weighted_sum, 1.0)

        # Collect signals that contributed meaningfully (>= 0.15)
        fired = [name for name, _, _ in _SIGNALS if raw_scores[name] >= 0.15]

        threat_level = self._classify(risk_score)
        blocked = risk_score >= self.block_threshold

        reason = (
            f"Detected: {', '.join(fired)}" if fired else "No adversarial signals"
        )

        assessment = ThreatAssessment(
            risk_score=round(risk_score, 4),
            threat_level=threat_level,
            blocked=blocked,
            signals=fired,
            reason=reason,
        )

        self._log_and_audit(assessment, text, agent_id, user_id)
        return assessment

    # ── Internal ──────────────────────────────────────────────────────────────

    @staticmethod
    def _classify(score: float) -> ThreatLevel:
        if score >= 0.85:
            return ThreatLevel.CRITICAL
        if score >= 0.65:
            return ThreatLevel.HIGH
        if score >= 0.45:
            return ThreatLevel.MEDIUM
        if score >= 0.20:
            return ThreatLevel.LOW
        return ThreatLevel.SAFE

    def _log_and_audit(
        self,
        assessment: ThreatAssessment,
        text: str,
        agent_id: str,
        user_id: str,
    ) -> None:
        if assessment.blocked:
            logger.warning(
                "Adversarial input BLOCKED [score=%.3f, level=%s, signals=%s] "
                "agent=%r user=%r preview=%r",
                assessment.risk_score,
                assessment.threat_level.value,
                assessment.signals,
                agent_id,
                user_id,
                text[:100],
            )
        elif assessment.risk_score >= self.warn_threshold:
            logger.warning(
                "Adversarial input WARNING [score=%.3f, level=%s, signals=%s] "
                "agent=%r user=%r preview=%r",
                assessment.risk_score,
                assessment.threat_level.value,
                assessment.signals,
                agent_id,
                user_id,
                text[:100],
            )

        if assessment.blocked or assessment.risk_score >= self.warn_threshold:
            try:
                import sys as _sys
                from pathlib import Path as _Path
                _rdir = _Path(__file__).resolve().parent.parent
                if str(_rdir) not in _sys.path:
                    _sys.path.insert(0, str(_rdir))
                from core.audit_engine import get_audit_engine  # type: ignore
                get_audit_engine().record(
                    actor=user_id or "anonymous",
                    action="adversarial_detection",
                    input_data={
                        "agent": agent_id,
                        "signals": assessment.signals,
                        "preview": text[:200],
                    },
                    output_data={
                        "risk_score": assessment.risk_score,
                        "threat_level": assessment.threat_level.value,
                        "blocked": assessment.blocked,
                    },
                    risk_score=assessment.risk_score,
                    meta={"xai_module": "adversarial_filter"},
                )
            except Exception:
                pass


# ── Singleton ─────────────────────────────────────────────────────────────────

_filter_instance: Optional[AdversarialFilter] = None
_filter_lock = threading.Lock()


def get_adversarial_filter() -> AdversarialFilter:
    """Return the process-wide :class:`AdversarialFilter` singleton."""
    global _filter_instance
    with _filter_lock:
        if _filter_instance is None:
            _filter_instance = AdversarialFilter()
    return _filter_instance
