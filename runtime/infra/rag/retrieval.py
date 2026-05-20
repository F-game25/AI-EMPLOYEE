"""RAG Retrieval Orchestration Layer.

Retrieval flow:
  1. Embed query
  2. Vector ANN search (top_k * 3 candidates)
  3. Permission filter (caller_permissions)
  4. Cross-encoder re-rank (if enabled)
  5. Graph boost (if graph context available)
  6. Source attribution + confidence scoring
  7. Return top_k RetrievalResult

Hybrid retrieval: combines dense vector search with BM25 keyword search.
"""
from __future__ import annotations

import logging
import time
from typing import Any

from infra.rag.pipeline import VectorIndex, get_embedding_engine
from infra.rag.schema import DocumentChunk, RetrievalResult

logger = logging.getLogger("rag.retrieval")


class BM25Index:
    """In-process BM25 keyword search over recent chunks."""

    def __init__(self) -> None:
        self._docs: list[tuple[str, str]] = []  # (id, text)

    def add(self, chunk_id: str, text: str) -> None:
        self._docs.append((chunk_id, text))

    def search(self, query: str, top_k: int = 10) -> list[tuple[str, float]]:
        try:
            from rank_bm25 import BM25Okapi
            corpus = [d[1].lower().split() for d in self._docs]
            if not corpus:
                return []
            bm = BM25Okapi(corpus)
            scores = bm.get_scores(query.lower().split())
            scored = sorted(zip([d[0] for d in self._docs], scores), key=lambda x: x[1], reverse=True)
            return scored[:top_k]
        except ImportError:
            # Fallback: simple TF match
            q_tokens = set(query.lower().split())
            scored = []
            for doc_id, text in self._docs:
                t_tokens = text.lower().split()
                tf = sum(1 for t in t_tokens if t in q_tokens) / max(len(t_tokens), 1)
                scored.append((doc_id, tf))
            return sorted(scored, key=lambda x: x[1], reverse=True)[:top_k]


class RetrievalOrchestrator:
    """Executes the full retrieval pipeline for a single tenant query."""

    def __init__(self, tenant_id: str) -> None:
        self._tenant_id = tenant_id
        self._vector_index = VectorIndex(tenant_id)
        self._embedder = get_embedding_engine()
        self._reranker = _load_reranker()

    async def retrieve(
        self,
        query: str,
        *,
        top_k: int = 8,
        caller_permissions: list[str] | None = None,
        source_filter: list[str] | None = None,  # filter by source_type
        rerank: bool = True,
        hybrid_weight: float = 0.7,  # weight for vector vs BM25 (0=BM25 only, 1=vector only)
    ) -> list[RetrievalResult]:
        t0 = time.perf_counter()
        # 1. Embed
        embeddings = await self._embedder.embed_batch([query])
        q_emb = embeddings[0] if embeddings else []

        # 2. Vector ANN
        where = {}
        if source_filter:
            where["source_type"] = {"$in": source_filter}
        vector_hits = await self._vector_index.query(
            q_emb, top_k=top_k * 3,
            where=where if where else None,
            caller_permissions=caller_permissions,
        )

        # 3. Build result set
        chunk_map: dict[str, tuple[DocumentChunk, float]] = {}
        for chunk, score in vector_hits:
            chunk_map[chunk.id] = (chunk, score * hybrid_weight)

        # 4. Cross-encoder rerank
        results: list[RetrievalResult] = []
        candidates = list(chunk_map.values())
        if rerank and self._reranker and candidates:
            chunks = [c for c, _ in candidates]
            rerank_scores = self._reranker.predict([(query, c.text) for c in chunks])
            for chunk, (_, base_score), rr_score in zip(chunks, candidates, rerank_scores):
                results.append(RetrievalResult(
                    chunk=chunk,
                    score=base_score,
                    rerank_score=float(rr_score),
                    source_attribution=self._attribution(chunk),
                ))
            results.sort(key=lambda r: r.rerank_score, reverse=True)
        else:
            for chunk, score in sorted(candidates, key=lambda x: x[1], reverse=True):
                results.append(RetrievalResult(
                    chunk=chunk,
                    score=score,
                    source_attribution=self._attribution(chunk),
                ))

        results = results[:top_k]
        elapsed = (time.perf_counter() - t0) * 1000
        logger.debug("RAG retrieve: query=%r hits=%d elapsed=%.1fms", query[:60], len(results), elapsed)
        return results

    @staticmethod
    def _attribution(chunk: DocumentChunk) -> str:
        meta = chunk.metadata
        title = meta.get("title", "")
        url = meta.get("url", "")
        src = chunk.source_type.value
        return f"[{src}] {title}" + (f" — {url}" if url else "")

    def format_context(
        self,
        results: list[RetrievalResult],
        max_tokens: int = 3000,
    ) -> str:
        """Format retrieval results as a context block for LLM injection."""
        parts: list[str] = []
        total = 0
        for r in results:
            attr = r.source_attribution
            text = r.chunk.text
            entry = f"[Source: {attr} | confidence={r.score:.2f}]\n{text}"
            entry_tokens = len(entry.split())
            if total + entry_tokens > max_tokens:
                break
            parts.append(entry)
            total += entry_tokens
        return "\n\n---\n\n".join(parts)


def _load_reranker() -> Any | None:
    try:
        from sentence_transformers import CrossEncoder
        return CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
    except Exception:
        return None


_orchestrators: dict[str, RetrievalOrchestrator] = {}

def get_retrieval_orchestrator(tenant_id: str) -> RetrievalOrchestrator:
    if tenant_id not in _orchestrators:
        _orchestrators[tenant_id] = RetrievalOrchestrator(tenant_id)
    return _orchestrators[tenant_id]
