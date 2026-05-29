"""Persistent Chroma adapter — one collection per memory type."""
from __future__ import annotations

import logging
from collections import defaultdict
from pathlib import Path
from typing import Any

from neural_brain.memory.embedding_provider import EmbeddingProvider
from neural_brain.memory.memory_schemas import MemoryItem, RecallHit

logger = logging.getLogger(__name__)


class ChromaAdapter:
    KNOWN_COLLECTIONS = ("episodic", "semantic", "procedural", "outcome", "interactions")

    def __init__(self, persist_dir: str | Path, embedder: EmbeddingProvider) -> None:
        try:
            import chromadb
            from chromadb.config import Settings
        except ImportError as e:  # pragma: no cover - import guard
            raise RuntimeError(
                "chromadb not installed; pip install chromadb"
            ) from e

        path = Path(persist_dir)
        try:
            path.mkdir(parents=True, exist_ok=True)
            # Touch-test write access.
            probe = path / ".write_probe"
            probe.write_text("")
            probe.unlink()
        except Exception as e:
            raise RuntimeError(f"chroma persist_dir not writable: {path}: {e}") from e

        self._embedder = embedder
        self._client = chromadb.PersistentClient(
            path=str(path),
            settings=Settings(anonymized_telemetry=False),
        )
        self._collections: dict[str, Any] = {}
        for name in self.KNOWN_COLLECTIONS:
            self._collections[name] = self._client.get_or_create_collection(
                name=name,
                metadata={"hnsw:space": "cosine"},
            )

    def add(self, items: list[MemoryItem]) -> list[str]:
        if not items:
            return []
        # Group by type.
        groups: dict[str, list[MemoryItem]] = defaultdict(list)
        for item in items:
            if item.type not in self._collections:
                logger.warning("unknown memory type %s; routing to semantic", item.type)
                groups["semantic"].append(item)
            else:
                groups[item.type].append(item)

        all_ids: list[str] = []
        for type_, batch in groups.items():
            texts = [it.text for it in batch]
            embeddings = self._embedder.encode(texts, normalize=True)
            ids = [it.id for it in batch]
            metadatas = [self._meta_for(it) for it in batch]
            self._collections[type_].upsert(
                ids=ids,
                documents=texts,
                embeddings=embeddings,
                metadatas=metadatas,
            )
            all_ids.extend(ids)
        return all_ids

    def query(
        self,
        query_text: str,
        *,
        n_results: int = 10,
        types: list[str] | None = None,
        where: dict | None = None,
    ) -> list[RecallHit]:
        if not query_text:
            return []
        target_types = list(types) if types else list(self.KNOWN_COLLECTIONS)
        emb = self._embedder.encode([query_text], normalize=True)
        if not emb:
            return []
        q_emb = emb[0]

        hits: list[RecallHit] = []
        for type_ in target_types:
            coll = self._collections.get(type_)
            if coll is None:
                continue
            try:
                kwargs: dict[str, Any] = {
                    "query_embeddings": [q_emb],
                    "n_results": n_results,
                }
                if where:
                    kwargs["where"] = where
                res = coll.query(**kwargs)
            except Exception as e:
                logger.warning("chroma query failed on %s: %s", type_, e)
                continue
            hits.extend(self._rows_to_hits(res, type_))

        hits.sort(key=lambda h: h.score, reverse=True)
        return hits[:n_results]

    def delete(self, ids: list[str], type_: str | None = None) -> int:
        if not ids:
            return 0
        targets = [type_] if type_ else list(self.KNOWN_COLLECTIONS)
        removed = 0
        for t in targets:
            coll = self._collections.get(t)
            if coll is None:
                continue
            try:
                coll.delete(ids=ids)
                removed += len(ids)
            except Exception as e:
                logger.debug("chroma delete on %s skipped: %s", t, e)
        return removed

    def stats(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for name, coll in self._collections.items():
            try:
                out[name] = int(coll.count())
            except Exception:
                out[name] = -1
        return out

    # ------------------------------------------------------------------ helpers

    @staticmethod
    def _meta_for(item: MemoryItem) -> dict[str, Any]:
        meta: dict[str, Any] = {
            "user_id": item.user_id,
            "importance": float(item.importance),
            "source": item.source,
            "created_at": float(item.created_at),
            "type": item.type,
        }
        # Only flat scalars are safe in Chroma metadata.
        for k, v in (item.metadata or {}).items():
            if isinstance(v, (str, int, float, bool)) or v is None:
                meta[k] = v
            else:
                meta[k] = str(v)
        return meta

    def _rows_to_hits(self, res: dict, type_: str) -> list[RecallHit]:
        hits: list[RecallHit] = []
        ids_lists = res.get("ids") or []
        docs_lists = res.get("documents") or []
        dist_lists = res.get("distances") or []
        meta_lists = res.get("metadatas") or []
        if not ids_lists:
            return hits
        ids = ids_lists[0] or []
        docs = (docs_lists[0] if docs_lists else []) or []
        dists = (dist_lists[0] if dist_lists else []) or []
        metas = (meta_lists[0] if meta_lists else []) or []
        for i, mid in enumerate(ids):
            doc = docs[i] if i < len(docs) else ""
            dist = float(dists[i]) if i < len(dists) and dists[i] is not None else 1.0
            meta = metas[i] if i < len(metas) and isinstance(metas[i], dict) else {}
            score = max(0.0, 1.0 - dist)
            hits.append(
                RecallHit(
                    id=mid,
                    text=doc or "",
                    score=score,
                    type=meta.get("type", type_),  # type: ignore[arg-type]
                    source_store="chroma",
                    metadata=dict(meta),
                )
            )
        return hits
