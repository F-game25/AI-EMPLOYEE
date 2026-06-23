"""File-backed canonical memory store."""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any

from core.state_paths import canonical_state_dir
from memory.schema import MemoryRecord, SCHEMA_VERSION, utc_now


_LOCK = threading.RLock()


def _default_path() -> Path:
    root = canonical_state_dir() / "memory"
    root.mkdir(parents=True, exist_ok=True)
    return root / "unified_memory.json"


def _safe_path(path: Path | None = None) -> Path:
    candidate = (path or _default_path()).resolve()
    state_root = canonical_state_dir().resolve()
    try:
        candidate.relative_to(state_root)
    except ValueError:
        if path is not None and os.getenv("PYTEST_CURRENT_TEST"):
            candidate.parent.mkdir(parents=True, exist_ok=True)
            return candidate
        raise ValueError("unified memory path must live under STATE_DIR")
    candidate.parent.mkdir(parents=True, exist_ok=True)
    return candidate


class UnifiedMemoryStore:
    """Durable JSON store for canonical memory records."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = _safe_path(path)
        self._records: dict[str, MemoryRecord] = {}
        self._load()

    @property
    def path(self) -> Path:
        return self._path

    def _load(self) -> None:
        with _LOCK:
            try:
                raw = json.loads(self._path.read_text(encoding="utf-8"))
            except Exception:
                self._records = {}
                self._save()
                return

            if isinstance(raw, list):
                rows = raw
            elif isinstance(raw, dict):
                rows = raw.get("records") or raw.get("entries") or []
            else:
                rows = []

            records: dict[str, MemoryRecord] = {}
            for row in rows:
                if not isinstance(row, dict):
                    continue
                record = MemoryRecord.from_dict(row)
                records[record.id] = record
            self._records = records

    def _save(self) -> None:
        payload = {
            "schema_version": SCHEMA_VERSION,
            "updated_at": utc_now(),
            "count": len(self._records),
            "records": [r.to_dict() for r in self._records.values()],
        }
        # Ensure the parent exists at write time, not only at __init__: the process-wide
        # store can outlive the directory it was bound to (e.g. a test tmp state dir torn
        # down after the singleton cached its path), so re-create defensively before writing.
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def upsert(self, record: MemoryRecord | dict[str, Any]) -> MemoryRecord:
        with _LOCK:
            current = record if isinstance(record, MemoryRecord) else MemoryRecord.from_dict(record)
            existing = self._records.get(current.id)
            if existing is not None and current.created_at == current.updated_at:
                current.created_at = existing.created_at
            current.updated_at = utc_now()
            self._records[current.id] = current
            self._save()
            return MemoryRecord.from_dict(current.to_dict())

    def get(self, memory_id: str, *, touch: bool = True) -> MemoryRecord | None:
        with _LOCK:
            record = self._records.get(str(memory_id))
            if record is None:
                return None
            if touch:
                record.touch()
                self._save()
            return MemoryRecord.from_dict(record.to_dict())

    def delete(self, memory_id: str) -> bool:
        with _LOCK:
            existed = str(memory_id) in self._records
            self._records.pop(str(memory_id), None)
            if existed:
                self._save()
            return existed

    def count(self, **filters: Any) -> int:
        return len(self.search(limit=10**9, touch=False, **filters))

    def list_recent(self, *, limit: int = 50, tenant_id: str | None = None) -> list[MemoryRecord]:
        with _LOCK:
            rows = list(self._records.values())
            if tenant_id:
                rows = [r for r in rows if r.tenant_id == tenant_id]
            rows.sort(key=lambda r: r.updated_at or r.created_at, reverse=True)
            return [MemoryRecord.from_dict(r.to_dict()) for r in rows[:limit]]

    def search(
        self,
        *,
        query: str = "",
        tenant_id: str | None = None,
        memory_type: str | None = None,
        scope: str | None = None,
        project_id: str | None = None,
        session_id: str | None = None,
        agent: str | None = None,
        tags: list[str] | None = None,
        limit: int = 20,
        touch: bool = True,
    ) -> list[MemoryRecord]:
        query_tokens = {t for t in query.lower().split() if len(t) > 2}
        wanted_tags = {str(t).lower() for t in (tags or [])}
        scored: list[tuple[float, MemoryRecord]] = []

        with _LOCK:
            for record in self._records.values():
                if tenant_id and record.tenant_id != tenant_id:
                    continue
                if memory_type and record.memory_type != memory_type:
                    continue
                if scope and record.scope != scope:
                    continue
                if project_id and record.project_id != project_id:
                    continue
                if session_id and record.session_id != session_id:
                    continue
                if agent and record.agent != agent:
                    continue
                if wanted_tags and not wanted_tags.intersection(set(record.tags)):
                    continue

                score = self._score(record, query_tokens, project_id=project_id, session_id=session_id, wanted_tags=wanted_tags)
                if query_tokens and score <= 0:
                    continue
                scored.append((score, record))

            scored.sort(key=lambda item: item[0], reverse=True)
            results = [record for _, record in scored[:limit]]
            if touch and results:
                for record in results:
                    record.touch()
                self._save()
            return [MemoryRecord.from_dict(r.to_dict()) for r in results]

    def apply_feedback(self, memory_id: str, reward: float) -> MemoryRecord | None:
        with _LOCK:
            record = self._records.get(str(memory_id))
            if record is None:
                return None
            record.feedback_score += float(reward)
            record.importance = max(0.0, min(1.0, record.importance + (0.05 * float(reward))))
            record.updated_at = utc_now()
            self._save()
            return MemoryRecord.from_dict(record.to_dict())

    @staticmethod
    def _score(
        record: MemoryRecord,
        query_tokens: set[str],
        *,
        project_id: str | None,
        session_id: str | None,
        wanted_tags: set[str],
    ) -> float:
        score = record.importance * 0.2 + record.confidence * 0.1
        haystack = " ".join([
            record.text,
            record.summary or "",
            record.topic or "",
            " ".join(record.tags),
            record.source,
            record.agent or "",
        ]).lower()
        if query_tokens:
            hits = sum(1 for token in query_tokens if token in haystack)
            score += hits / max(len(query_tokens), 1)
        if project_id and record.project_id == project_id:
            score += 0.25
        if session_id and record.session_id == session_id:
            score += 0.25
        if wanted_tags:
            score += 0.15 * len(wanted_tags.intersection(set(record.tags)))
        if record.verified:
            score += 0.05
        score += min(0.2, max(-0.2, record.feedback_score * 0.05))
        return round(score, 6)

    def snapshot(self, *, limit: int = 100) -> list[dict[str, Any]]:
        return [r.to_dict() for r in self.list_recent(limit=limit)]


_instance: UnifiedMemoryStore | None = None
_instance_lock = threading.Lock()


def get_unified_memory_store() -> UnifiedMemoryStore:
    global _instance
    with _instance_lock:
        if _instance is None:
            _instance = UnifiedMemoryStore()
    return _instance
