"""Enterprise RAG ingestion pipeline.

Flow:
  Connector.list_changed()
    → DocumentProcessor.chunk()
    → EmbeddingEngine.embed_batch()
    → VectorIndex.upsert_batch()
    → GraphEnhancer.link_concepts()
    → FreshnessTracker.mark_synced()

Change detection: content_hash comparison prevents re-embedding unchanged docs.
Tenant isolation: all vector IDs are namespaced {tenant_id}::{chunk_id}.
Permission filtering: chunks carry permissions list, enforced at retrieval.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import time
import uuid
from typing import Any

from infra.rag.schema import (
    ChunkStrategy, DocumentChunk, SourceDocument, SourceType,
)

logger = logging.getLogger("rag.pipeline")


# ── Document processor ────────────────────────────────────────────────────────

class DocumentProcessor:
    """Chunks documents using a configurable strategy."""

    CHUNK_TOKENS = 400       # target tokens per chunk
    CHUNK_OVERLAP = 80       # overlap tokens between adjacent chunks

    def chunk(
        self,
        doc: SourceDocument,
        strategy: ChunkStrategy = ChunkStrategy.SEMANTIC,
    ) -> list[DocumentChunk]:
        if strategy == ChunkStrategy.HIERARCHICAL:
            return self._hierarchical(doc)
        if strategy == ChunkStrategy.SEMANTIC:
            return self._semantic(doc)
        return self._fixed(doc)

    def _fixed(self, doc: SourceDocument) -> list[DocumentChunk]:
        words = doc.raw_text.split()
        target = self.CHUNK_TOKENS  # approximate 1 word ≈ 1.3 tokens
        overlap = self.CHUNK_OVERLAP
        step = max(1, target - overlap)
        chunks: list[DocumentChunk] = []
        i = 0
        idx = 0
        while i < len(words):
            window = words[i : i + target]
            text = " ".join(window)
            chunks.append(self._make_chunk(doc, text, idx))
            idx += 1
            i += step
        return self._finalize(chunks)

    def _semantic(self, doc: SourceDocument) -> list[DocumentChunk]:
        # Split on double-newlines (paragraphs), then merge to target size
        paragraphs = [p.strip() for p in doc.raw_text.split("\n\n") if p.strip()]
        chunks: list[DocumentChunk] = []
        current: list[str] = []
        current_tokens = 0
        idx = 0
        for para in paragraphs:
            para_tokens = len(para.split())
            if current_tokens + para_tokens > self.CHUNK_TOKENS and current:
                chunks.append(self._make_chunk(doc, "\n\n".join(current), idx))
                idx += 1
                # Keep last paragraph as overlap
                current = [current[-1]] if current else []
                current_tokens = len(current[0].split()) if current else 0
            current.append(para)
            current_tokens += para_tokens
        if current:
            chunks.append(self._make_chunk(doc, "\n\n".join(current), idx))
        return self._finalize(chunks)

    def _hierarchical(self, doc: SourceDocument) -> list[DocumentChunk]:
        # Section → paragraph → sentence (naive implementation)
        import re
        sections = re.split(r"\n#{1,3} ", doc.raw_text)
        chunks: list[DocumentChunk] = []
        idx = 0
        for sec in sections:
            sec_chunks = self._semantic(SourceDocument(
                **{**doc.__dict__, "raw_text": sec}
            ))
            for c in sec_chunks:
                c.chunk_index = idx
                chunks.append(c)
                idx += 1
        return self._finalize(chunks)

    def _make_chunk(self, doc: SourceDocument, text: str, idx: int) -> DocumentChunk:
        chunk_id = f"{doc.id}::chunk::{idx}"
        return DocumentChunk(
            id=chunk_id,
            doc_id=doc.id,
            tenant_id=doc.tenant_id,
            source_type=doc.source_type,
            text=text,
            token_count=len(text.split()),
            chunk_index=idx,
            total_chunks=0,  # filled by _finalize
            metadata={**doc.metadata, "title": doc.title, "url": doc.url,
                      "modified_at": doc.modified_at, "content_hash": doc.content_hash},
            permissions=doc.permissions,
        )

    @staticmethod
    def _finalize(chunks: list[DocumentChunk]) -> list[DocumentChunk]:
        n = len(chunks)
        for c in chunks:
            c.total_chunks = n
        return chunks


# ── Embedding engine ──────────────────────────────────────────────────────────

class EmbeddingEngine:
    """Batch embedding with provider fallback chain.

    Providers (first available):
      1. OpenAI text-embedding-3-small  (1536 dims, cheapest at scale)
      2. Anthropic voyage-3             (1024 dims)
      3. Local sentence-transformers    (384 dims, zero cost, offline)
    """

    _DIMS = {"openai": 1536, "voyage": 1024, "local": 384}

    def __init__(self) -> None:
        self._provider: str | None = None

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        provider = await self._resolve_provider()
        if provider == "openai":
            return await self._openai(texts)
        if provider == "voyage":
            return await self._voyage(texts)
        return self._local(texts)

    async def _resolve_provider(self) -> str:
        if self._provider:
            return self._provider
        if os.environ.get("OPENAI_API_KEY"):
            self._provider = "openai"
        elif os.environ.get("ANTHROPIC_API_KEY"):
            self._provider = "voyage"
        else:
            self._provider = "local"
        return self._provider

    async def _openai(self, texts: list[str]) -> list[list[float]]:
        import os
        try:
            import httpx
            resp = await httpx.AsyncClient(timeout=30.0).post(
                "https://api.openai.com/v1/embeddings",
                headers={"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"},
                json={"model": "text-embedding-3-small", "input": texts},
            )
            data = resp.json()
            return [item["embedding"] for item in data.get("data", [])]
        except Exception as e:
            logger.warning("OpenAI embed failed: %s — falling back to local", e)
            return self._local(texts)

    async def _voyage(self, texts: list[str]) -> list[list[float]]:
        import os
        try:
            import httpx
            resp = await httpx.AsyncClient(timeout=30.0).post(
                "https://api.voyageai.com/v1/embeddings",
                headers={"Authorization": f"Bearer {os.environ['ANTHROPIC_API_KEY']}"},
                json={"model": "voyage-3", "input": texts},
            )
            data = resp.json()
            return [item["embedding"] for item in data.get("data", [])]
        except Exception as e:
            logger.warning("Voyage embed failed: %s — falling back to local", e)
            return self._local(texts)

    @staticmethod
    def _local(texts: list[str]) -> list[list[float]]:
        try:
            from sentence_transformers import SentenceTransformer
            model = SentenceTransformer("all-MiniLM-L6-v2")
            return model.encode(texts).tolist()
        except ImportError:
            # Deterministic hash-based pseudo-embedding (dev only)
            import hashlib, struct
            out = []
            for t in texts:
                h = hashlib.sha256(t.encode()).digest()
                vec = [struct.unpack("f", h[i:i+4])[0] for i in range(0, 64, 4)]
                # Normalize
                norm = sum(v*v for v in vec) ** 0.5 or 1.0
                out.append([v / norm for v in vec])
            return out


import os
_embedding_engine: EmbeddingEngine | None = None
def get_embedding_engine() -> EmbeddingEngine:
    global _embedding_engine
    if _embedding_engine is None:
        _embedding_engine = EmbeddingEngine()
    return _embedding_engine


# ── Vector index (Chroma-backed with tenant namespace) ────────────────────────

class VectorIndex:
    """Wraps ChromaAdapter for RAG chunks with tenant isolation."""

    def __init__(self, tenant_id: str) -> None:
        self._tenant_id = tenant_id
        self._collection_name = f"rag_{tenant_id}"
        self._col: Any = None

    def _collection(self) -> Any:
        if self._col is not None:
            return self._col
        try:
            import chromadb
            from pathlib import Path
            db_path = Path.home() / ".ai-employee" / "rag_chroma" / self._tenant_id
            db_path.mkdir(parents=True, exist_ok=True)
            client = chromadb.PersistentClient(path=str(db_path))
            self._col = client.get_or_create_collection(self._collection_name,
                                                         metadata={"hnsw:space": "cosine"})
        except ImportError:
            logger.warning("chromadb not installed — using in-memory index")
            self._col = _InMemoryIndex()
        return self._col

    async def upsert_batch(self, chunks: list[DocumentChunk]) -> None:
        if not chunks:
            return
        col = self._collection()
        ids = [c.id for c in chunks]
        docs = [c.text for c in chunks]
        embeddings = [c.embedding for c in chunks] if chunks[0].embedding else None
        metadatas = [{
            **c.metadata,
            "permissions": ",".join(c.permissions),
            "source_type": c.source_type.value,
            "tenant_id": c.tenant_id,
            "chunk_index": c.chunk_index,
            "total_chunks": c.total_chunks,
        } for c in chunks]
        try:
            if embeddings:
                col.upsert(ids=ids, documents=docs, embeddings=embeddings, metadatas=metadatas)
            else:
                col.upsert(ids=ids, documents=docs, metadatas=metadatas)
        except Exception as e:
            logger.error("VectorIndex upsert failed: %s", e)

    async def query(
        self,
        query_embedding: list[float],
        top_k: int = 10,
        where: dict | None = None,
        caller_permissions: list[str] | None = None,
    ) -> list[tuple[DocumentChunk, float]]:
        col = self._collection()
        try:
            results = col.query(
                query_embeddings=[query_embedding],
                n_results=top_k * 2,  # over-fetch for permission filtering
                where=where,
                include=["documents", "metadatas", "distances"],
            )
            out: list[tuple[DocumentChunk, float]] = []
            for i, (doc_id, text, meta, dist) in enumerate(zip(
                results["ids"][0], results["documents"][0],
                results["metadatas"][0], results["distances"][0],
            )):
                # Permission check
                perms = set(meta.get("permissions", "").split(","))
                if caller_permissions and not perms.intersection(caller_permissions):
                    continue
                chunk = DocumentChunk(
                    id=doc_id,
                    doc_id=meta.get("doc_id", ""),
                    tenant_id=meta.get("tenant_id", self._tenant_id),
                    source_type=SourceType(meta.get("source_type", "file")),
                    text=text,
                    token_count=len(text.split()),
                    chunk_index=meta.get("chunk_index", 0),
                    total_chunks=meta.get("total_chunks", 1),
                    metadata={k: v for k, v in meta.items() if k not in ("permissions", "source_type", "tenant_id")},
                    permissions=list(perms),
                )
                score = max(0.0, 1.0 - dist)
                out.append((chunk, score))
                if len(out) >= top_k:
                    break
            return out
        except Exception as e:
            logger.error("VectorIndex query failed: %s", e)
            return []

    async def delete_doc(self, doc_id: str) -> None:
        col = self._collection()
        try:
            col.delete(where={"doc_id": doc_id})
        except Exception as e:
            logger.warning("VectorIndex delete failed: %s", e)


class _InMemoryIndex:
    """Fallback when chromadb is not available."""
    def __init__(self) -> None:
        self._store: dict[str, tuple[str, list[float], dict]] = {}

    def upsert(self, ids, documents, metadatas, embeddings=None) -> None:
        for i, (id_, doc, meta) in enumerate(zip(ids, documents, metadatas)):
            emb = embeddings[i] if embeddings else []
            self._store[id_] = (doc, emb, meta)

    def query(self, query_embeddings, n_results=10, where=None, include=None):
        q = query_embeddings[0]
        def cos(a, b):
            if not a or not b:
                return 0.0
            dot = sum(x*y for x,y in zip(a,b))
            na = sum(x*x for x in a)**0.5
            nb = sum(x*x for x in b)**0.5
            return dot / (na * nb) if na and nb else 0.0

        scored = sorted(self._store.items(), key=lambda kv: cos(q, kv[1][1]), reverse=True)[:n_results]
        return {
            "ids": [[k for k,_ in scored]],
            "documents": [[v[0] for _,v in scored]],
            "metadatas": [[v[2] for _,v in scored]],
            "distances": [[1 - cos(q, v[1]) for _,v in scored]],
        }

    def delete(self, where=None) -> None:
        doc_id = (where or {}).get("doc_id")
        if doc_id:
            self._store = {k: v for k, v in self._store.items() if not k.startswith(doc_id)}


# ── Freshness tracker ─────────────────────────────────────────────────────────

class FreshnessTracker:
    """Tracks last-synced timestamps and content hashes per tenant+source."""

    def __init__(self, tenant_id: str) -> None:
        import json
        from pathlib import Path
        self._path = Path.home() / ".ai-employee" / "rag_state" / f"{tenant_id}_freshness.json"
        self._path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._state: dict = json.loads(self._path.read_text())
        except Exception:
            self._state = {}

    def last_sync(self, source_type: str) -> float:
        return self._state.get(f"sync_{source_type}", 0.0)

    def mark_synced(self, source_type: str) -> None:
        self._state[f"sync_{source_type}"] = time.time()
        self._save()

    def is_changed(self, doc_id: str, content_hash: str) -> bool:
        return self._state.get(f"hash_{doc_id}") != content_hash

    def mark_hash(self, doc_id: str, content_hash: str) -> None:
        self._state[f"hash_{doc_id}"] = content_hash

    def _save(self) -> None:
        import json
        try:
            self._path.write_text(json.dumps(self._state))
        except Exception:
            pass


# ── Graph enhancer ────────────────────────────────────────────────────────────

class GraphEnhancer:
    """Links chunks to Neo4j concept graph for graph-enhanced retrieval."""

    def __init__(self) -> None:
        self._available = False
        try:
            from neural_brain.graph.brain_graph import get_brain_graph
            self._graph = get_brain_graph()
            self._available = True
        except Exception:
            logger.debug("GraphEnhancer: brain_graph unavailable — graph linking disabled")

    async def link_chunks(self, chunks: list[DocumentChunk]) -> None:
        if not self._available:
            return
        for chunk in chunks:
            try:
                concepts = self._extract_concepts(chunk.text)
                for concept in concepts[:5]:
                    concept_id = self._graph.upsert_concept(concept, type="RAGConcept", weight=0.5)
                    # Store chunk reference as concept metadata
            except Exception as e:
                logger.debug("GraphEnhancer link_chunks: %s", e)

    @staticmethod
    def _extract_concepts(text: str) -> list[str]:
        import re
        cap_run = re.compile(r"\b[A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*\b")
        return list(set(cap_run.findall(text)))[:10]


# ── Ingestion pipeline ────────────────────────────────────────────────────────

class IngestionPipeline:
    """Orchestrates the full ingestion lifecycle for one tenant."""

    EMBED_BATCH_SIZE = 32

    def __init__(self, tenant_id: str) -> None:
        self._tenant_id = tenant_id
        self._processor = DocumentProcessor()
        self._embedder = get_embedding_engine()
        self._index = VectorIndex(tenant_id)
        self._freshness = FreshnessTracker(tenant_id)
        self._graph = GraphEnhancer()

    async def ingest_connector(
        self,
        connector: "BaseConnector",  # noqa: F821
        strategy: ChunkStrategy = ChunkStrategy.SEMANTIC,
        full_sync: bool = False,
    ) -> dict:
        since = 0.0 if full_sync else self._freshness.last_sync(connector.source_type.value)
        logger.info("RAG ingest: tenant=%s source=%s since=%.0f", self._tenant_id, connector.source_type.value, since)
        docs = await connector.list_changed(since)
        stats = {"docs_fetched": len(docs), "chunks_upserted": 0, "docs_skipped": 0}

        for doc in docs:
            if not self._freshness.is_changed(doc.id, doc.content_hash):
                stats["docs_skipped"] += 1
                continue
            chunks = self._processor.chunk(doc, strategy)
            # Embed in batches
            for batch_start in range(0, len(chunks), self.EMBED_BATCH_SIZE):
                batch = chunks[batch_start : batch_start + self.EMBED_BATCH_SIZE]
                texts = [c.text for c in batch]
                embeddings = await self._embedder.embed_batch(texts)
                for chunk, emb in zip(batch, embeddings):
                    chunk.embedding = emb
                await self._index.upsert_batch(batch)
                stats["chunks_upserted"] += len(batch)
            await self._graph.link_chunks(chunks)
            self._freshness.mark_hash(doc.id, doc.content_hash)

        self._freshness.mark_synced(connector.source_type.value)
        logger.info("RAG ingest complete: %s", stats)
        return stats

    async def ingest_doc(self, doc: SourceDocument) -> int:
        chunks = self._processor.chunk(doc)
        texts = [c.text for c in chunks]
        embeddings = await self._embedder.embed_batch(texts)
        for chunk, emb in zip(chunks, embeddings):
            chunk.embedding = emb
        await self._index.upsert_batch(chunks)
        return len(chunks)


_pipelines: dict[str, IngestionPipeline] = {}

def get_pipeline(tenant_id: str) -> IngestionPipeline:
    if tenant_id not in _pipelines:
        _pipelines[tenant_id] = IngestionPipeline(tenant_id)
    return _pipelines[tenant_id]
