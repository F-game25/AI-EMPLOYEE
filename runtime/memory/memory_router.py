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

import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Any

from memory.vector_store import VectorStore, get_vector_store
from memory.short_term_cache import ShortTermCache, get_short_term_cache
from memory.strategy_store import StrategyStore, get_strategy_store
from memory.service import MemoryService
from memory.bm25 import BM25

try:
    from neural_brain.graph.native_graph_store import NativeGraphStore
except Exception:  # pragma: no cover - import path can differ in legacy tools
    NativeGraphStore = None  # type: ignore[assignment]

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
        self._graph = NativeGraphStore() if NativeGraphStore is not None else None
        self._service = MemoryService(
            vector_store=self._vs,
            cache=self._cache,
            strategy_store=self._ss,
            graph=self._graph,
        )
        self._stats: dict[str, int] = {
            "cache_writes": 0,
            "vector_writes": 0,
            "strategy_writes": 0,
            "graph_writes": 0,
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
        with _LOCK:
            routed = self._service.remember(
                text,
                key=key,
                memory_type=memory_type,
                source=source,
                importance=importance,
                agent=agent,
                extra=extra,
            )
            self._stats["cache_writes"] += 1
            if routed.get("vector_stored"):
                self._stats["vector_writes"] += 1
            if routed.get("graph_stored"):
                self._stats["graph_writes"] += 1
            return routed

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
        # Clamp first: a negative/bogus top_k must not flow into the service or the
        # gate (apply_trust_gate treats a negative cap as uncapped → bypasses the cap).
        try:
            top_k = max(0, int(top_k))
        except (TypeError, ValueError):
            top_k = 5
        with _LOCK:
            self._stats["cache_reads"] += 1
            self._stats["vector_reads"] += 1
            # Over-fetch so the trust gate can drop untrusted rows without starving top_k.
            results = self._service.retrieve(query, memory_type=memory_type, top_k=top_k * 2)
        # C4 provenance-trust gate: retrieved memories are untrusted data — drop
        # low-trust / injection-bearing entries before they reach any prompt.
        # Never fatal; on any error the gate fails closed (keeps nothing).
        try:
            from core.memory_trust import apply_trust_gate
            kept, stats = apply_trust_gate(results, limit=top_k)
            self._stats["trust_dropped"] = self._stats.get("trust_dropped", 0) + \
                int(stats.get("dropped_low_trust", 0)) + int(stats.get("dropped_injection", 0))
            return kept
        except Exception as e:  # noqa: BLE001 — fail CLOSED: never leak ungated memory
            logger.error("retrieve: trust gate unavailable, dropping all memories (%s)", e)
            return []

    async def retrieve_qce(self, query: str, tenant_id: str = '', **kwargs) -> list:
        """QCE-powered retrieval via SearchOrchestrator. Falls back to retrieve() on error."""
        try:
            from core.quantum.search.orchestrator import SearchOrchestrator
            from core.quantum.search.schema import SearchRequest
            orch = SearchOrchestrator()
            req = SearchRequest(query=query, bangs=['memory'], tenant_id=tenant_id)
            results = await orch.search(req)
            mapped = [{'content': r.content, 'text': r.content, 'score': r.amplitude,
                       'source': r.engine, 'id': r.id} for r in results[:10]]
            # Same provenance-trust gate as retrieve(): QCE memory results are untrusted
            # too and must not reach a prompt ungated. Fail-closed on any error.
            try:
                from core.memory_trust import apply_trust_gate
                kept, _stats = apply_trust_gate(mapped, limit=10)
                return kept
            except Exception:  # noqa: BLE001
                return []
        except Exception:
            return []

    def get(self, key: str) -> dict[str, Any] | None:
        """Retrieve a specific entry by exact key.

        Checks short-term cache first, then vector store.
        """
        with _LOCK:
            return self._service.get(key)

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
        with _LOCK:
            routed = self._service.record_outcome(
                action=action,
                success=success,
                context=context,
                result=result,
                goal_type=goal_type,
            )
            self._stats["strategy_writes"] += 1
            self._stats["cache_writes"] += 1
            if routed.get("memory_stored"):
                self._stats["cache_writes"] += 1
                self._stats["vector_writes"] += 1
            return routed

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def stats(self) -> dict[str, Any]:
        """Return I/O statistics."""
        with _LOCK:
            service_stats = self._service.stats()
            return {
                **self._stats,
                "cache_size": self._cache.size(),
                "vector_count": self._vs.count(),
                "canonical_count": service_stats.get("canonical_count", 0),
                "ts": _ts(),
            }

    def health(self) -> dict[str, Any]:
        """Return a brief health summary suitable for the dashboard."""
        with _LOCK:
            service_stats = self._service.stats()
            return {
                "status": "ok",
                "canonical_entries": service_stats.get("canonical_count", 0),
                "cache_live_entries": self._cache.size(),
                "vector_entries": {
                    "total": self._vs.count(),
                    "episodic": self._vs.count(memory_type="episodic"),
                    "semantic": self._vs.count(memory_type="semantic"),
                    "procedural": self._vs.count(memory_type="procedural"),
                },
                "graph": self._graph.stats() if self._graph is not None else {
                    "available": False,
                    "backend": "native_sqlite_graph",
                    "error": "native graph store unavailable",
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


# ── Hybrid search (BM25 + vector) ─────────────────────────────────────────────

_KS_PATH = Path(os.environ.get("STATE_DIR", Path.home() / ".ai-employee" / "state")) / "knowledge_store.json"


def _load_knowledge_entries() -> list[dict]:
    """Load entries from knowledge_store.json, flattening all topic buckets."""
    try:
        raw = json.loads(_KS_PATH.read_text())
    except Exception:
        return []
    entries: list[dict] = []
    for bucket in raw.get("topics", {}).values():
        for topic_entry in bucket:
            for finding in topic_entry.get("findings", []):
                content = finding.get("summary") or finding.get("content") or ""
                if content:
                    entries.append({
                        "source": finding.get("source") or finding.get("url") or "knowledge_store",
                        "content": content,
                        "url": finding.get("url", ""),
                        "title": finding.get("title", ""),
                    })
    for entry in raw.get("entries", []):
        content = entry.get("content") or entry.get("text") or ""
        if content:
            entries.append({
                "source": entry.get("source", "knowledge_store"),
                "content": content,
                "url": entry.get("url", ""),
                "title": entry.get("title", ""),
            })
    return entries


def _normalize(scores: list[float]) -> list[float]:
    lo, hi = min(scores, default=0.0), max(scores, default=0.0)
    span = hi - lo
    if span == 0:
        return [0.0] * len(scores)
    return [(s - lo) / span for s in scores]


def _compress_passage(query: str, passage: str, max_sentences: int = 3) -> str:
    """Score sentences by keyword overlap with query, keep top N in original order."""
    import re
    query_words = set(query.lower().split())
    sentences = re.split(r'(?<=[.!?])\s+', passage)
    scored = [
        (sum(1 for w in s.lower().split() if w in query_words), i, s)
        for i, s in enumerate(sentences)
    ]
    scored.sort(reverse=True)
    kept = sorted(scored[:max_sentences], key=lambda x: x[1])
    return ' '.join(s for _, _, s in kept) or passage[:500]


def rag_retrieve(
    query: str,
    top_k: int = 5,
    alpha: float = 0.5,
    rerank: bool = True,
    compress: bool = True,
    cite: bool = True,
    tenant_id: str = "default",
) -> dict:
    """Full RAG pipeline: hybrid search → rerank → compress → cite.

    Returns:
        {
            query: str,
            results: [{source, content, score, rank, citations: [{text, source}]}],
            context: str,    # compressed, citation-annotated context ready for LLM
            sources: [str],  # unique source list
        }
    """
    # Step 1: Hybrid search — fetch 2× candidates for reranking headroom
    candidates = hybrid_search(query, top_k=top_k * 2, alpha=alpha)

    # Step 2: Rerank with cross-encoder when requested
    if rerank and candidates:
        try:
            from sentence_transformers import CrossEncoder  # type: ignore
            _ce = CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')
            pairs = [(query, r['content']) for r in candidates]
            ce_scores = _ce.predict(pairs)
            for r, s in zip(candidates, ce_scores):
                r['_ce_score'] = float(s)
            candidates.sort(key=lambda r: r.get('_ce_score', 0.0), reverse=True)
        except Exception:
            pass  # graceful degradation: keep hybrid ranking

    top_results = candidates[:top_k]

    # Step 3 + 4: Compress and cite
    context_parts: list[str] = []
    sources: list[dict] = []
    out_results: list[dict] = []

    for i, r in enumerate(top_results):
        src_id = f"[{i + 1}]"
        raw_content = r.get('content') or ''
        compressed = _compress_passage(query, raw_content) if compress else raw_content[:500]

        citation = {"text": compressed, "source": r.get('source', '')}
        entry = {
            "source": r.get('source', ''),
            "content": raw_content,
            "compressed_content": compressed,
            "score": r.get('score', 0.0),
            "rank": i + 1,
            "citations": [citation] if cite else [],
        }
        out_results.append(entry)

        if cite:
            context_parts.append(f"{compressed} {src_id}")
            sources.append({"id": src_id, "source": r.get('source', ''), "score": r.get('score', 0.0)})

    context = "\n\n".join(context_parts)
    if cite and sources:
        context += "\n\nSources:\n" + "\n".join(f"{s['id']} {s['source']}" for s in sources)

    return {
        "query": query,
        "results": out_results,
        "context": context,
        "sources": [s['source'] for s in sources] if cite else list({r.get('source', '') for r in top_results}),
    }


def hybrid_search(
    query: str,
    top_k: int = 5,
    alpha: float = 0.5,
) -> list[dict]:
    """Hybrid BM25 + vector search over the knowledge store.

    Args:
        query: Search query.
        top_k: Number of results.
        alpha: Weight for vector score (1-alpha = BM25 weight).

    Returns:
        List of dicts: {source, content, score, bm25_score, vector_score, rank}.
    """
    entries = _load_knowledge_entries()
    if not entries:
        # Fallback: pure vector search via memory router
        router = get_memory_router()
        raw = router.retrieve(query, top_k=top_k)
        return [
            {
                "source": r.get("metadata", {}).get("source") or r.get("_source") or "",
                "content": r.get("text") or "",
                "score": r.get("_score", 0.0),
                "bm25_score": 0.0,
                "vector_score": r.get("_score", 0.0),
                "rank": i + 1,
            }
            for i, r in enumerate(raw)
        ]

    corpus = [e["content"] for e in entries]
    n = len(corpus)

    # BM25 scores
    bm25 = BM25(corpus)
    raw_bm25 = bm25.scores(query)
    norm_bm25 = _normalize(raw_bm25)

    # Vector scores
    norm_vec = [0.0] * n
    if alpha > 0.0:
        try:
            from core.embeddings import get_embeddings_manager
            mgr = get_embeddings_manager()
            q_emb = mgr.embed_text(query)
            raw_vec: list[float] = []
            for e in entries:
                emb = e.get("embedding")
                if emb:
                    raw_vec.append(mgr.similarity(q_emb, emb))
                else:
                    c_emb = mgr.embed_text(e["content"])
                    raw_vec.append(mgr.similarity(q_emb, c_emb))
            norm_vec = _normalize(raw_vec)
        except Exception:
            logger.debug("hybrid_search: vector scoring unavailable, using BM25 only")
            alpha = 0.0

    # Combine
    combined = [
        alpha * norm_vec[i] + (1 - alpha) * norm_bm25[i]
        for i in range(n)
    ]

    # Rank top_k
    ranked_idx = sorted(range(n), key=lambda i: combined[i], reverse=True)[:top_k]
    return [
        {
            "source": entries[i]["source"],
            "content": entries[i]["content"],
            "score": round(combined[i], 6),
            "bm25_score": round(norm_bm25[i], 6),
            "vector_score": round(norm_vec[i], 6),
            "rank": rank + 1,
        }
        for rank, i in enumerate(ranked_idx)
    ]
