"""Vector Memory — embedding-based semantic memory for AI agents.

Extends the file-based MemoryStore with NVIDIA NV-Embed-v2 vector embeddings
for:
  - Semantic similarity search (find the most relevant leads/entities)
  - Duplicate detection (same business under different names)
  - Interaction tracking with embedding-indexed history

Falls back to keyword-only search (via MemoryStore.search) when the NVIDIA
API key is absent or the NIM endpoint is unreachable — so all callers degrade
gracefully.

Usage::

    from vector_memory import VectorMemory

    vm = VectorMemory()
    vm.upsert("lead:acme-corp", "B2B SaaS company selling analytics to CFOs",
              entity_type="lead", metadata={"niche": "SaaS", "location": "NYC"})

    # Semantic similarity search
    results = vm.search("analytics software for finance teams", top_k=5)
    for r in results:
        print(r["entity_id"], r["score"], r["summary"])

    # Deduplication check
    dupes = vm.find_duplicates("lead:acme-corp", threshold=0.92)

    # Mark an interaction
    vm.record_interaction("lead:acme-corp", "Sent cold email", sentiment="neutral")

Environment variables:
    NVIDIA_API_KEY      — required for semantic search (falls back to keyword)
    VECTOR_MEMORY_DIR   — override storage directory
                          (default: ~/.ai-employee/state/vector_memory)
    VECTOR_SIMILARITY_THRESHOLD  — cosine threshold for dedup (default: 0.92)
"""
from __future__ import annotations

import json
import logging
import math
import os
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger("vector_memory")

AI_HOME = Path(os.environ.get("AI_HOME", str(Path.home() / ".ai-employee")))
VECTOR_MEMORY_DIR = Path(
    os.environ.get("VECTOR_MEMORY_DIR", str(AI_HOME / "state" / "vector_memory"))
)
VECTOR_SIMILARITY_THRESHOLD = float(
    os.environ.get("VECTOR_SIMILARITY_THRESHOLD", "0.92")
)

# ── NIM client import (optional dependency) ───────────────────────────────────

_nim_client = None


def _get_nim_client():
    global _nim_client
    if _nim_client is not None:
        return _nim_client
    # Try to import from sibling directory
    _nim_dir = Path(__file__).parent.parent / "nvidia-nim"
    if str(_nim_dir) not in sys.path:
        sys.path.insert(0, str(_nim_dir))
    try:
        from nim_client import get_client  # type: ignore
        _nim_client = get_client()
        return _nim_client
    except ImportError:
        logger.debug("vector_memory: nim_client not available — falling back to keyword search")
        return None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two equal-length vectors."""
    if len(a) != len(b) or not a:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


# Keep underscore alias for backward compatibility
_cosine_similarity = cosine_similarity


# ── VectorMemory ──────────────────────────────────────────────────────────────

class VectorMemory:
    """Persistent entity memory store with optional vector similarity search.

    Each entity is stored as a JSON file containing:
      - entity_id, entity_type, summary text
      - metadata dict (arbitrary key-value pairs)
      - embedding vector (float list, stored alongside the entity)
      - interaction log
      - created_at / updated_at timestamps
    """

    def __init__(self) -> None:
        VECTOR_MEMORY_DIR.mkdir(parents=True, exist_ok=True)
        self._index_path = VECTOR_MEMORY_DIR / "_vector_index.json"
        self._index_lock = threading.Lock()

    # ── Storage helpers ───────────────────────────────────────────────────────

    def _entity_path(self, entity_id: str) -> Path:
        safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in entity_id)
        return VECTOR_MEMORY_DIR / f"{safe}.json"

    def _load(self, entity_id: str) -> Optional[dict]:
        p = self._entity_path(entity_id)
        if p.exists():
            try:
                return json.loads(p.read_text())
            except Exception:
                return None
        return None

    def _save(self, entity: dict) -> None:
        entity["updated_at"] = _now_iso()
        self._entity_path(entity["entity_id"]).write_text(
            json.dumps(entity, indent=2)
        )
        self._update_index(entity)

    def _load_index(self) -> dict:
        if self._index_path.exists():
            try:
                return json.loads(self._index_path.read_text())
            except Exception:
                pass
        return {"entities": {}}

    def _update_index(self, entity: dict) -> None:
        with self._index_lock:
            index = self._load_index()
            eid = entity["entity_id"]
            index["entities"][eid] = {
                "entity_type": entity.get("entity_type", "unknown"),
                "updated_at": entity.get("updated_at", ""),
                "summary": (entity.get("summary", ""))[:120],
                "has_embedding": bool(entity.get("embedding")),
                "interaction_count": len(entity.get("interactions", [])),
            }
            self._index_path.write_text(json.dumps(index, indent=2))

    # ── Public API ────────────────────────────────────────────────────────────

    def upsert(
        self,
        entity_id: str,
        summary: str,
        *,
        entity_type: str = "lead",
        metadata: Optional[dict] = None,
        embed: bool = True,
    ) -> dict:
        """Store or update an entity with optional semantic embedding.

        Args:
            entity_id:   Unique identifier (e.g. "lead:acme-corp").
            summary:     Human-readable description used for embedding.
            entity_type: Category tag ("lead", "company", "contact", …).
            metadata:    Arbitrary key-value pairs attached to this entity.
            embed:       Whether to generate/update the embedding vector.

        Returns:
            The stored entity dict.
        """
        entity = self._load(entity_id) or {
            "entity_id": entity_id,
            "created_at": _now_iso(),
            "interactions": [],
        }
        entity["entity_type"] = entity_type
        entity["summary"] = summary
        entity["metadata"] = {**(entity.get("metadata") or {}), **(metadata or {})}

        if embed:
            client = _get_nim_client()
            if client and client.is_available():
                vec = client.embed_one(summary, input_type="passage")
                if vec:
                    entity["embedding"] = vec

        self._save(entity)
        logger.debug("vector_memory: upserted [%s]", entity_id)
        return entity

    def get(self, entity_id: str) -> Optional[dict]:
        """Return a stored entity or None if not found."""
        return self._load(entity_id)

    def search(
        self,
        query: str,
        *,
        top_k: int = 10,
        entity_type: Optional[str] = None,
        min_score: float = 0.0,
    ) -> list[dict]:
        """Find the most semantically similar entities to the query.

        Uses cosine similarity on NV-Embed-v2 vectors when available;
        falls back to keyword search across summaries and metadata.

        Args:
            query:        Natural language query.
            top_k:        Number of results to return.
            entity_type:  Filter by entity type.
            min_score:    Minimum similarity score (0–1) to include.

        Returns:
            List of dicts: {entity_id, score, entity_type, summary, metadata}
            Ordered by score descending.
        """
        index = self._load_index()
        candidates = list(index.get("entities", {}).keys())
        if entity_type:
            candidates = [
                eid for eid in candidates
                if index["entities"][eid].get("entity_type") == entity_type
            ]
        if not candidates:
            return []

        client = _get_nim_client()
        use_vectors = client and client.is_available()

        query_vec: list[float] = []
        if use_vectors:
            query_vec = client.embed_one(query, input_type="query")

        scored = []
        for eid in candidates:
            entity = self._load(eid)
            if not entity:
                continue

            if use_vectors and query_vec:
                evec = entity.get("embedding", [])
                if evec:
                    score = _cosine_similarity(query_vec, evec)
                else:
                    # No embedding yet — give keyword score
                    score = _keyword_score(query, entity)
            else:
                score = _keyword_score(query, entity)

            if score >= min_score:
                scored.append({
                    "entity_id": eid,
                    "score": round(score, 4),
                    "entity_type": entity.get("entity_type", "unknown"),
                    "summary": entity.get("summary", ""),
                    "metadata": entity.get("metadata", {}),
                })

        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:top_k]

    def find_duplicates(
        self,
        entity_id: str,
        *,
        threshold: float = VECTOR_SIMILARITY_THRESHOLD,
        top_k: int = 5,
    ) -> list[dict]:
        """Return entities likely to be duplicates of the given entity.

        Two entities are considered duplicates when their embedding cosine
        similarity exceeds `threshold`.  Falls back to exact-substring
        matching on the summary when vectors are unavailable.

        Args:
            entity_id:  Reference entity ID.
            threshold:  Cosine similarity threshold (default from env).
            top_k:      Max duplicates to return.

        Returns:
            List of {entity_id, score, summary} dicts, ordered by score.
        """
        entity = self._load(entity_id)
        if not entity:
            return []
        summary = entity.get("summary", "")
        results = self.search(
            summary,
            top_k=top_k + 1,  # +1 because the entity itself will score 1.0
            entity_type=entity.get("entity_type"),
            min_score=threshold,
        )
        # Exclude the entity itself
        return [r for r in results if r["entity_id"] != entity_id][:top_k]

    def record_interaction(
        self,
        entity_id: str,
        action: str,
        *,
        sentiment: str = "neutral",
        notes: str = "",
    ) -> None:
        """Append an interaction event to an entity's log.

        Args:
            entity_id: Target entity.
            action:    Short description (e.g. "Sent cold email", "Replied").
            sentiment: "positive" | "neutral" | "negative".
            notes:     Free-text notes.
        """
        entity = self._load(entity_id)
        if not entity:
            logger.warning("vector_memory: record_interaction — entity not found: %s", entity_id)
            return
        interactions = entity.setdefault("interactions", [])
        interactions.append({
            "action": action,
            "sentiment": sentiment,
            "notes": notes,
            "ts": _now_iso(),
        })
        # Keep last 200 interactions
        if len(interactions) > 200:
            entity["interactions"] = interactions[-200:]
        self._save(entity)

    def delete(self, entity_id: str) -> bool:
        """Delete an entity and remove it from the index. Returns True if deleted."""
        p = self._entity_path(entity_id)
        if p.exists():
            p.unlink()
            with self._index_lock:
                index = self._load_index()
                index["entities"].pop(entity_id, None)
                self._index_path.write_text(json.dumps(index, indent=2))
            return True
        return False

    def list_entities(self, entity_type: Optional[str] = None) -> list[str]:
        """Return all entity IDs, optionally filtered by type."""
        index = self._load_index()
        return [
            eid for eid, meta in index.get("entities", {}).items()
            if entity_type is None or meta.get("entity_type") == entity_type
        ]

    def rerank_results(
        self,
        query: str,
        results: list[dict],
        *,
        text_field: str = "summary",
        top_n: Optional[int] = None,
    ) -> list[dict]:
        """Re-rank a list of result dicts using NVIDIA NV-Rerank.

        Useful for refining vector search results with a cross-encoder model.

        Args:
            query:      The user query.
            results:    List of result dicts (must contain text_field).
            text_field: Key in each result dict to use as passage text.
            top_n:      Return only top N reranked results.

        Returns:
            Results re-ordered by rerank score (highest first).
            Original results unchanged if reranking unavailable.
        """
        client = _get_nim_client()
        if not client or not client.is_available():
            return results

        passages = [r.get(text_field, "") for r in results]
        ranked = client.rerank(query, passages, top_n=top_n)
        if not ranked:
            return results

        # Rebuild result list in ranked order
        reranked = []
        for rank_item in ranked:
            idx = rank_item["index"]
            if idx < len(results):
                entry = dict(results[idx])
                entry["rerank_score"] = rank_item["score"]
                reranked.append(entry)
        return reranked


# ── Keyword fallback ──────────────────────────────────────────────────────────

def _keyword_score(query: str, entity: dict) -> float:
    """Simple keyword overlap score (0–1) as a vector search fallback."""
    keywords = set(query.lower().split())
    if not keywords:
        return 0.0

    text_parts = [
        entity.get("summary", ""),
        entity.get("entity_id", ""),
        json.dumps(entity.get("metadata", {})),
    ]
    text = " ".join(text_parts).lower()
    matches = sum(1 for kw in keywords if kw in text)
    return matches / len(keywords)
