"""Unified vector + facts + graph memory orchestrator."""
from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import Any, Callable, Protocol

from neural_brain.memory.chroma_adapter import ChromaAdapter
from neural_brain.memory.embedding_provider import EmbeddingProvider
from neural_brain.memory.mem0_adapter import Mem0Adapter
from neural_brain.memory.memory_schemas import (
    MemoryItem,
    MemoryType,
    RecallHit,
    RecallResult,
)
from neural_brain.memory.reranker import CrossEncoderReranker

logger = logging.getLogger(__name__)


class GraphHook(Protocol):
    """Subset of BrainGraph M3 will provide."""

    def upsert_concept(
        self, label: str, *, type: str = "Concept", weight: float = 1.0
    ) -> str: ...

    def link(
        self, src_id: str, dst_id: str, *, rel: str = "RELATES_TO", strength: float = 0.5
    ) -> None: ...

    def neighborhood(
        self, seed_ids: list[str], *, depth: int = 2, limit: int = 50
    ) -> list[dict]: ...

    def attach_memory(self, memory_id: str, concept_ids: list[str]) -> None: ...


# Naive concept extractor — capitalized runs and hyphenated tokens.
_CAP_RUN = re.compile(r"\b(?:[A-Z][a-zA-Z0-9]+(?:[-_][A-Za-z0-9]+)*)(?:\s+[A-Z][a-zA-Z0-9]+)*\b")
_HYPHEN = re.compile(r"\b[a-zA-Z][a-zA-Z0-9]+(?:[-_][a-zA-Z0-9]+)+\b")


def _extract_concepts(text: str, *, cap: int = 5) -> list[str]:
    if not text:
        return []
    seen: set[str] = set()
    out: list[str] = []
    for rx in (_CAP_RUN, _HYPHEN):
        for m in rx.finditer(text):
            tok = m.group(0).strip()
            key = tok.lower()
            if key in seen or len(tok) < 3:
                continue
            seen.add(key)
            out.append(tok)
            if len(out) >= cap:
                return out
    return out


class NeuralMemoryManager:
    def __init__(
        self,
        chroma: ChromaAdapter,
        mem0: Mem0Adapter,
        embedder: EmbeddingProvider,
        graph: GraphHook | None = None,
        *,
        bridge_emit: Callable[[str, dict], None] | None = None,
        reranker: CrossEncoderReranker | None = None,
        proxy_legacy: bool = False,
        unified_store: Any = None,
    ) -> None:
        self.chroma = chroma
        self.mem0 = mem0
        self.embedder = embedder
        self.graph = graph
        self._emit = bridge_emit
        self.reranker = reranker
        self.proxy_legacy = proxy_legacy
        self._unified = unified_store if unified_store is not None else self._init_unified_store()

    @staticmethod
    def _init_unified_store() -> Any:
        try:
            from memory.unified_store import UnifiedMemoryStore
            return UnifiedMemoryStore()
        except Exception:
            return None

    # ---------------------------------------------------------------- remember

    async def remember(
        self,
        content: str,
        *,
        type: MemoryType = "semantic",
        user_id: str = "default",
        importance: float = 0.5,
        source: str = "",
        metadata: dict | None = None,
    ) -> str:
        item = MemoryItem(
            text=content,
            type=type,
            user_id=user_id,
            importance=importance,
            source=source,
            metadata=dict(metadata or {}),
        )

        # 1. Chroma — required.
        await asyncio.to_thread(self.chroma.add, [item])

        # 2. Mem0 — best effort.
        try:
            await asyncio.to_thread(
                self.mem0.add, content, user_id=user_id, metadata=metadata or {}
            )
        except Exception as e:
            logger.debug("mem0.add swallowed: %s", e)

        # 3. Canonical unified memory — best effort.
        if self._unified is not None:
            try:
                await asyncio.to_thread(self._store_unified, item)
            except Exception as e:
                logger.debug("unified memory write skipped: %s", e)

        # 4. Graph — extract simple concepts and link.
        if self.graph is not None:
            try:
                await asyncio.to_thread(self._graph_link, item, content)
            except Exception as e:
                logger.warning("graph link failed: %s", e)

        # 5. Optional legacy proxy.
        if self.proxy_legacy:
            try:
                from memory import memory_router  # type: ignore

                store = getattr(memory_router, "store", None)
                if callable(store):
                    await asyncio.to_thread(
                        store, content, type, user_id, metadata or {}
                    )
            except Exception as e:
                logger.debug("legacy memory proxy skipped: %s", e)

        # 6. Bridge event.
        self._safe_emit(
            "nb:memory_write",
            {
                "id": item.id,
                "type": type,
                "user_id": user_id,
                "preview": content[:120],
            },
        )

        return item.id

    def _store_unified(self, item: MemoryItem) -> None:
        if self._unified is None:
            return
        from memory.schema import MemoryRecord
        record = MemoryRecord.create(
            item.text,
            id=item.id,
            tenant_id=item.user_id or "default",
            user_id=item.user_id,
            memory_type=item.type,
            source=item.source or "neural_brain",
            importance=item.importance,
            agent="neural_brain",
            metadata={
                **item.metadata,
                "origin_store": "neural_memory_manager",
                "created_at_epoch": item.created_at,
            },
        )
        self._unified.upsert(record)

    def _graph_link(self, item: MemoryItem, content: str) -> None:
        if self.graph is None:
            return
        concepts = _extract_concepts(content, cap=5)
        if not concepts:
            return
        cids: list[str] = []
        for label in concepts:
            try:
                cid = self.graph.upsert_concept(label, type="Concept", weight=1.0)
                if cid:
                    cids.append(cid)
            except Exception as e:
                logger.debug("upsert_concept(%s) failed: %s", label, e)
        if cids:
            try:
                self.graph.attach_memory(item.id, cids)
            except Exception as e:
                logger.debug("attach_memory failed: %s", e)

    # ------------------------------------------------------------------ recall

    async def recall(
        self,
        query: str,
        *,
        k: int = 10,
        types: list[MemoryType] | None = None,
        user_id: str = "default",
        with_graph: bool = True,
    ) -> RecallResult:
        t0 = time.perf_counter()
        stores_queried: list[str] = []

        chroma_where: dict | None = {"user_id": user_id} if user_id else None

        chroma_task = asyncio.to_thread(
            self.chroma.query,
            query,
            n_results=k,
            types=list(types) if types else None,
            where=chroma_where,
        )
        mem0_task = asyncio.to_thread(
            self.mem0.search, query, user_id=user_id, limit=k
        )

        chroma_hits, mem0_hits = await asyncio.gather(
            chroma_task, mem0_task, return_exceptions=True
        )

        all_hits: list[RecallHit] = []
        if isinstance(chroma_hits, Exception):
            logger.warning("chroma.query failed: %s", chroma_hits)
        else:
            stores_queried.append("chroma")
            all_hits.extend(chroma_hits or [])

        if isinstance(mem0_hits, Exception):
            logger.warning("mem0.search failed: %s", mem0_hits)
        elif self.mem0.enabled:
            stores_queried.append("mem0")
            all_hits.extend(mem0_hits or [])

        if self._unified is not None:
            try:
                unified_hits = await asyncio.to_thread(
                    self._recall_unified,
                    query,
                    k=k,
                    types=types,
                    user_id=user_id,
                )
                if unified_hits:
                    stores_queried.append("unified")
                    all_hits.extend(unified_hits)
            except Exception as e:
                logger.debug("unified recall failed: %s", e)

        # Graph neighborhood — seeded by chroma top-3 ids.
        if self.graph is not None and with_graph:
            seeds: list[str] = []
            if not isinstance(chroma_hits, Exception) and chroma_hits:
                seeds = [h.id for h in chroma_hits[:3]]
            try:
                neigh = await asyncio.to_thread(
                    self.graph.neighborhood, seeds, depth=1, limit=k
                )
                stores_queried.append("graph")
                all_hits.extend(self._graph_rows_to_hits(neigh))
            except Exception as e:
                logger.debug("graph.neighborhood failed: %s", e)

        # Dedup by id and by normalized text; keep highest score.
        merged: dict[str, RecallHit] = {}
        for h in all_hits:
            key = h.id or f"text::{h.text.strip().lower()[:160]}"
            existing = merged.get(key)
            if existing is None or h.score > existing.score:
                merged[key] = h
        hits = list(merged.values())
        hits.sort(key=lambda h: h.score, reverse=True)

        # Optional rerank.
        if self.reranker is not None:
            hits = self.reranker.rerank(query, hits, top_k=k)
        else:
            hits = hits[:k]

        elapsed = (time.perf_counter() - t0) * 1000.0
        result = RecallResult(
            query=query,
            hits=hits,
            elapsed_ms=elapsed,
            stores_queried=stores_queried,
        )

        self._safe_emit(
            "nb:memory_read",
            {
                "query": query[:120],
                "hit_count": len(hits),
                "stores": stores_queried,
            },
        )
        return result

    @staticmethod
    def _graph_rows_to_hits(rows: list[dict] | dict) -> list[RecallHit]:
        hits: list[RecallHit] = []
        if isinstance(rows, dict):
            graph_nodes = rows.get("nodes") or []
            graph_links = rows.get("links") or []
            rows = []
            for node in graph_nodes:
                if not isinstance(node, dict):
                    continue
                props = node.get("props") if isinstance(node.get("props"), dict) else {}
                rows.append({
                    "id": node.get("id") or props.get("id"),
                    "label": node.get("label") or props.get("label"),
                    "text": node.get("text") or props.get("text") or node.get("label") or props.get("label"),
                    "type": props.get("type") or node.get("type") or "semantic",
                    "score": node.get("score") or props.get("confidence") or 0.4,
                    "graph_degree": sum(
                        1 for link in graph_links
                        if isinstance(link, dict) and (link.get("source") == node.get("id") or link.get("target") == node.get("id"))
                    ),
                })
        for row in rows or []:
            if not isinstance(row, dict):
                continue
            mid = str(row.get("id") or row.get("memory_id") or row.get("concept_id") or "")
            if not mid:
                continue
            text = str(row.get("text") or row.get("label") or "")
            try:
                score = float(row.get("score", 0.4))
            except (TypeError, ValueError):
                score = 0.4
            mtype = row.get("type") if row.get("type") in {
                "episodic", "semantic", "procedural", "outcome", "interactions"
            } else "semantic"
            hits.append(
                RecallHit(
                    id=mid,
                    text=text,
                    score=max(0.0, min(1.0, score)),
                    type=mtype,  # type: ignore[arg-type]
                    source_store="graph",
                    metadata={k: v for k, v in row.items() if k not in {"id", "text", "label", "score"}},
                )
            )
        return hits

    # ------------------------------------------------------------------ forget

    async def forget(self, id: str) -> bool:
        if not id:
            return False
        ok_chroma = False
        try:
            removed = await asyncio.to_thread(self.chroma.delete, [id], None)
            ok_chroma = removed > 0
        except Exception as e:
            logger.warning("chroma.delete failed: %s", e)
        try:
            await asyncio.to_thread(self.mem0.delete, id)
        except Exception as e:
            logger.debug("mem0.delete swallowed: %s", e)
        ok_unified = False
        if self._unified is not None:
            try:
                ok_unified = await asyncio.to_thread(self._unified.delete, id)
            except Exception as e:
                logger.debug("unified delete swallowed: %s", e)
        return ok_chroma or ok_unified

    # ------------------------------------------------------------------ stats

    def stats(self) -> dict[str, Any]:
        unified_count = 0
        if self._unified is not None:
            try:
                unified_count = self._unified.count()
            except Exception:
                unified_count = 0
        return {
            "chroma": self.chroma.stats(),
            "mem0": self.mem0.health(),
            "graph": "connected" if self.graph is not None else "missing",
            "unified_count": unified_count,
            "embed_dim": self.embedder.dim,
        }

    def health(self) -> dict[str, Any]:
        chroma_ok = True
        chroma_err: str | None = None
        try:
            self.chroma.stats()
        except Exception as e:
            chroma_ok = False
            chroma_err = str(e)
        return {
            "chroma": {"ok": chroma_ok, "error": chroma_err},
            "mem0": self.mem0.health(),
            "unified": {"ok": self._unified is not None},
            "embedder": {
                "model": self.embedder.model_name,
                "dim": self.embedder.dim,
            },
            "graph": "connected" if self.graph is not None else "missing",
        }

    # ------------------------------------------------------------------ helpers

    def _recall_unified(
        self,
        query: str,
        *,
        k: int,
        types: list[MemoryType] | None,
        user_id: str,
    ) -> list[RecallHit]:
        if self._unified is None:
            return []
        wanted = set(types or [])
        records = self._unified.search(query=query, tenant_id=user_id or None, limit=k)
        hits: list[RecallHit] = []
        for record in records:
            mtype = record.memory_type if record.memory_type in {
                "episodic", "semantic", "procedural", "outcome", "interactions"
            } else "semantic"
            if wanted and mtype not in wanted:
                continue
            score = max(0.0, min(1.0, record.importance * 0.3 + record.confidence * 0.2 + 0.5))
            hits.append(
                RecallHit(
                    id=record.id,
                    text=record.text,
                    score=score,
                    type=mtype,  # type: ignore[arg-type]
                    source_store="unified",
                    metadata=record.vector_metadata(),
                )
            )
        return hits[:k]

    def _safe_emit(self, channel: str, payload: dict) -> None:
        if self._emit is None:
            return
        try:
            self._emit(channel, payload)
        except Exception as e:
            logger.debug("bridge_emit(%s) failed: %s", channel, e)
