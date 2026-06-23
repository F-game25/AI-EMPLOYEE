"""Unified memory service.

This is the single Python-facing memory facade.  It writes the canonical memory
record first, then maintains compatibility with the existing short-term cache,
vector store, strategy store, and native graph.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any

from memory.schema import MemoryRecord, utc_now
from memory.short_term_cache import ShortTermCache, get_short_term_cache
from memory.strategy_store import StrategyStore, get_strategy_store
from memory.unified_store import UnifiedMemoryStore, get_unified_memory_store
from memory.vector_store import VectorStore, get_vector_store


logger = logging.getLogger("memory_service")

_LOCK = threading.RLock()
_TTL_POLICY = {
    "episodic": 600.0,
    "semantic": 1800.0,
    "procedural": 3600.0,
    "outcome": 300.0,
    "session": 1800.0,
    "default": 300.0,
}
_PROMOTION_THRESHOLD = {
    "episodic": 0.4,
    "semantic": 0.0,
    "procedural": 0.0,
    "outcome": 1.1,
    "default": 0.5,
}


def _default_tenant() -> str:
    # Prefer the request-scoped tenant set by TenantMiddleware (a ContextVar) so concurrent
    # multi-tenant requests don't all collapse onto one process-wide env value. Fall back to
    # env, then "default" for non-request contexts (CLI, background jobs, tests).
    try:
        from core.tenancy import get_tenant_manager
        ctx = get_tenant_manager().get_current_tenant()
        if ctx is not None and getattr(ctx, "tenant_id", None):
            return ctx.tenant_id
    except Exception:
        pass
    return os.environ.get("TENANT_ID") or os.environ.get("AI_EMPLOYEE_TENANT_ID") or "default"


def _ttl_for(memory_type: str) -> float:
    return _TTL_POLICY.get(memory_type, _TTL_POLICY["default"])


def _threshold_for(memory_type: str) -> float:
    return _PROMOTION_THRESHOLD.get(memory_type, _PROMOTION_THRESHOLD["default"])


class MemoryService:
    """Canonical memory service with compatibility fan-out."""

    def __init__(
        self,
        *,
        store: UnifiedMemoryStore | None = None,
        vector_store: VectorStore | None = None,
        cache: ShortTermCache | None = None,
        strategy_store: StrategyStore | None = None,
        graph: Any = None,
    ) -> None:
        self._store = store or get_unified_memory_store()
        self._vs = vector_store or get_vector_store()
        self._cache = cache or get_short_term_cache()
        self._ss = strategy_store or get_strategy_store()
        self._graph = graph

    def remember(
        self,
        text: str,
        *,
        key: str | None = None,
        memory_type: str = "semantic",
        source: str = "",
        importance: float = 0.5,
        agent: str = "",
        tenant_id: str | None = None,
        user_id: str | None = None,
        scope: str | None = None,
        summary: str | None = None,
        topic: str | None = None,
        tags: list[str] | None = None,
        project_id: str | None = None,
        session_id: str | None = None,
        task_id: str | None = None,
        confidence: float = 0.5,
        verified: bool = False,
        sensitive: bool = False,
        visibility: str = "private",
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        record = MemoryRecord.create(
            text,
            id=key,
            tenant_id=tenant_id or _default_tenant(),
            user_id=user_id,
            scope=scope,
            memory_type=memory_type,
            source=source,
            importance=importance,
            agent=agent or None,
            summary=summary,
            topic=topic,
            tags=tags or (extra or {}).get("tags"),
            project_id=project_id or (extra or {}).get("project_id"),
            session_id=session_id or (extra or {}).get("session_id"),
            task_id=task_id or (extra or {}).get("task_id"),
            confidence=confidence,
            verified=verified,
            sensitive=sensitive,
            visibility=visibility,
            metadata=extra or {},
        )
        return self.store(record)

    def store(self, record: MemoryRecord | dict[str, Any]) -> dict[str, Any]:
        with _LOCK:
            current = record if isinstance(record, MemoryRecord) else MemoryRecord.from_dict(record)
            stored = self._store.upsert(current)

            # Canonical commit (above) is the source of truth. Cache/vector/graph are
            # best-effort fan-out: isolate their failures so a downstream backend hiccup
            # can't fail the whole write after the canonical record is already persisted.
            cache_payload = {"text": stored.text, "metadata": stored.vector_metadata(), "record": stored.to_dict()}
            try:
                self._cache.set(stored.id, cache_payload, ttl=_ttl_for(stored.memory_type))
            except Exception as exc:
                logger.warning("memory cache write skipped: %s", exc)

            vector_stored = False
            if stored.memory_type != "outcome" and stored.importance >= _threshold_for(stored.memory_type):
                try:
                    self._vs.store(stored.id, stored.text, metadata=stored.vector_metadata(), importance=stored.importance)
                    vector_stored = True
                except Exception as exc:
                    logger.warning("memory vector write skipped: %s", exc)

            graph_stored = False
            if vector_stored and self._graph is not None:
                try:
                    self._graph.upsert_node(
                        stored.id,
                        stored.summary or stored.topic or stored.id,
                        type=stored.memory_type,
                        group="memory",
                        source=stored.source or "memory_service",
                        confidence=stored.importance,
                        metadata={**stored.vector_metadata(), "content": stored.text},
                    )
                    graph_stored = True
                except Exception as exc:
                    logger.debug("native graph memory write skipped: %s", exc)

        return {
            "id": stored.id,
            "cache_key": stored.id,
            "vector_stored": vector_stored,
            "graph_stored": graph_stored,
            "memory_type": stored.memory_type,
            "record": stored.to_dict(),
            "ts": utc_now(),
        }

    def retrieve(
        self,
        query: str,
        *,
        tenant_id: str | None = None,
        memory_type: str | None = None,
        scope: str | None = None,
        project_id: str | None = None,
        session_id: str | None = None,
        agent: str | None = None,
        tags: list[str] | None = None,
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        # Default retrieval to the current tenant — without this, an unscoped call returned
        # every tenant's memories (cross-tenant read). Callers wanting cross-tenant reads
        # must pass an explicit tenant_id (none of the production call sites do).
        tenant_id = tenant_id or _default_tenant()
        query_tokens = {t for t in str(query or "").lower().split() if len(t) > 2}
        seen: set[str] = set()
        # Mirror the canonical store's scope/agent/tags filters on cache + vector
        # candidates so a query scoped to one tenant/agent/scope/tag-set can't surface
        # out-of-scope rows from those secondary sources.
        wanted_tags = {str(t).lower() for t in (tags or [])}

        def _scope_ok(metadata: dict[str, Any]) -> bool:
            if scope and metadata.get("scope") != scope:
                return False
            if agent and metadata.get("agent") != agent:
                return False
            if wanted_tags and not wanted_tags.intersection(
                {str(t).lower() for t in (metadata.get("tags") or [])}
            ):
                return False
            return True
        results: list[dict[str, Any]] = []

        with _LOCK:
            for key, entry in self._cache.snapshot().items():
                if not isinstance(entry, dict):
                    continue
                metadata = entry.get("metadata", {})
                if memory_type and metadata.get("memory_type") != memory_type:
                    continue
                if tenant_id and metadata.get("tenant_id") not in ("", tenant_id):
                    continue
                if project_id and metadata.get("project_id") != project_id:
                    continue
                if session_id and metadata.get("session_id") != session_id:
                    continue
                if not _scope_ok(metadata):
                    continue
                text = str(entry.get("text") or "")
                low = text.lower()
                score = 0.0
                if query_tokens:
                    score = sum(1.0 for token in query_tokens if token in low) / max(len(query_tokens), 1)
                if score > 0:
                    results.append({
                        "key": key,
                        "id": key,
                        "text": text,
                        "metadata": metadata,
                        "_score": round(score * 0.5, 4),
                        "_source": "cache",
                        "_reason": "short-term keyword match",
                    })
                    seen.add(key)

            canonical = self._store.search(
                query=str(query or ""),
                tenant_id=tenant_id,
                memory_type=memory_type,
                scope=scope,
                project_id=project_id,
                session_id=session_id,
                agent=agent,
                tags=tags,
                limit=top_k * 2,
            )
            for record in canonical:
                if record.id in seen:
                    continue
                results.append({
                    "key": record.id,
                    "id": record.id,
                    "text": record.text,
                    "metadata": record.vector_metadata(),
                    "record": record.to_dict(),
                    "_score": self._score_record(record, query_tokens, project_id=project_id, session_id=session_id, tags=set(tags or [])),
                    "_source": "unified",
                    "_reason": "canonical memory match",
                })
                seen.add(record.id)

            for row in self._vs.search(str(query or ""), top_k=top_k, memory_type=memory_type):
                key = row.get("key") or row.get("id")
                if not key or key in seen:
                    continue
                metadata = row.get("metadata") or {}
                if tenant_id and metadata.get("tenant_id") not in ("", tenant_id):
                    continue
                if project_id and metadata.get("project_id") != project_id:
                    continue
                if session_id and metadata.get("session_id") != session_id:
                    continue
                if not _scope_ok(metadata):
                    continue
                results.append({**row, "id": key, "_source": "vector", "_reason": "vector similarity"})
                seen.add(key)

        results.sort(key=lambda item: float(item.get("_score", 0.0)), reverse=True)
        return results[:top_k]

    def get(self, memory_id: str) -> dict[str, Any] | None:
        with _LOCK:
            cached = self._cache.get(memory_id)
            if isinstance(cached, dict):
                return {"key": memory_id, "id": memory_id, **cached, "_source": "cache"}
            record = self._store.get(memory_id)
            if record is not None:
                return {
                    "key": record.id,
                    "id": record.id,
                    "text": record.text,
                    "metadata": record.vector_metadata(),
                    "record": record.to_dict(),
                    "_source": "unified",
                }
            vector = self._vs.retrieve(memory_id)
            if vector:
                return {**vector, "id": memory_id, "_source": "vector"}
            return None

    def record_outcome(
        self,
        *,
        action: str,
        success: bool,
        context: str = "",
        result: dict[str, Any] | None = None,
        goal_type: str = "general",
        tenant_id: str | None = None,
    ) -> dict[str, Any]:
        score = 1.0 if success else 0.0
        result = result or {}
        summary = f"[{action}] {'ok' if success else 'failed'} {context[:120]}"

        with _LOCK:
            self._ss.record(
                goal_type=goal_type,
                agent=action,
                config=result,
                outcome_score=score,
            )
            cache_key = f"outcome:{action}:{int(time.monotonic() * 1000)}"
            self.remember(
                summary,
                key=cache_key,
                memory_type="outcome",
                source="memory_service",
                agent=action,
                importance=0.2,
                tenant_id=tenant_id,
                extra={"action": action, "goal_type": goal_type, "result": result},
            )

            promoted = False
            ep_key = f"ep:{action}:{abs(hash(context)) % 100_000}"
            if success:
                self.remember(
                    summary,
                    key=ep_key,
                    memory_type="episodic",
                    source="memory_service",
                    agent=action,
                    importance=0.6,
                    tenant_id=tenant_id,
                    extra={"action": action, "goal_type": goal_type, "result": result},
                )
                promoted = True

        return {
            "strategy_recorded": True,
            "memory_stored": promoted,
            "cache_key": cache_key,
            "ts": utc_now(),
        }

    def apply_feedback(self, memory_id: str, reward: float) -> dict[str, Any] | None:
        record = self._store.apply_feedback(memory_id, reward)
        return record.to_dict() if record else None

    def stats(self) -> dict[str, Any]:
        return {
            "canonical_count": self._store.count(),
            "cache_size": self._cache.size(),
            "vector_count": self._vs.count(),
            "ts": utc_now(),
        }

    @staticmethod
    def _score_record(
        record: MemoryRecord,
        query_tokens: set[str],
        *,
        project_id: str | None,
        session_id: str | None,
        tags: set[str],
    ) -> float:
        text = " ".join([record.text, record.summary or "", record.topic or "", " ".join(record.tags)]).lower()
        token_score = sum(1 for token in query_tokens if token in text) / max(len(query_tokens), 1) if query_tokens else 0.0
        label_score = 0.0
        if project_id and record.project_id == project_id:
            label_score += 0.25
        if session_id and record.session_id == session_id:
            label_score += 0.25
        if tags:
            label_score += min(0.3, 0.1 * len(tags.intersection(set(record.tags))))
        return round(token_score + label_score + record.importance * 0.2 + record.confidence * 0.1, 4)


_instance: MemoryService | None = None
_instance_lock = threading.Lock()


def get_memory_service() -> MemoryService:
    global _instance
    with _instance_lock:
        if _instance is None:
            _instance = MemoryService()
    return _instance
