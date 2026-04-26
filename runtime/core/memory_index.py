"""Memory ranking and retrieval index for context-aware planning."""
from __future__ import annotations

import json
import math
import os
import threading
import time
from pathlib import Path
from typing import Any

_DECAY_PER_DAY = 0.995
_lock = threading.RLock()

# ── Embedding backend ─────────────────────────────────────────────────────────
# When sentence-transformers is installed, use the all-MiniLM-L6-v2 model
# (384-dim real semantic embeddings, ~80 MB, CPU-friendly, offline).
# Falls back to the 32-dim hash-vote approach when not available.
# Install: pip install sentence-transformers
_ST_MODEL_NAME = "all-MiniLM-L6-v2"
_st_model = None
_st_lock = threading.Lock()

def _get_st_model():
    global _st_model
    if _st_model is not None:
        return _st_model
    with _st_lock:
        if _st_model is not None:
            return _st_model
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore
            _st_model = SentenceTransformer(_ST_MODEL_NAME)
        except Exception:
            _st_model = False  # explicitly mark unavailable
    return _st_model


def _embedding_dim() -> int:
    model = _get_st_model()
    return 384 if model else 32


def _hash_embed(text: str, dim: int = 32) -> list[float]:
    vec = [0.0] * dim
    tokens = [t for t in (text or "").lower().split() if t]
    if not tokens:
        return vec
    for tok in tokens:
        slot = abs(hash(tok)) % dim
        vec[slot] += 1.0
    return _normalize(vec)


_DIM = 32  # kept for backward-compat imports; use _embedding_dim() at runtime


def _state_path() -> Path:
    home = os.getenv("AI_HOME")
    base = Path(home) if home else Path(__file__).resolve().parents[2]
    path = base / "state" / "memory_index.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _ts() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, float(value)))


def _parse_iso(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return time.mktime(time.strptime(value, "%Y-%m-%dT%H:%M:%SZ"))
    except Exception:
        return None


def _normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def embed_text(text: str) -> list[float]:
    model = _get_st_model()
    if model:
        try:
            return model.encode(text or "", normalize_embeddings=True).tolist()
        except Exception:
            pass
    return _hash_embed(text or "", dim=32)


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 0.0
    n = min(len(a), len(b))
    return max(0.0, min(1.0, sum(a[i] * b[i] for i in range(n))))


def recency_score(last_used: str | None) -> float:
    ts = _parse_iso(last_used)
    if ts is None:
        return 0.0
    age_days = max(0.0, (time.time() - ts) / 86400.0)
    return float(math.exp(-age_days / 7.0))


class MemoryIndex:
    def __init__(self, path: Path | None = None) -> None:
        self._path = path or _state_path()
        self._memories: list[dict[str, Any]] = []
        self._memories = self._load()

    def _load(self) -> list[dict[str, Any]]:
        memories: list[dict[str, Any]] = []
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
            if isinstance(payload, list):
                memories = payload
            elif isinstance(payload, dict) and isinstance(payload.get("memories"), list):
                memories = payload["memories"]
        except Exception:
            pass
        # Re-embed any entries whose vector dimensionality doesn't match current embedder
        target_dim = _embedding_dim()
        needs_save = False
        for mem in memories:
            emb = mem.get("embedding") or []
            if len(emb) != target_dim and mem.get("text"):
                mem["embedding"] = embed_text(mem["text"])
                needs_save = True
        if needs_save:
            self._memories = memories
            self._save()
        return memories

    def _save(self) -> None:
        payload = {"updated_at": _ts(), "memories": self._memories}
        self._path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def snapshot(self) -> list[dict[str, Any]]:
        with _lock:
            return json.loads(json.dumps(self._memories))

    def add_memory(self, text: str, *, importance: float = 0.5, embedding: list[float] | None = None) -> dict[str, Any]:
        with _lock:
            item = {
                "id": f"m-{abs(hash((text, _ts()))) % 10_000_000}",
                "text": text,
                "embedding": embedding or embed_text(text),
                "importance": clamp(importance),
                "usage_count": 0,
                "last_used": _ts(),
            }
            self._memories.append(item)
            self._save()
            return dict(item)

    @staticmethod
    def rank_memory(memory: dict[str, Any], query_embedding: list[float]) -> float:
        similarity = cosine_similarity(memory.get("embedding") or [], query_embedding)
        return (
            (similarity * 0.6)
            + (float(memory.get("importance", 0.0)) * 0.3)
            + (recency_score(memory.get("last_used")) * 0.1)
        )

    def get_relevant_memories(self, query: str, *, top_k: int = 5, touch: bool = True) -> list[dict[str, Any]]:
        query_embedding = embed_text(query)
        with _lock:
            ranked = sorted(
                self._memories,
                key=lambda m: self.rank_memory(m, query_embedding),
                reverse=True,
            )[: max(top_k, 1)]
            if touch:
                now = _ts()
                for mem in ranked:
                    mem["usage_count"] = int(mem.get("usage_count", 0)) + 1
                    mem["last_used"] = now
                if ranked:
                    self._save()
            return [dict(m) for m in ranked]

    def apply_feedback(self, memories: list[dict[str, Any]], reward: float) -> None:
        if not memories:
            return
        memory_ids = {m.get("id") for m in memories if m.get("id")}
        if not memory_ids:
            return
        with _lock:
            for mem in self._memories:
                if mem.get("id") in memory_ids:
                    mem["importance"] = clamp(float(mem.get("importance", 0.0)) + (float(reward) * 0.1))
            self._save()

    def apply_decay(self) -> None:
        with _lock:
            changed = False
            now_ts = time.time()
            for mem in self._memories:
                last_used = _parse_iso(mem.get("last_used"))
                if last_used is None:
                    continue
                days = max(0.0, (now_ts - last_used) / 86400.0)
                if days <= 0:
                    continue
                factor = _DECAY_PER_DAY ** days
                mem["importance"] = clamp(float(mem.get("importance", 0.0)) * factor)
                changed = True
            if changed:
                self._save()


_instance: MemoryIndex | None = None
_instance_lock = threading.Lock()


def get_memory_index(path: Path | None = None) -> MemoryIndex:
    global _instance
    with _instance_lock:
        if _instance is None:
            _instance = MemoryIndex(path)
        elif path is not None and _instance._path != path:
            _instance = MemoryIndex(path)
    return _instance
