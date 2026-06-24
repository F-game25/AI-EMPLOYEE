"""Canonical memory record schema.

This module defines the durable envelope every memory subsystem can share.
It is intentionally dependency-light so agents, routes, migration scripts, and
tests can validate records without importing the full runtime.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any
import uuid


SCHEMA_VERSION = 1

MEMORY_TYPES = {
    "semantic",
    "episodic",
    "procedural",
    "outcome",
    "preference",
    "decision",
    "failure",
    "research",
    "money",
    "forge",
    "task",
    # Existing MemoryManager names kept for compatibility during migration.
    "session",
    "long_term",
    "knowledge_graph",
    "company",
    "skill",
    "financial",
    "tool_history",
    "project",
    "event_timeline",
    "structured_db",
}

SCOPES = {"system", "tenant", "user", "project", "agent", "session", "company", "task"}
VISIBILITIES = {"private", "internal", "shared", "public"}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def clamp01(value: Any, default: float = 0.5) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = default
    return max(0.0, min(1.0, number))


def normalize_memory_type(value: str | None) -> str:
    memory_type = str(value or "semantic").strip().lower()
    return memory_type if memory_type in MEMORY_TYPES else "semantic"


def normalize_scope(value: str | None, *, project_id: str | None = None, session_id: str | None = None, agent: str | None = None) -> str:
    scope = str(value or "").strip().lower()
    if scope in SCOPES:
        return scope
    if project_id:
        return "project"
    if session_id:
        return "session"
    if agent:
        return "agent"
    return "tenant"


def normalize_visibility(value: str | None) -> str:
    visibility = str(value or "private").strip().lower()
    return visibility if visibility in VISIBILITIES else "private"


def normalize_tags(value: Any) -> list[str]:
    if value is None:
        return []
    raw = value if isinstance(value, list) else [value]
    tags: list[str] = []
    for item in raw:
        tag = str(item or "").strip().lower()
        if tag and tag not in tags:
            tags.append(tag[:80])
    return tags


@dataclass(slots=True)
class MemoryRecord:
    id: str
    tenant_id: str
    text: str
    memory_type: str = "semantic"
    scope: str = "tenant"
    user_id: str | None = None
    summary: str | None = None
    topic: str | None = None
    tags: list[str] = field(default_factory=list)
    source: str = ""
    agent: str | None = None
    project_id: str | None = None
    session_id: str | None = None
    task_id: str | None = None
    confidence: float = 0.5
    importance: float = 0.5
    verified: bool = False
    sensitive: bool = False
    visibility: str = "private"
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    last_accessed: str | None = None
    access_count: int = 0
    feedback_score: float = 0.0
    schema_version: int = SCHEMA_VERSION

    @classmethod
    def create(
        cls,
        text: str,
        *,
        id: str | None = None,
        tenant_id: str = "default",
        memory_type: str = "semantic",
        scope: str | None = None,
        user_id: str | None = None,
        summary: str | None = None,
        topic: str | None = None,
        tags: Any = None,
        source: str = "",
        agent: str | None = None,
        project_id: str | None = None,
        session_id: str | None = None,
        task_id: str | None = None,
        confidence: float = 0.5,
        importance: float = 0.5,
        verified: bool = False,
        sensitive: bool = False,
        visibility: str = "private",
        metadata: dict[str, Any] | None = None,
    ) -> "MemoryRecord":
        now = utc_now()
        normalized_type = normalize_memory_type(memory_type)
        return cls(
            id=str(id or uuid.uuid4()),
            tenant_id=str(tenant_id or "default"),
            user_id=user_id,
            scope=normalize_scope(scope, project_id=project_id, session_id=session_id, agent=agent),
            memory_type=normalized_type,
            text=str(text or "")[:10000],
            summary=(summary or None),
            topic=(topic or None),
            tags=normalize_tags(tags),
            source=str(source or ""),
            agent=agent,
            project_id=project_id,
            session_id=session_id,
            task_id=task_id,
            confidence=clamp01(confidence),
            importance=clamp01(importance),
            verified=bool(verified),
            sensitive=bool(sensitive),
            visibility=normalize_visibility(visibility),
            metadata=dict(metadata or {}),
            created_at=now,
            updated_at=now,
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MemoryRecord":
        created_at = str(data.get("created_at") or utc_now())
        updated_at = str(data.get("updated_at") or created_at)
        return cls(
            id=str(data.get("id") or uuid.uuid4()),
            tenant_id=str(data.get("tenant_id") or "default"),
            user_id=data.get("user_id"),
            scope=normalize_scope(
                data.get("scope"),
                project_id=data.get("project_id"),
                session_id=data.get("session_id"),
                agent=data.get("agent"),
            ),
            memory_type=normalize_memory_type(data.get("memory_type")),
            text=str(data.get("text") or "")[:10000],
            summary=data.get("summary"),
            topic=data.get("topic"),
            tags=normalize_tags(data.get("tags")),
            source=str(data.get("source") or ""),
            agent=data.get("agent"),
            project_id=data.get("project_id"),
            session_id=data.get("session_id"),
            task_id=data.get("task_id"),
            confidence=clamp01(data.get("confidence"), 0.5),
            importance=clamp01(data.get("importance"), 0.5),
            verified=bool(data.get("verified", False)),
            sensitive=bool(data.get("sensitive", False)),
            visibility=normalize_visibility(data.get("visibility")),
            metadata=dict(data.get("metadata") or {}),
            created_at=created_at,
            updated_at=updated_at,
            last_accessed=data.get("last_accessed"),
            access_count=max(0, int(data.get("access_count") or 0)),
            feedback_score=float(data.get("feedback_score") or 0.0),
            schema_version=int(data.get("schema_version") or SCHEMA_VERSION),
        )

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["memory_type"] = normalize_memory_type(data.get("memory_type"))
        data["scope"] = normalize_scope(
            data.get("scope"),
            project_id=data.get("project_id"),
            session_id=data.get("session_id"),
            agent=data.get("agent"),
        )
        data["visibility"] = normalize_visibility(data.get("visibility"))
        data["tags"] = normalize_tags(data.get("tags"))
        data["confidence"] = clamp01(data.get("confidence"), 0.5)
        data["importance"] = clamp01(data.get("importance"), 0.5)
        return data

    def vector_metadata(self) -> dict[str, Any]:
        metadata = dict(self.metadata)
        metadata.update({
            "memory_id": self.id,
            "tenant_id": self.tenant_id,
            "memory_type": self.memory_type,
            "scope": self.scope,
            "source": self.source,
            # Persisted so the C4 provenance-trust gate (core/memory_trust.py) can
            # read real confidence/importance at retrieval time instead of defaults.
            "confidence": self.confidence,
            "importance": self.importance,
            "agent": self.agent or "",
            "project_id": self.project_id or "",
            "session_id": self.session_id or "",
            "task_id": self.task_id or "",
            "topic": self.topic or "",
            "tags": list(self.tags),
            "verified": self.verified,
            "sensitive": self.sensitive,
            "visibility": self.visibility,
        })
        return metadata

    def touch(self) -> None:
        self.access_count += 1
        self.last_accessed = utc_now()
        self.updated_at = self.last_accessed
