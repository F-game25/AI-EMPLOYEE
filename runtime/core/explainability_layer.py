"""Explainability Layer for ASCEND AI.

XAI (Explainable AI) module that produces structured, human-readable
explanations for every AI decision without exposing raw chain-of-thought.

────────────────────────────────────────────────────────────────
DESIGN GOALS
────────────────────────────────────────────────────────────────

1. Every LLM response can be paired with a structured Explanation:
   - reason          : concise summary of *why* the decision was made
   - key_factors     : ranked list of influencing factors
   - alternatives    : other options the agent considered or could have taken
   - confidence      : 0.0–1.0 score based on linguistic confidence signals

2. No unsafe chain-of-thought exposure:
   The raw internal reasoning is never surfaced.  Instead a short,
   summarised explanation is derived from the response text and context.

3. Audit integration:
   Every explanation is persisted via AuditEngine so it is traceable.

4. Modular & non-breaking:
   The engine is optional — if not imported, existing behaviour is unchanged.
   All errors are swallowed so a failing explainability check can never
   break the core response pipeline.

5. Async-compatible:
   All public methods are synchronous but safe to call from
   ``asyncio.run_in_threadpool``.

────────────────────────────────────────────────────────────────
PUBLIC API
────────────────────────────────────────────────────────────────

::

    from core.explainability_layer import get_explain_engine, ExplainContext

    ctx = ExplainContext(
        agent="recruiter",
        action="rank_candidate",
        message="Rank these 3 candidates",
        response="Candidate A is ranked first because …",
        model="gpt-4o",
        user_id="user:alice",
    )
    exp = get_explain_engine().explain(ctx)
    # exp.reason         → "Candidate A ranked first based on …"
    # exp.key_factors    → ["experience match", "skill alignment", …]
    # exp.alternatives   → ["Candidate B was close due to …"]
    # exp.confidence     → 0.82
    # exp.explain_id     → "xai-abc123def456"
    # exp.to_dict()      → serialisable dict safe for API responses
"""
from __future__ import annotations

import re
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field, asdict
from typing import Any

# ── Confidence signals ────────────────────────────────────────────────────────

# Phrases that reduce confidence
_HEDGE_PAT = re.compile(
    r"\b(may|might|could|perhaps|possibly|probably|likely|seemingly|"
    r"it seems|i think|i believe|not sure|uncertain|unclear|hard to say|"
    r"approximately|roughly|around|estimated|generally|typically|often)\b",
    re.IGNORECASE,
)

# Phrases that increase confidence
_DEFINITE_PAT = re.compile(
    r"\b(definitely|certainly|clearly|obviously|always|never|must|will|is|are|"
    r"has|have|confirmed|proven|guaranteed|exactly|precisely|specifically|"
    r"the best|the only|the correct|the right)\b",
    re.IGNORECASE,
)

# Causal / reasoning signal phrases (indicate the response contains an explanation)
_CAUSAL_PAT = re.compile(
    r"\b(because|since|due to|as a result|therefore|hence|thus|given that|"
    r"based on|owing to|in light of|as|so that)\b",
    re.IGNORECASE,
)

# Alternative-consideration markers
_ALT_PAT = re.compile(
    r"\b(alternatively|however|another option|you could also|on the other hand|"
    r"instead|or you could|one alternative|other approach|consider|though|"
    r"whereas|unlike|compared to)\b",
    re.IGNORECASE,
)

# Sentence splitter
_SENTENCE_PAT = re.compile(r"(?<=[.!?])\s+")

# Max chars for a reason or alternative summary
_REASON_MAX_LEN = 280
_ALT_MAX_LEN = 200
_FACTOR_MAX_LEN = 80
_MAX_FACTORS = 5
_MAX_ALTERNATIVES = 3

# In-process explanation cache size
_CACHE_SIZE = int(__import__("os").environ.get("XAI_CACHE_SIZE", "500"))


def _ts() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# ── Data structures ───────────────────────────────────────────────────────────

@dataclass
class ExplainContext:
    """Input to a single explanation request."""
    agent: str
    action: str
    message: str          # the user / system prompt that triggered the response
    response: str         # the raw LLM / agent response text
    model: str = ""
    user_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    session_id: str = field(default_factory=lambda: uuid.uuid4().hex[:10])


@dataclass
class Explanation:
    """Structured XAI explanation for one AI decision.

    All fields are safe for external consumption — no raw chain-of-thought.
    """
    explain_id: str = field(default_factory=lambda: f"xai-{uuid.uuid4().hex[:12]}")
    ts: str = field(default_factory=_ts)
    agent: str = ""
    action: str = ""
    model: str = ""
    user_id: str = ""
    # Core XAI fields
    reason: str = ""              # concise human-readable reason for the decision
    key_factors: list[str] = field(default_factory=list)   # ranked influencing factors
    alternatives: list[str] = field(default_factory=list)  # alternatives considered
    confidence: float = 0.5       # 0.0 (very uncertain) – 1.0 (very confident)
    confidence_label: str = "medium"  # low | medium | high
    # Safety flag — always True; raw reasoning is never included
    safe: bool = True
    # Non-fatal error (if extraction partially failed)
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ── Confidence scoring ────────────────────────────────────────────────────────

def _score_confidence(response: str) -> float:
    """Heuristic confidence score (0.0–1.0) from response language.

    Algorithm:
    - Base = 0.60 (moderate default)
    - Each hedge phrase     → −0.04 (floor 0.10)
    - Each definite phrase  → +0.03 (cap 0.95)
    - Causal phrases present → +0.05 (the agent explains itself)
    - Very short response   → −0.10 (less grounded)
    """
    hedges = len(_HEDGE_PAT.findall(response))
    definites = len(_DEFINITE_PAT.findall(response))
    causals = 1 if _CAUSAL_PAT.search(response) else 0

    score = 0.60
    score -= hedges * 0.04
    score += definites * 0.03
    score += causals * 0.05
    if len(response) < 80:
        score -= 0.10

    return round(max(0.10, min(0.95, score)), 2)


def _confidence_label(score: float) -> str:
    if score >= 0.70:
        return "high"
    if score >= 0.40:
        return "medium"
    return "low"


# ── Key factor extraction ─────────────────────────────────────────────────────

# Agent-domain factor templates — agent-specific context signals added to factors
_AGENT_DOMAIN_FACTORS: dict[str, list[str]] = {
    "recruiter":          ["candidate qualifications", "role fit", "experience match"],
    "hr-manager":         ["policy compliance", "role requirements", "team dynamics"],
    "lead-scorer":        ["engagement signals", "intent indicators", "profile match"],
    "qualification-agent":["qualification criteria", "lead quality", "conversion potential"],
    "lead-intelligence":  ["market signals", "prospect data", "outreach history"],
    "financial":          ["risk profile", "market conditions", "return potential"],
    "brand-strategist":   ["brand positioning", "audience alignment", "messaging clarity"],
    "customer-profiling": ["behavioural signals", "demographic data", "interaction history"],
}


def _extract_key_factors(agent: str, message: str, response: str) -> list[str]:
    """Extract up to _MAX_FACTORS ranked key factors from the response.

    Strategy:
    1. Look for causal sentences (contain "because", "since", "due to", etc.)
       and pull noun-phrase fragments from them.
    2. Append agent-domain factors when space remains.
    3. Deduplicate and truncate.
    """
    factors: list[str] = []
    sentences = _SENTENCE_PAT.split(response)

    # Find sentences with causal language
    for sent in sentences:
        if not _CAUSAL_PAT.search(sent):
            continue
        # Extract a clean fragment: strip leading filler words
        fragment = re.sub(
            r"^(because|since|due to|based on|as a result of|given that|"
            r"in light of|owing to)\s+",
            "",
            sent.strip(),
            flags=re.IGNORECASE,
        ).strip(" .,;:")
        # Keep only the first clause (before next subordinate connector)
        fragment = re.split(r",\s*(which|and|or|but)\b", fragment, maxsplit=1)[0].strip()
        if 5 < len(fragment) <= _FACTOR_MAX_LEN:
            factors.append(_capitalise(fragment))
        if len(factors) >= _MAX_FACTORS:
            break

    # Pad with agent-domain heuristics
    for key, domain_factors in _AGENT_DOMAIN_FACTORS.items():
        if key in agent.lower():
            for df in domain_factors:
                if len(factors) >= _MAX_FACTORS:
                    break
                cap = _capitalise(df)
                if cap.lower() not in {f.lower() for f in factors}:
                    factors.append(cap)
            break

    # Always include action as context if still short
    if len(factors) < 2:
        action_fragment = _clean_action(agent)
        if action_fragment:
            factors.insert(0, action_fragment)

    return _deduplicate(factors)[:_MAX_FACTORS]


def _clean_action(agent: str) -> str:
    return agent.replace("-", " ").replace("_", " ").strip()


def _capitalise(s: str) -> str:
    return s[:1].upper() + s[1:] if s else s


def _deduplicate(lst: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in lst:
        lower = item.lower()
        if lower not in seen:
            seen.add(lower)
            out.append(item)
    return out


# ── Reason extraction ─────────────────────────────────────────────────────────

def _extract_reason(response: str, agent: str, action: str) -> str:
    """Derive a concise, safe reason from the response.

    Rules:
    - Take the first 1-2 sentences that contain causal language, OR
    - Fall back to the first 2 sentences of the response.
    - Never exceed _REASON_MAX_LEN characters.
    - Strip any lines that look like system/internal markers.
    """
    # Remove potential internal markers
    clean = re.sub(r"<[^>]{1,80}>|```[\s\S]{0,200}?```", " ", response).strip()
    sentences = _SENTENCE_PAT.split(clean)

    # Prefer causal sentences
    causal = [s.strip() for s in sentences if _CAUSAL_PAT.search(s)]
    if causal:
        reason = " ".join(causal[:2])
    else:
        reason = " ".join(s.strip() for s in sentences[:2])

    # Hard cap
    reason = reason[:_REASON_MAX_LEN]
    if len(reason) < 20:
        # Not enough text — generate a generic contextual reason
        reason = (
            f"Decision made by {agent} agent for action '{action}' "
            "based on available context and configured objectives."
        )
    return reason.strip()


# ── Alternatives extraction ───────────────────────────────────────────────────

def _extract_alternatives(response: str) -> list[str]:
    """Extract alternative options the agent mentioned in its response."""
    alts: list[str] = []
    sentences = _SENTENCE_PAT.split(response)
    for sent in sentences:
        if not _ALT_PAT.search(sent):
            continue
        fragment = sent.strip()[:_ALT_MAX_LEN].strip(" .,;:")
        if len(fragment) > 10:
            alts.append(_capitalise(fragment))
        if len(alts) >= _MAX_ALTERNATIVES:
            break
    return alts


# ── Core engine ───────────────────────────────────────────────────────────────

class ExplainabilityEngine:
    """Main XAI engine — produces structured, safe explanations for AI decisions.

    Thread-safe.  All public methods are synchronous but safe to call from
    asyncio.run_in_threadpool().
    """

    def __init__(self, cache_size: int = _CACHE_SIZE) -> None:
        self._lock = threading.RLock()
        self._cache: deque[dict[str, Any]] = deque(maxlen=cache_size)
        self._index: dict[str, dict[str, Any]] = {}

    # ── Public API ─────────────────────────────────────────────────────────────

    def explain(self, ctx: ExplainContext) -> Explanation:
        """Produce a structured explanation for a single AI decision.

        Steps:
        1. Extract reason, key_factors, alternatives, confidence from response.
        2. Build Explanation object (no raw CoT exposed).
        3. Store in in-process cache.
        4. Persist to AuditEngine.
        5. Return Explanation.
        """
        exp = Explanation(
            agent=ctx.agent,
            action=ctx.action,
            model=ctx.model,
            user_id=ctx.user_id,
        )
        try:
            exp.reason = _extract_reason(ctx.response, ctx.agent, ctx.action)
            exp.key_factors = _extract_key_factors(ctx.agent, ctx.message, ctx.response)
            exp.alternatives = _extract_alternatives(ctx.response)
            exp.confidence = _score_confidence(ctx.response)
            exp.confidence_label = _confidence_label(exp.confidence)
        except Exception as exc:
            exp.error = str(exc)
            exp.reason = (
                f"Explanation could not be fully extracted ({exc}). "
                "Decision was processed by the agent."
            )

        self._store(exp)
        self._audit(exp, ctx)
        return exp

    def get(self, explain_id: str) -> dict[str, Any] | None:
        """Return a previously generated explanation by its ID, or None."""
        with self._lock:
            return self._index.get(explain_id)

    def recent(self, *, limit: int = 50) -> list[dict[str, Any]]:
        """Return the most recent explanations (newest first)."""
        with self._lock:
            items = list(self._cache)
        return items[:limit]

    def recent_for_agent(self, agent: str, *, limit: int = 20) -> list[dict[str, Any]]:
        """Return recent explanations filtered to a specific agent."""
        with self._lock:
            items = [e for e in self._cache if e.get("agent") == agent]
        return items[:limit]

    # ── Internal ──────────────────────────────────────────────────────────────

    def _store(self, exp: Explanation) -> None:
        d = exp.to_dict()
        with self._lock:
            self._cache.appendleft(d)
            self._index[exp.explain_id] = d

    def _audit(self, exp: Explanation, ctx: ExplainContext) -> None:
        try:
            import sys as _sys
            from pathlib import Path as _Path
            _rdir = _Path(__file__).resolve().parent.parent
            if str(_rdir) not in _sys.path:
                _sys.path.insert(0, str(_rdir))
            from core.audit_engine import get_audit_engine  # type: ignore
            get_audit_engine().record(
                actor=ctx.agent,
                action="xai_explain",
                input_data={
                    "agent": ctx.agent,
                    "action": ctx.action,
                    "model": ctx.model,
                    "explain_id": exp.explain_id,
                    "message_preview": ctx.message[:120],
                },
                output_data={
                    "reason": exp.reason[:200],
                    "key_factors": exp.key_factors,
                    "confidence": exp.confidence,
                    "confidence_label": exp.confidence_label,
                    "alternatives_count": len(exp.alternatives),
                },
                risk_score=0.10,
                meta={
                    "explain_id": exp.explain_id,
                    "xai_module": "explainability_layer",
                    "safe": True,
                },
            )
        except Exception:
            pass


# ── Singleton ──────────────────────────────────────────────────────────────────

_instance: ExplainabilityEngine | None = None
_instance_lock = threading.Lock()


def get_explain_engine() -> ExplainabilityEngine:
    """Return the process-wide ExplainabilityEngine singleton."""
    global _instance
    with _instance_lock:
        if _instance is None:
            _instance = ExplainabilityEngine()
    return _instance
