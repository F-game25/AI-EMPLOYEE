"""Unified intent + routing seam — system coherence.

One classification service so the chat, tasks, companion and money entrypoints
classify the same sentence identically, instead of three independent classifiers
diverging:
  * core.orchestrator.TaskOrchestrator.classify_intent  — business-domain label
  * companion.intent_classifier.IntentClassifier        — conversation mode
  * engine.api.process_input                            — task_type + entities

Candidate agents come from the live agent registry
(``config/agent_capabilities.json``) by token-overlap scoring — no hardcoded
intent->agent table. Each sub-classifier is wrapped so a failure degrades that
one field rather than raising; ``classify`` never raises.
"""
from __future__ import annotations

import json
import logging
import threading
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("core.intent_service")

_CAPS_PATH = Path(__file__).resolve().parent.parent / "config" / "agent_capabilities.json"

# Tokens that carry no routing signal — dropped before scoring so "do my taxes"
# scores on "taxes", not "do"/"my".
_STOPWORDS = frozenset({
    "the", "a", "an", "to", "for", "of", "and", "or", "in", "on", "is", "it",
    "my", "me", "you", "we", "do", "can", "with", "this", "that", "what", "how",
    "please", "want", "need", "get", "got", "are", "was", "your", "our",
})

_caps_cache: Optional[dict[str, Any]] = None
_caps_lock = threading.Lock()


def _agent_caps() -> dict[str, Any]:
    """Load + cache the agent registry (the ``agents`` map). Empty on failure."""
    global _caps_cache
    with _caps_lock:
        if _caps_cache is None:
            try:
                data = json.loads(_CAPS_PATH.read_text())
                _caps_cache = data.get("agents", data) if isinstance(data, dict) else {}
            except Exception as exc:  # noqa: BLE001
                logger.warning("agent_capabilities load failed: %s", exc)
                _caps_cache = {}
    return _caps_cache


def _tokens(text: str) -> set[str]:
    return {w for w in text.lower().split() if len(w) > 2 and w not in _STOPWORDS}


def score_agents(text: str, *, top_k: int = 3) -> list[tuple[str, int]]:
    """Registry-backed agent ranking by token overlap against each agent's
    description/category/skills/commands/specialties. Single source of truth for
    keyword routing (``AgentController._keyword_route_agent`` should delegate
    here). Returns ``[(agent_id, score), ...]`` best-first, ``score > 0`` only.
    """
    caps = _agent_caps()
    toks = _tokens(text)
    if not caps or not toks:
        return []
    scored: list[tuple[str, int]] = []
    for agent_id, meta in caps.items():
        if not isinstance(meta, dict):
            continue
        corpus = " ".join((
            meta.get("description", ""),
            meta.get("category", ""),
            " ".join(meta.get("skills", []) or []),
            " ".join(meta.get("commands", []) or []),
            " ".join(meta.get("specialties", []) or []),
        )).lower()
        score = sum(1 for t in toks if t in corpus)
        if score > 0:
            scored.append((agent_id, score))
    scored.sort(key=lambda kv: kv[1], reverse=True)
    return scored[:top_k]


@dataclass
class IntentResult:
    """Unified classification across all three axes. Consumers read the slice
    they need; the whole object is logged for traceability."""

    text: str
    business_intent: str = "ops"             # INTENT_CATEGORIES (lead_gen/content/...)
    conversation_mode: str = "conversation"  # companion MODE_* (execution/monitoring/...)
    task_type: str = "general"
    entities: list[str] = field(default_factory=list)
    is_command: bool = False
    confidence: float = 0.0
    reason: str = ""                         # companion classifier rationale (traceability)
    candidate_agents: list[str] = field(default_factory=list)
    sources: dict[str, bool] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_companion_intent(self) -> dict[str, Any]:
        """Map to the dict shape ``companion.ConversationRuntime`` consumes
        (``mode``/``task_type``/``confidence``/``is_command``/``reason``), so the
        companion sources intent from the one seam without changing its contract.
        Adds ``business_intent``/``candidate_agents`` (inert for current consumers;
        used once broker routing goes registry-backed in C2)."""
        return {
            "mode": self.conversation_mode,
            "task_type": self.task_type,
            "confidence": self.confidence,
            "is_command": self.is_command,
            "reason": self.reason,
            "business_intent": self.business_intent,
            "candidate_agents": list(self.candidate_agents),
        }


def classify(
    text: str,
    context: Optional[dict] = None,
    *,
    business_intent: bool = True,
) -> IntentResult:
    """Compose the three classifiers + registry routing into one result.

    Never raises: each axis degrades to its default on failure. Axes 2 (companion
    conversation mode) and 3 (entity/task-type normalization) are pure heuristics.
    Axis 1 (business intent) is the only LLM call — the same one
    ``classify_decision`` already makes — so latency-sensitive callers that don't
    need a business label (the companion's conversational turns) pass
    ``business_intent=False`` to stay on the seam without paying for an extra LLM
    round-trip. The companion axis only escalates to an LLM when
    ``COMPANION_LLM_INTENT=1``.
    """
    text = (text or "").strip()
    res = IntentResult(text=text)
    if not text:
        return res
    ctx = context or {}

    # Axis 1 — business-domain intent (LLM label; reuse TaskOrchestrator).
    # Opt-out for latency-sensitive callers (companion conversation turns).
    if business_intent:
        try:
            from core.orchestrator import TaskOrchestrator  # noqa: PLC0415
            res.business_intent = TaskOrchestrator().classify_intent(text)
            res.sources["business_intent"] = True
        except Exception as exc:  # noqa: BLE001
            logger.debug("business_intent classify failed (non-fatal): %s", exc)

    # Axis 2 — conversation mode (heuristic-first; reuse companion classifier).
    try:
        from companion.intent_classifier import get_intent_classifier  # noqa: PLC0415
        c = get_intent_classifier().classify(text, ctx)
        res.conversation_mode = c.get("mode", res.conversation_mode)
        res.task_type = c.get("task_type", res.task_type)
        res.is_command = bool(c.get("is_command", False))
        res.confidence = float(c.get("confidence", 0.0) or 0.0)
        res.reason = c.get("reason", "")
        res.sources["conversation_mode"] = True
    except Exception as exc:  # noqa: BLE001
        logger.debug("conversation_mode classify failed (non-fatal): %s", exc)

    # Axis 3 — normalization: entities + task_type fallback (reuse engine.api).
    try:
        from engine.api import process_input  # noqa: PLC0415
        norm = process_input(text)
        res.entities = norm.get("entities") or res.entities
        if res.task_type == "general":
            res.task_type = norm.get("task_type", res.task_type)
        res.sources["normalization"] = True
    except Exception as exc:  # noqa: BLE001
        logger.debug("normalization failed (non-fatal): %s", exc)

    # Registry-backed candidate agents (no hardcoded intent->agent table).
    try:
        res.candidate_agents = [aid for aid, _ in score_agents(text)]
        res.sources["candidate_agents"] = bool(res.candidate_agents)
    except Exception as exc:  # noqa: BLE001
        logger.debug("agent scoring failed (non-fatal): %s", exc)

    return res


class IntentService:
    """Thin stateless facade — parity with ``get_intent_classifier()``."""

    classify = staticmethod(classify)
    score_agents = staticmethod(score_agents)


_service_singleton: Optional[IntentService] = None


def get_intent_service() -> IntentService:
    """Return the process-wide IntentService singleton."""
    global _service_singleton
    if _service_singleton is None:
        _service_singleton = IntentService()
    return _service_singleton
