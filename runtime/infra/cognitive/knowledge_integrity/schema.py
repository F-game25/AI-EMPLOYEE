from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
import time
import uuid


class MemoryLifecycleState(str, Enum):
    FRESH = "fresh"           # 0 days: just learned
    REINFORCED = "reinforced" # confirmed by multiple sources
    STABLE = "stable"         # 7+ days: proven reliable
    AGING = "aging"           # 7+ days: no recent access
    STALE = "stale"           # 30+ days: needs validation
    ARCHIVED = "archived"     # 90+ days: historical but searchable
    QUARANTINED = "quarantined"  # low confidence or contradicted


@dataclass
class MemoryRecord:
    """Lifecycle-tracked memory entry."""
    tenant_id: str
    memory_key: str
    text: str
    embedding: Optional[list[float]] = None
    state: MemoryLifecycleState = MemoryLifecycleState.FRESH
    confidence: float = 0.8
    source_agent_id: str = ""
    created_at: float = field(default_factory=time.time)
    last_accessed_at: float = field(default_factory=time.time)
    access_count: int = 0
    reinforcement_count: int = 0
    metadata: dict = field(default_factory=dict)
    id: str = field(default_factory=lambda: str(uuid.uuid4()))

    @property
    def age_days(self) -> float:
        return (time.time() - self.created_at) / 86400

    @property
    def days_since_access(self) -> float:
        return (time.time() - self.last_accessed_at) / 86400

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "memory_key": self.memory_key,
            "text": self.text,
            "embedding": self.embedding,
            "state": self.state.value,
            "confidence": self.confidence,
            "source_agent_id": self.source_agent_id,
            "created_at": self.created_at,
            "last_accessed_at": self.last_accessed_at,
            "access_count": self.access_count,
            "reinforcement_count": self.reinforcement_count,
            "metadata": self.metadata,
            "age_days": self.age_days,
            "days_since_access": self.days_since_access,
        }


@dataclass
class DuplicateCluster:
    """Group of semantically similar memories."""
    cluster_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str = ""
    memory_ids: list[str] = field(default_factory=list)
    similarity_scores: list[float] = field(default_factory=list)
    canonical_id: Optional[str] = None
    consolidated_text: str = ""
    consolidated_embedding: Optional[list[float]] = None
    detected_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "cluster_id": self.cluster_id,
            "tenant_id": self.tenant_id,
            "memory_ids": self.memory_ids,
            "similarity_scores": self.similarity_scores,
            "canonical_id": self.canonical_id,
            "consolidated_text": self.consolidated_text,
            "detected_at": self.detected_at,
        }


@dataclass
class Contradiction:
    """Logical conflict between two memories."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str = ""
    memory_id_a: str = ""
    memory_id_b: str = ""
    conflict_type: str = ""  # e.g., "factual", "temporal", "logical"
    confidence: float = 0.8
    description: str = ""
    detected_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "memory_id_a": self.memory_id_a,
            "memory_id_b": self.memory_id_b,
            "conflict_type": self.conflict_type,
            "confidence": self.confidence,
            "description": self.description,
            "detected_at": self.detected_at,
        }


@dataclass
class HallucinationFlag:
    """Low-confidence or suspicious claim in memory."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str = ""
    memory_id: str = ""
    flag_type: str = ""  # e.g., "low_confidence", "absolute_claim", "future_dated"
    severity: int = 1    # 1-5: 5 = requires immediate quarantine
    reason: str = ""
    flagged_at: float = field(default_factory=time.time)
    quarantined: bool = False

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "memory_id": self.memory_id,
            "flag_type": self.flag_type,
            "severity": self.severity,
            "reason": self.reason,
            "flagged_at": self.flagged_at,
            "quarantined": self.quarantined,
        }


@dataclass
class IntegrityReport:
    """Summary of knowledge integrity health."""
    tenant_id: str = ""
    total_memories: int = 0
    fresh_count: int = 0
    reinforced_count: int = 0
    stable_count: int = 0
    aging_count: int = 0
    stale_count: int = 0
    archived_count: int = 0
    quarantined_count: int = 0
    duplicate_clusters: int = 0
    contradictions_found: int = 0
    hallucination_flags: int = 0
    avg_confidence: float = 0.8
    memory_entropy: float = 0.0  # entropy in knowledge graph (0=ordered, 1=chaotic)
    generated_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "tenant_id": self.tenant_id,
            "total_memories": self.total_memories,
            "fresh_count": self.fresh_count,
            "reinforced_count": self.reinforced_count,
            "stable_count": self.stable_count,
            "aging_count": self.aging_count,
            "stale_count": self.stale_count,
            "archived_count": self.archived_count,
            "quarantined_count": self.quarantined_count,
            "duplicate_clusters": self.duplicate_clusters,
            "contradictions_found": self.contradictions_found,
            "hallucination_flags": self.hallucination_flags,
            "avg_confidence": self.avg_confidence,
            "memory_entropy": self.memory_entropy,
            "generated_at": self.generated_at,
        }
