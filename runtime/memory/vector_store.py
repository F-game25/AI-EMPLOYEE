"""Long-Term Vector Store — semantic memory with similarity search.

Persists embeddings and associated payloads to disk and supports fast
nearest-neighbour retrieval using cosine similarity.

Usage::

    from memory.vector_store import get_vector_store

    vs = get_vector_store()
    vs.store("how_to_write_email", "Write concise subject lines and clear CTAs",
             metadata={"source": "email_ninja", "memory_type": "semantic"})
    results = vs.search("email marketing tips", top_k=5)
    entry   = vs.retrieve("how_to_write_email")

Memory types
------------
- ``semantic``    — factual knowledge / best practices
- ``episodic``    — specific task events with outcome
- ``procedural``  — learned how-to steps / skills

Storage
-------
Each entry is a JSON object:
  {
    "key":        str,
    "text":       str,
    "embedding":  list[float],   # 32-dim normalised hash vector
    "metadata":   dict,
    "importance": float,         # 0–1
    "access_count": int,
    "created_at": str,
    "last_accessed": str,
  }
"""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any

from core.memory_index import embed_text, cosine_similarity, clamp

_LOCK = threading.RLock()
_MAX_ENTRIES = int(os.environ.get("AI_EMPLOYEE_VECTOR_STORE_MAX", "10000"))


def _default_path() -> Path:
    home = os.getenv("AI_HOME")
    base = Path(home) if home else Path(__file__).resolve().parents[2]
    path = base / "state" / "vector_store.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _ts() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


class VectorStore:
    """File-backed long-term semantic memory with vector similarity search."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or _default_path()
        self._entries: dict[str, dict[str, Any]] = {}
        self._load()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load(self) -> None:
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            if isinstance(raw, list):
                self._entries = {e["key"]: e for e in raw if isinstance(e, dict) and "key" in e}
            elif isinstance(raw, dict) and "entries" in raw:
                entries = raw["entries"]
                if isinstance(entries, list):
                    self._entries = {
                        e["key"]: e for e in entries if isinstance(e, dict) and "key" in e
                    }
        except Exception:
            self._entries = {}
            self._save()

    def _save(self) -> None:
        payload = {
            "updated_at": _ts(),
            "count": len(self._entries),
            "entries": list(self._entries.values()),
        }
        self._path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def store(
        self,
        key: str,
        text: str,
        *,
        metadata: dict[str, Any] | None = None,
        importance: float = 0.5,
        overwrite: bool = True,
    ) -> dict[str, Any]:
        """Store a text entry with its embedding.

        Args:
            key:        Unique identifier (e.g. ``"email_tip_001"``).
            text:       The text to store and embed.
            metadata:   Optional dict (source, memory_type, agent, …).
            importance: 0–1 relevance weight; higher = retrieved more often.
            overwrite:  When False and *key* already exists, the call is a no-op.

        Returns:
            The stored entry dict.
        """
        with _LOCK:
            if not overwrite and key in self._entries:
                return dict(self._entries[key])

            entry: dict[str, Any] = {
                "key": key,
                "text": (text or "")[:2000],
                "embedding": embed_text(text),
                "metadata": metadata or {},
                "importance": clamp(float(importance)),
                "access_count": 0,
                "created_at": self._entries.get(key, {}).get("created_at", _ts()),
                "last_accessed": _ts(),
            }
            self._entries[key] = entry

            # Evict least-important entries when limit is reached
            if len(self._entries) > _MAX_ENTRIES:
                evict_key = min(
                    self._entries,
                    key=lambda k: (
                        self._entries[k].get("importance", 0.0),
                        self._entries[k].get("access_count", 0),
                    ),
                )
                del self._entries[evict_key]

            self._save()
            return dict(entry)

    def delete(self, key: str) -> bool:
        """Remove an entry. Returns True if the key existed."""
        with _LOCK:
            existed = key in self._entries
            self._entries.pop(key, None)
            if existed:
                self._save()
            return existed

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def retrieve(self, key: str) -> dict[str, Any] | None:
        """Return the entry for *key*, or None if not found."""
        with _LOCK:
            entry = self._entries.get(key)
            if entry:
                entry["access_count"] = int(entry.get("access_count", 0)) + 1
                entry["last_accessed"] = _ts()
            return dict(entry) if entry else None

    def search(
        self,
        query: str,
        *,
        top_k: int = 5,
        memory_type: str | None = None,
        min_importance: float = 0.0,
    ) -> list[dict[str, Any]]:
        """Return the *top_k* entries most similar to *query*.

        Args:
            query:         Free-text query.
            top_k:         Maximum number of results.
            memory_type:   Filter by ``metadata.memory_type``
                           (e.g. ``"semantic"``, ``"episodic"``, ``"procedural"``).
            min_importance: Only return entries with importance ≥ this value.

        Returns:
            List of entry dicts sorted by relevance score (highest first).
            Each entry gets a transient ``_score`` key added.
        """
        with _LOCK:
            q_emb = embed_text(query)
            q_tokens = set(query.lower().split())
            scored: list[dict[str, Any]] = []

            for entry in self._entries.values():
                if float(entry.get("importance", 0.0)) < min_importance:
                    continue
                mt = entry.get("metadata", {}).get("memory_type")
                if memory_type and mt and mt != memory_type:
                    continue

                sim = cosine_similarity(q_emb, entry.get("embedding") or [])
                text = entry.get("text", "").lower()
                keyword = 1.0 if any(t in text for t in q_tokens if len(t) > 2) else 0.0
                score = sim * 0.7 + keyword * 0.2 + float(entry.get("importance", 0.0)) * 0.1
                scored.append({**entry, "_score": round(score, 4)})

            results = sorted(scored, key=lambda x: x.get("_score", 0.0), reverse=True)[:top_k]
            # Update access stats for returned entries
            for r in results:
                k = r.get("key")
                if k and k in self._entries:
                    self._entries[k]["access_count"] = int(
                        self._entries[k].get("access_count", 0)
                    ) + 1
                    self._entries[k]["last_accessed"] = _ts()
            return results

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def count(self, *, memory_type: str | None = None) -> int:
        """Return number of stored entries, optionally filtered by type."""
        with _LOCK:
            if not memory_type:
                return len(self._entries)
            return sum(
                1
                for e in self._entries.values()
                if e.get("metadata", {}).get("memory_type") == memory_type
            )

    def snapshot(self, *, limit: int = 100) -> list[dict[str, Any]]:
        """Return up to *limit* entries ordered by last-accessed time."""
        with _LOCK:
            all_entries = sorted(
                self._entries.values(),
                key=lambda e: e.get("last_accessed", ""),
                reverse=True,
            )
            return [dict(e) for e in all_entries[:limit]]


# ── Singleton ─────────────────────────────────────────────────────────────────

_instance: VectorStore | None = None
_instance_lock = threading.Lock()


def get_vector_store() -> VectorStore:
    """Return the process-wide VectorStore singleton."""
    global _instance
    with _instance_lock:
        if _instance is None:
            _instance = VectorStore()
    return _instance
