"""Memory Router — unified memory interface for agents and orchestrator.

Agents and the orchestrator MUST NOT write to memory stores directly.
All memory I/O goes through this module so that:

- Important signals are routed to the right store
- Short-lived data stays in the short-term cache
- Lasting knowledge is promoted to the long-term vector store
- Learning outcomes are forwarded to the strategy store
- No duplicate or low-quality data pollutes long-term memory

Memory taxonomy
---------------
- **episodic**    — events / task runs (what happened, when, outcome)
- **semantic**    — factual knowledge / best practices (how things work)
- **procedural**  — step-by-step skills (how to do something)

Routing rules (default)
-----------------------
+---------------------+------------------+---------------------------+
| memory_type         | TTL cache        | vector store              |
+=====================+==================+===========================+
| episodic            | 10 min           | importance ≥ 0.4          |
| semantic            | 30 min           | always                    |
| procedural          | 60 min           | always                    |
| outcome (internal)  | 5 min            | never (goes to strategy)  |
+---------------------+------------------+---------------------------+

Usage::

    from memory.memory_router import get_memory_router

    router = get_memory_router()
    router.store(
        "email_tip_001",
        "Subject lines under 50 chars have 22% higher open rates",
        memory_type="semantic",
        source="email_ninja",
        importance=0.8,
    )
    results = router.retrieve("email marketing", memory_type="semantic")
    router.record_outcome(
        action="email_ninja",
        success=True,
        context="write sales email",
        result={"opens": 5},
    )
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any

from memory.vector_store import VectorStore, get_vector_store
from memory.short_term_cache import ShortTermCache, get_short_term_cache
from memory.strategy_store import StrategyStore, get_strategy_store

logger = logging.getLogger("memory_router")

_LOCK = threading.RLock()

# TTL policy: memory_type → seconds
_TTL_POLICY: dict[str, float] = {
    "episodic":   600.0,   # 10 minutes
    "semantic":   1800.0,  # 30 minutes
    "procedural": 3600.0,  # 60 minutes
    "outcome":    300.0,   # 5 minutes (internal, not persisted long-term)
    "default":    300.0,
}

# Minimum importance for vector-store promotion
_IMPORTANCE_THRESHOLD: dict[str, float] = {
    "episodic":   0.4,
    "semantic":   0.0,
    "procedural": 0.0,
    "default":    0.5,
}


def _ts() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


class MemoryRouter:
    """Central memory dispatcher.  Agents use this — never the stores directly."""

    def __init__(
        self,
        *,
        vector_store: VectorStore | None = None,
        cache: ShortTermCache | None = None,
        strategy_store: StrategyStore | None = None,
    ) -> None:
        self._vs = vector_store or get_vector_store()
        self._cache = cache or get_short_term_cache()
        self._ss = strategy_store or get_strategy_store()
        self._stats: dict[str, int] = {
            "cache_writes": 0,
            "vector_writes": 0,
            "strategy_writes": 0,
            "cache_reads": 0,
            "vector_reads": 0,
        }
        logger.info("MemoryRouter initialised")

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def store(
        self,
        key: str,
        text: str,
        *,
        memory_type: str = "semantic",
        source: str = "",
        importance: float = 0.5,
        agent: str = "",
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Route *text* to appropriate memory stores.

        Args:
            key:         Unique entry identifier.
            text:        The content to store.
            memory_type: One of ``"episodic"``, ``"semantic"``, ``"procedural"``.
            source:      Free-text label for the originating agent/module.
            importance:  0–1; controls promotion to vector store and eviction order.
            agent:       Agent name that produced this memory.
            extra:       Additional metadata dict.

        Returns:
            A routing summary with ``cache_key``, ``vector_stored``, and ``ts``.
        """
        mt = memory_type if memory_type in _TTL_POLICY else "default"
        ttl = _TTL_POLICY[mt]
        threshold = _IMPORTANCE_THRESHOLD.get(mt, _IMPORTANCE_THRESHOLD["default"])

        metadata: dict[str, Any] = {
            "memory_type": mt,
            "source": source,
            "agent": agent,
            **(extra or {}),
        }

        with _LOCK:
            # Always write to short-term cache
            self._cache.set(key, {"text": text, "metadata": metadata}, ttl=ttl)
            self._stats["cache_writes"] += 1

            # Promote to vector store based on type + importance
            vector_stored = False
            if mt != "outcome" and float(importance) >= threshold:
                self._vs.store(key, text, metadata=metadata, importance=importance)
                self._stats["vector_writes"] += 1
                vector_stored = True

        return {
            "cache_key": key,
            "vector_stored": vector_stored,
            "memory_type": mt,
            "ts": _ts(),
        }

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def retrieve(
        self,
        query: str,
        *,
        memory_type: str | None = None,
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        """Retrieve relevant memories for *query*.

        Searches both the short-term cache and long-term vector store,
        merges results (deduplicating by key), and sorts by relevance.

        Args:
            query:       Free-text search query.
            memory_type: Filter to ``"episodic"``, ``"semantic"``, or ``"procedural"``.
            top_k:       Maximum number of results.

        Returns:
            List of memory dicts with ``key``, ``text``, ``metadata``, and ``_score``.
        """
        with _LOCK:
            seen: set[str] = set()
            results: list[dict[str, Any]] = []

            # 1. Short-term cache: scan live entries by keyword
            query_tokens = set(query.lower().split())
            for k, entry in self._cache.snapshot().items():
                if not isinstance(entry, dict):
                    continue
                if memory_type:
                    mt = entry.get("metadata", {}).get("memory_type")
                    if mt and mt != memory_type:
                        continue
                text = (entry.get("text") or "").lower()
                score = sum(1.0 for t in query_tokens if len(t) > 2 and t in text) / max(
                    len(query_tokens), 1
                )
                if score > 0:
                    results.append({
                        "key": k,
                        "text": entry.get("text", ""),
                        "metadata": entry.get("metadata", {}),
                        "_score": round(score * 0.5, 4),  # cache scores capped at 0.5
                        "_source": "cache",
                    })
                    seen.add(k)
            self._stats["cache_reads"] += 1

            # 2. Long-term vector store
            vs_results = self._vs.search(query, top_k=top_k, memory_type=memory_type)
            for r in vs_results:
                k = r.get("key", "")
                if k and k not in seen:
                    results.append({**r, "_source": "vector"})
                    seen.add(k)
            self._stats["vector_reads"] += 1

        sorted_results = sorted(
            results, key=lambda x: float(x.get("_score", 0.0)), reverse=True
        )
        return sorted_results[:top_k]

    def get(self, key: str) -> dict[str, Any] | None:
        """Retrieve a specific entry by exact key.

        Checks short-term cache first, then vector store.
        """
        with _LOCK:
            cached = self._cache.get(key)
            if cached is not None:
                return {"key": key, **cached, "_source": "cache"}
            vs_entry = self._vs.retrieve(key)
            if vs_entry:
                return {**vs_entry, "_source": "vector"}
            return None

    # ------------------------------------------------------------------
    # Outcome recording (forwards to strategy store + learning)
    # ------------------------------------------------------------------

    def record_outcome(
        self,
        *,
        action: str,
        success: bool,
        context: str = "",
        result: dict[str, Any] | None = None,
        goal_type: str = "general",
    ) -> dict[str, Any]:
        """Record a task outcome and route to strategy store.

        Also writes a short-lived episodic entry to the cache and, if the
        outcome score is high enough, promotes it to the vector store.

        Args:
            action:     Agent / action name.
            success:    Whether the action succeeded.
            context:    Task description.
            result:     Arbitrary result payload.
            goal_type:  High-level goal category (for strategy store).

        Returns:
            A dict with ``strategy_recorded`` and ``memory_stored``.
        """
        outcome_score = 1.0 if success else 0.0
        result = result or {}
        summary = f"[{action}] {'✓' if success else '✗'} {context[:120]}"

        with _LOCK:
            # Strategy store: track which agent + config won
            self._ss.record(
                goal_type=goal_type,
                agent=action,
                config=result,
                outcome_score=outcome_score,
            )
            self._stats["strategy_writes"] += 1

            # Cache: transient outcome signal
            cache_key = f"outcome:{action}:{int(time.monotonic() * 1000)}"
            self._cache.set(
                cache_key,
                {"text": summary, "metadata": {"memory_type": "outcome", "action": action}},
                ttl=_TTL_POLICY["outcome"],
            )
            self._stats["cache_writes"] += 1

            # Promote successes to long-term episodic memory
            ep_key = f"ep:{action}:{abs(hash(context)) % 100_000}"
            promoted = False
            if success:
                self._vs.store(
                    ep_key,
                    summary,
                    metadata={
                        "memory_type": "episodic",
                        "action": action,
                        "goal_type": goal_type,
                    },
                    importance=0.6,
                )
                self._stats["vector_writes"] += 1
                promoted = True

        return {
            "strategy_recorded": True,
            "memory_stored": promoted,
            "cache_key": cache_key,
            "ts": _ts(),
        }

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def stats(self) -> dict[str, Any]:
        """Return I/O statistics."""
        with _LOCK:
            return {
                **self._stats,
                "cache_size": self._cache.size(),
                "vector_count": self._vs.count(),
                "ts": _ts(),
            }

    def health(self) -> dict[str, Any]:
        """Return a brief health summary suitable for the dashboard."""
        with _LOCK:
            return {
                "status": "ok",
                "cache_live_entries": self._cache.size(),
                "vector_entries": {
                    "total": self._vs.count(),
                    "episodic": self._vs.count(memory_type="episodic"),
                    "semantic": self._vs.count(memory_type="semantic"),
                    "procedural": self._vs.count(memory_type="procedural"),
                },
                "ts": _ts(),
            }


# ── Singleton ─────────────────────────────────────────────────────────────────

_instance: MemoryRouter | None = None
_instance_lock = threading.Lock()


def get_memory_router() -> MemoryRouter:
    """Return the process-wide MemoryRouter singleton."""
    global _instance
    with _instance_lock:
        if _instance is None:
            _instance = MemoryRouter()
    return _instance
