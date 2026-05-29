"""Dual vector backend adapter.

Strategy:
- Chroma = always-on primary (embedded persistent, no Docker required)
- Qdrant = secondary when running (Docker container at :6333)
- Writes go to BOTH when both available; reads go to primary (Chroma)
- Graceful degrade: if Qdrant offline, log warning and proceed Chroma-only

Public API mirrors existing VectorStore so callers can swap painlessly.
"""
import os
import time
import hashlib
import logging
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field

log = logging.getLogger(__name__)


@dataclass
class Match:
    id: str
    text: str
    score: float
    metadata: Dict[str, Any] = field(default_factory=dict)


class MemoryAdapter:
    COLLECTION_PREFIX = "ai_employee_memory"
    EMBED_DIM = 384  # all-MiniLM-L6-v2
    LEGACY_PATH = os.path.expanduser("~/.ai-employee/chroma_db")
    LEGACY_COLLECTION = "ai_employee_memory"

    def __init__(self, tenant_id: str = "default"):
        # Per-tenant namespacing (2026-05-18 security audit CRITICAL #2):
        # each tenant gets its own Chroma path + collection name + Qdrant collection.
        # Prevents cross-tenant memory poisoning via shared global store.
        self.tenant_id = tenant_id
        self.collection_name = f"{self.COLLECTION_PREFIX}_{tenant_id}"
        self.chroma_path = os.path.expanduser(f"~/.ai-employee/tenants/{tenant_id}/chroma_db")
        self.chroma_client = None
        self.chroma_collection = None
        self.qdrant_client = None
        self._embedder = None
        self._init_chroma()
        self._init_qdrant()
        log.info(
            "MemoryAdapter ready for tenant=%s: chroma=%s, qdrant=%s",
            tenant_id,
            self.chroma_collection is not None,
            self.qdrant_client is not None,
        )

    # ------------------------------------------------------------------ init
    def _init_chroma(self) -> None:
        try:
            import chromadb
            from chromadb.config import Settings

            # Migrate-on-init: if a legacy ~/.ai-employee/chroma_db exists and we are
            # the 'default' tenant, move it into the tenant path so historical data
            # stays accessible. Idempotent (only runs if tenant path empty).
            if (
                self.tenant_id == "default"
                and os.path.isdir(self.LEGACY_PATH)
                and not os.path.exists(self.chroma_path)
            ):
                import shutil
                os.makedirs(os.path.dirname(self.chroma_path), exist_ok=True)
                shutil.move(self.LEGACY_PATH, self.chroma_path)
                log.info("Migrated legacy chroma_db → %s", self.chroma_path)

            os.makedirs(self.chroma_path, exist_ok=True)
            self.chroma_client = chromadb.PersistentClient(
                path=self.chroma_path,
                settings=Settings(anonymized_telemetry=False),
            )
            # Try collection name with tenant suffix; fall back to legacy name if it
            # exists in the (now moved) database — keeps existing entries searchable.
            try:
                self.chroma_collection = self.chroma_client.get_collection(self.LEGACY_COLLECTION)
                # Rename: copy entries to tenant-named collection (idempotent if already done)
                tenant_collection = self.chroma_client.get_or_create_collection(name=self.collection_name)
                if tenant_collection.count() == 0 and self.chroma_collection.count() > 0:
                    legacy = self.chroma_collection.get(include=["embeddings", "documents", "metadatas"])
                    if legacy.get("ids"):
                        tenant_collection.add(
                            ids=legacy["ids"],
                            embeddings=legacy.get("embeddings"),
                            documents=legacy.get("documents"),
                            metadatas=legacy.get("metadatas"),
                        )
                        log.info("Copied %d entries from legacy collection → %s", len(legacy["ids"]), self.collection_name)
                self.chroma_collection = tenant_collection
            except Exception:
                self.chroma_collection = self.chroma_client.get_or_create_collection(
                    name=self.collection_name
                )
        except Exception as e:
            log.warning("Chroma init failed for tenant %s: %s", self.tenant_id, e)

    def _init_qdrant(self) -> None:
        try:
            from qdrant_client import QdrantClient
            from qdrant_client.http.models import VectorParams, Distance

            client = QdrantClient(host="localhost", port=6333, timeout=2.0)
            existing = [c.name for c in client.get_collections().collections]
            if self.collection_name not in existing:
                client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=VectorParams(
                        size=self.EMBED_DIM, distance=Distance.COSINE
                    ),
                )
            self.qdrant_client = client
        except Exception as e:
            log.info("Qdrant unavailable (continuing Chroma-only): %s", e)

    def _get_embedder(self):
        if self._embedder is None:
            try:
                from sentence_transformers import SentenceTransformer

                self._embedder = SentenceTransformer("all-MiniLM-L6-v2")
            except Exception as e:
                log.error("SentenceTransformer load failed: %s", e)
                raise RuntimeError("Sentence transformer required for MemoryAdapter")
        return self._embedder

    # ------------------------------------------------------------- embeddings
    def embed(self, text: str) -> List[float]:
        return self._get_embedder().encode(text, convert_to_tensor=False).tolist()

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        return (
            self._get_embedder()
            .encode(texts, convert_to_tensor=False, batch_size=32)
            .tolist()
        )

    # ------------------------------------------------------------------ ids
    @staticmethod
    def _qdrant_id(orig_id: str) -> int:
        # Qdrant requires numeric or UUID ids — hash original string to int
        return int(hashlib.md5(orig_id.encode()).hexdigest()[:15], 16)

    # --------------------------------------------------------------- writes
    def add(
        self,
        text: str,
        metadata: Optional[dict] = None,
        id: Optional[str] = None,
    ) -> str:
        if not text or not text.strip():
            raise ValueError("text required")
        if id is None:
            id = hashlib.md5(f"{text}{time.time()}".encode()).hexdigest()[:16]
        meta = dict(metadata or {})
        meta.setdefault("ts", time.time())
        emb = self.embed(text)

        if self.chroma_collection is not None:
            try:
                self.chroma_collection.upsert(
                    ids=[id],
                    embeddings=[emb],
                    documents=[text],
                    metadatas=[meta],
                )
            except Exception as e:
                log.error("Chroma upsert failed: %s", e)

        if self.qdrant_client is not None:
            try:
                from qdrant_client.http.models import PointStruct

                self.qdrant_client.upsert(
                    collection_name=self.collection_name,
                    points=[
                        PointStruct(
                            id=self._qdrant_id(id),
                            vector=emb,
                            payload={**meta, "text": text, "orig_id": id},
                        )
                    ],
                )
            except Exception as e:
                log.warning("Qdrant upsert failed (non-fatal): %s", e)
        return id

    def add_batch(self, items: List[dict]) -> List[str]:
        """items = [{text, metadata?, id?}, ...]"""
        ids: List[str] = []
        for n, it in enumerate(items):
            ids.append(
                it.get("id")
                or hashlib.md5(
                    f"{it['text']}{time.time()}{n}".encode()
                ).hexdigest()[:16]
            )
        texts = [it["text"] for it in items]
        metas: List[dict] = []
        for it in items:
            m = dict(it.get("metadata") or {})
            m.setdefault("ts", time.time())
            metas.append(m)
        embs = self.embed_batch(texts)

        if self.chroma_collection is not None:
            try:
                self.chroma_collection.upsert(
                    ids=ids, embeddings=embs, documents=texts, metadatas=metas
                )
            except Exception as e:
                log.error("Chroma batch upsert failed: %s", e)

        if self.qdrant_client is not None:
            try:
                from qdrant_client.http.models import PointStruct

                points = [
                    PointStruct(
                        id=self._qdrant_id(oid),
                        vector=emb,
                        payload={**meta, "text": text, "orig_id": oid},
                    )
                    for oid, emb, text, meta in zip(ids, embs, texts, metas)
                ]
                self.qdrant_client.upsert(
                    collection_name=self.collection_name, points=points
                )
            except Exception as e:
                log.warning("Qdrant batch upsert failed: %s", e)
        return ids

    # --------------------------------------------------------------- reads
    def search(
        self,
        query: str,
        top_k: int = 10,
        filter: Optional[dict] = None,
    ) -> List[Match]:
        if not query or not query.strip():
            return []
        emb = self.embed(query)
        if self.chroma_collection is not None:
            try:
                result = self.chroma_collection.query(
                    query_embeddings=[emb],
                    n_results=top_k,
                    where=filter if filter else None,
                )
                matches: List[Match] = []
                ids_row = (result.get("ids") or [[]])[0]
                docs_row = (result.get("documents") or [[]])[0]
                metas_row = (result.get("metadatas") or [[]])[0]
                dists_row = (result.get("distances") or [[0.0] * len(ids_row)])[0]
                for i, mid in enumerate(ids_row):
                    dist = dists_row[i] if i < len(dists_row) else 0.0
                    matches.append(
                        Match(
                            id=mid,
                            text=docs_row[i] if i < len(docs_row) else "",
                            score=max(0.0, 1.0 - float(dist)),
                            metadata=(metas_row[i] if i < len(metas_row) else {}) or {},
                        )
                    )
                return matches
            except Exception as e:
                log.error("Chroma search failed: %s", e)
        return []

    def delete(self, id: str) -> bool:
        ok = False
        if self.chroma_collection is not None:
            try:
                self.chroma_collection.delete(ids=[id])
                ok = True
            except Exception as e:
                log.error("Chroma delete failed: %s", e)
        if self.qdrant_client is not None:
            try:
                self.qdrant_client.delete(
                    collection_name=self.collection_name,
                    points_selector=[self._qdrant_id(id)],
                )
            except Exception as e:
                log.warning("Qdrant delete failed: %s", e)
        return ok

    def count(self) -> int:
        if self.chroma_collection is not None:
            try:
                return int(self.chroma_collection.count())
            except Exception:
                pass
        return 0

    def status(self) -> dict:
        return {
            "chroma": {
                "available": self.chroma_collection is not None,
                "count": self.count(),
            },
            "qdrant": {"available": self.qdrant_client is not None},
            "primary": "chroma",
        }


_tenant_adapters: Dict[str, "MemoryAdapter"] = {}
_default_tenant = "default"


def _current_tenant_id() -> str:
    """Resolve the active tenant from FastAPI's request context. Falls back to
    'default' when no context (CLI invocations, scheduler ticks, tests)."""
    try:
        from core.tenancy import _current_tenant  # ContextVar
        ctx = _current_tenant.get()
        if ctx and ctx.tenant_id:
            return ctx.tenant_id
    except Exception:
        pass
    return _default_tenant


def get_adapter(tenant_id: Optional[str] = None) -> MemoryAdapter:
    """Return the MemoryAdapter for the active tenant.

    - If tenant_id is given, use it directly (callers running outside request
      context, e.g. background scheduler, can pass explicitly).
    - Otherwise, resolve from FastAPI request ContextVar, falling back to
      'default' for local-mode and tests.
    - Adapters are cached per tenant (Chroma client + collection are expensive).
    """
    tid = tenant_id or _current_tenant_id()
    if tid not in _tenant_adapters:
        _tenant_adapters[tid] = MemoryAdapter(tenant_id=tid)
    return _tenant_adapters[tid]
