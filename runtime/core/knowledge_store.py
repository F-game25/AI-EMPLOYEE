"""Persistent topic/context memory used by planning and routing."""
from __future__ import annotations

import json
import os
import re
import threading
import time
from pathlib import Path
from typing import Any


_DEFAULT_STORE = {
    "topics": {
        "ecommerce": [],
        "marketing": [],
        "lead_generation": [],
    },
    "insights": [],
    "strategies": [],
    "user_profile": {
        "goals": [],
        "business_type": "",
        "preferences": [],
        "updated_at": None,
    },
}
_MAX_PROFILE_ITEMS = 30


class KnowledgeStore:
    def __init__(self, path: Path | None = None) -> None:
        self._path = path or self._default_path()
        self._lock = threading.RLock()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._unified = self._init_unified_store(path)
        self._state = self._load()

    def _init_unified_store(self, path: Path | None) -> Any:
        try:
            from memory.unified_store import UnifiedMemoryStore
            if path is not None:
                return UnifiedMemoryStore(path=path.parent / "memory" / "unified_memory.json")
            return UnifiedMemoryStore()
        except Exception:
            return None

    @staticmethod
    def _default_path() -> Path:
        from core.state_paths import tenant_state_dir
        return tenant_state_dir() / "knowledge_store.json"

    @staticmethod
    def _ts() -> str:
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    def _load(self) -> dict[str, Any]:
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                return dict(_DEFAULT_STORE)
            merged = dict(_DEFAULT_STORE)
            merged.update(payload)
            merged["topics"] = dict(_DEFAULT_STORE["topics"]) | dict(merged.get("topics", {}))
            merged["user_profile"] = dict(_DEFAULT_STORE["user_profile"]) | dict(merged.get("user_profile", {}))
            return merged
        except Exception:
            self._write(dict(_DEFAULT_STORE))
            return dict(_DEFAULT_STORE)

    def _write(self, payload: dict[str, Any]) -> None:
        self._path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def save(self) -> dict[str, Any]:
        with self._lock:
            self._write(self._state)
            return self.snapshot()

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return json.loads(json.dumps(self._state))

    def add_knowledge(self, topic: str, content: Any) -> dict[str, Any]:
        topic_key = (topic or "general").strip().lower()
        with self._lock:
            topics = self._state.setdefault("topics", {})
            topic_items = topics.setdefault(topic_key, [])
            topic_items.append({
                "content": content,
                "stored_at": self._ts(),
            })
            record_id = f"ks:topic:{topic_key}:{len(topic_items)}"
            self._state.setdefault("insights", []).append(
                {"id": record_id, "topic": topic_key, "content": content, "stored_at": self._ts()}
            )
            self._write(self._state)
            self._store_unified_record(
                record_id,
                title=topic_key,
                content=content,
                source="knowledge_store",
                tags=[topic_key],
                memory_type="knowledge_graph",
                metadata={"topic": topic_key, "origin_store": "knowledge_store"},
            )
            return {"topic": topic_key, "entries": len(topic_items)}

    def _store_unified_record(
        self,
        record_id: str,
        *,
        title: str,
        content: Any,
        source: str,
        tags: list[str] | None = None,
        memory_type: str = "knowledge_graph",
        importance: float = 0.5,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if self._unified is None:
            return
        try:
            from memory.schema import MemoryRecord
            text = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False, default=str)
            if title:
                text = f"{title}\n\n{text}".strip()
            record = MemoryRecord.create(
                text,
                id=record_id,
                memory_type=memory_type,
                source=source,
                topic=title or None,
                tags=tags or [],
                importance=importance,
                metadata={
                    **(metadata or {}),
                    "origin_store": (metadata or {}).get("origin_store", "knowledge_store"),
                },
            )
            self._unified.upsert(record)
        except Exception:
            return

    def search_knowledge(self, query: str) -> list[dict[str, Any]]:
        q = (query or "").strip().lower()
        if not q:
            return []
        with self._lock:
            hits: list[dict[str, Any]] = []
            for topic, entries in self._state.get("topics", {}).items():
                for item in entries:
                    blob = json.dumps(item, ensure_ascii=False).lower()
                    if q in topic or q in blob:
                        hits.append({"topic": topic, **item})
            for item in self._state.get("insights", []):
                blob = json.dumps(item, ensure_ascii=False).lower()
                if q in blob:
                    hits.append(item)
            hits.extend(self._search_unified_knowledge(q))
            return hits[:20]

    def _search_unified_knowledge(self, query: str, *, limit: int = 10) -> list[dict[str, Any]]:
        if self._unified is None:
            return []
        try:
            records = self._unified.search(query=query, memory_type="knowledge_graph", limit=limit)
        except Exception:
            return []
        hits: list[dict[str, Any]] = []
        for record in records:
            hits.append({
                "id": record.id,
                "topic": record.topic or record.metadata.get("topic", ""),
                "content": record.text,
                "source": record.source or record.metadata.get("source", "knowledge_store"),
                "tags": record.tags,
                "stored_at": record.created_at,
                "_source": "unified_memory",
            })
        return hits

    def get_relevant_context(self, task: str) -> str:
        task_text = (task or "").strip().lower()
        if not task_text:
            return ""
        with self._lock:
            relevant: list[str] = []
            for topic, entries in self._state.get("topics", {}).items():
                if topic in task_text:
                    for item in entries[-3:]:
                        relevant.append(f"[{topic}] {item.get('content')}")
            for item in self._state.get("insights", [])[-20:]:
                blob = json.dumps(item, ensure_ascii=False).lower()
                if any(token in blob for token in task_text.split()[:8]):
                    relevant.append(str(item.get("content", "")))
            for item in self._search_unified_knowledge(task_text, limit=5):
                content = str(item.get("content", ""))
                if content and content not in relevant:
                    relevant.append(content)
            return "\n".join(relevant[:8])

    def update_user_profile(
        self,
        *,
        goals: list[str] | None = None,
        business_type: str | None = None,
        preferences: list[str] | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            profile = self._state.setdefault("user_profile", dict(_DEFAULT_STORE["user_profile"]))
            if goals:
                profile["goals"] = list(dict.fromkeys([*(profile.get("goals", [])), *goals]))[-_MAX_PROFILE_ITEMS:]
            if business_type:
                profile["business_type"] = business_type
            if preferences:
                profile["preferences"] = list(dict.fromkeys([*(profile.get("preferences", [])), *preferences]))[-_MAX_PROFILE_ITEMS:]
            profile["updated_at"] = self._ts()
            self._write(self._state)
            return dict(profile)

    def learn_from_conversation(self, text: str) -> dict[str, Any]:
        msg = (text or "").strip()
        if not msg:
            return {}
        lower = msg.lower()
        goals = []
        prefs = []
        business_type = ""

        if any(k in lower for k in ("goal", "need", "want", "plan", "strategy")):
            goals.append(msg[:160])
        match = re.search(r"(?:business|company|store|brand)\s*(?:is|type|:)\s*([\w\-\s&]+)", lower)
        if match:
            business_type = match.group(1).strip()[:80]
        for key in ("budget", "tone", "audience", "industry", "market", "timeline"):
            if key in lower:
                prefs.append(f"{key}:{msg[:120]}")

        return self.update_user_profile(goals=goals, business_type=business_type or None, preferences=prefs)


    def hybrid_search(
        self,
        query: str,
        *,
        top_k: int = 10,
        alpha: float = 0.7,
    ) -> list[dict[str, Any]]:
        """Hybrid semantic + keyword search over embedded knowledge entries.

        Args:
            query:  Free-text query.
            top_k:  Maximum results.
            alpha:  Weight for vector score (0.0 = pure BM25/keyword, 1.0 = pure vector).

        Returns:
            List of result dicts with guaranteed ``source`` and ``score`` fields.
        """
        try:
            from memory.vector_store import get_vector_store
        except ImportError:
            return self._keyword_fallback(query, top_k=top_k)

        vs = get_vector_store()
        raw = json.loads(self._path.read_text(encoding="utf-8"))
        entries_map = {
            f"ks:{e.get('id') or e.get('title','').replace(' ','_').lower()[:40]}": e
            for e in raw.get("entries", [])
            if e.get("id") or e.get("title")
        }

        # Vector / hybrid search via vector store
        vs_results = vs.search(query, top_k=top_k)

        results: list[dict[str, Any]] = []
        q_tokens = set(query.lower().split())
        for r in vs_results:
            key = r.get("key", "")
            original = entries_map.get(key, {})
            text = r.get("text", "").lower()
            kw_score = 1.0 if any(t in text for t in q_tokens if len(t) > 2) else 0.0
            vec_score = float(r.get("_score", 0.0))
            blended = vec_score * alpha + kw_score * (1.0 - alpha)
            results.append({
                "id":      original.get("id") or key.replace("ks:", ""),
                "title":   original.get("title") or r.get("text", "")[:60],
                "content": original.get("content") or r.get("text", ""),
                "source":  original.get("source") or r.get("metadata", {}).get("source") or "knowledge_store",
                "tags":    original.get("tags") or r.get("metadata", {}).get("tags") or [],
                "score":   round(blended, 4),
            })

        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_k]

    def _keyword_fallback(self, query: str, top_k: int = 10) -> list[dict[str, Any]]:
        """BM25-style keyword fallback when vector store is unavailable."""
        hits = self.search_knowledge(query)[:top_k]
        return [
            {
                "id":      h.get("id", ""),
                "title":   h.get("topic", ""),
                "content": str(h.get("content", "")),
                "source":  h.get("source", "knowledge_store"),
                "tags":    h.get("tags", []),
                "score":   0.5,
            }
            for h in hits
        ]

    def embed_entries_to_vector_store(self) -> int:
        """Embed the `entries` array from the JSON file into the vector store.

        Runs at startup and whenever new entries are added. Idempotent —
        skips entries already indexed (keyed by 'ks:<id>'). Returns the
        number of newly embedded entries.
        """
        try:
            from memory.vector_store import get_vector_store
        except ImportError:
            return 0

        vs = get_vector_store()
        raw = json.loads(self._path.read_text(encoding="utf-8"))
        entries = raw.get("entries", [])
        if not entries:
            return 0

        embedded = 0
        for e in entries:
            eid = e.get("id") or e.get("title", "").replace(" ", "_").lower()[:40]
            if not eid:
                continue
            key = f"ks:{eid}"
            title = e.get("title", eid)
            content = e.get("content", "")
            text = f"{title}\n\n{content}".strip()
            if not text:
                continue
            try:
                # overwrite=False → no-op if key already exists; detect by
                # checking presence before calling store.
                if vs.retrieve(key) is not None:
                    continue  # already indexed
                vs.store(
                    key,
                    text,
                    metadata={
                        "source": e.get("source", "knowledge_store"),
                        "tags": e.get("tags", []),
                        "created_at": e.get("created_at", ""),
                        "memory_type": "knowledge_graph",
                    },
                    importance=e.get("importance", 0.5),
                    overwrite=False,
                )
                self._store_unified_record(
                    key,
                    title=title,
                    content=content,
                    source=e.get("source", "knowledge_store"),
                    tags=e.get("tags", []),
                    memory_type="knowledge_graph",
                    importance=e.get("importance", 0.5),
                    metadata={
                        "entry_id": eid,
                        "created_at": e.get("created_at", ""),
                        "origin_store": "knowledge_store.entries",
                    },
                )
                embedded += 1
            except Exception:
                pass
        return embedded


from core.tenant_singleton import TenantSingletonPool

_pool: TenantSingletonPool[KnowledgeStore] = TenantSingletonPool(KnowledgeStore)


def get_knowledge_store(path: Path | None = None) -> KnowledgeStore:
    """Return the KnowledgeStore for the active tenant (per-tenant isolated; one
    shared ``__global__`` instance in local/default mode). An explicit ``path``
    pins a fresh instance for the active tenant (tests / reconfiguration)."""
    if path is not None:
        inst = _pool.get()
        if inst._path != path:
            inst = KnowledgeStore(path)
            _pool.set(inst)
        return inst
    return _pool.get()
