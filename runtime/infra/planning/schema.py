"""Planning engine schemas — goals, objectives, milestones."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Horizon(str, Enum):
    DAILY     = "daily"
    WEEKLY    = "weekly"
    MONTHLY   = "monthly"
    QUARTERLY = "quarterly"
    ANNUAL    = "annual"


class GoalStatus(str, Enum):
    DRAFT      = "draft"
    ACTIVE     = "active"
    PAUSED     = "paused"
    COMPLETED  = "completed"
    CANCELLED  = "cancelled"
    FAILED     = "failed"


class Priority(str, Enum):
    P0 = "p0"   # critical / blocking
    P1 = "p1"   # high
    P2 = "p2"   # medium
    P3 = "p3"   # low / nice-to-have


@dataclass
class KeyResult:
    id: str
    description: str
    metric: str             # measurable metric name
    target: float
    current: float = 0.0
    unit: str = ""          # e.g. "%", "$", "count"
    due_at: float = 0.0

    @property
    def progress(self) -> float:
        if self.target == 0:
            return 0.0
        return min(1.0, self.current / self.target)

    def to_dict(self) -> dict:
        return {
            "id": self.id, "description": self.description,
            "metric": self.metric, "target": self.target,
            "current": self.current, "unit": self.unit,
            "due_at": self.due_at, "progress": self.progress,
        }


@dataclass
class Milestone:
    id: str
    title: str
    due_at: float           # unix timestamp
    completed_at: float = 0.0
    blocked_by: list[str] = field(default_factory=list)   # milestone IDs

    @property
    def completed(self) -> bool:
        return self.completed_at > 0

    def to_dict(self) -> dict:
        return {
            "id": self.id, "title": self.title, "due_at": self.due_at,
            "completed_at": self.completed_at, "completed": self.completed,
            "blocked_by": self.blocked_by,
        }


@dataclass
class Goal:
    id: str
    tenant_id: str
    title: str
    description: str
    horizon: Horizon
    priority: Priority
    status: GoalStatus
    owner_id: str
    created_at: float
    updated_at: float
    due_at: float
    parent_id: str | None = None          # for objective trees
    key_results: list[KeyResult] = field(default_factory=list)
    milestones: list[Milestone] = field(default_factory=list)
    depends_on: list[str] = field(default_factory=list)   # goal IDs
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    review_cadence_days: int = 7
    last_reviewed_at: float = 0.0
    confidence: float = 0.7   # AI confidence this goal will be achieved

    @property
    def overall_progress(self) -> float:
        if not self.key_results:
            return 0.0
        return sum(kr.progress for kr in self.key_results) / len(self.key_results)

    def to_dict(self) -> dict:
        return {
            "id": self.id, "tenant_id": self.tenant_id,
            "title": self.title, "description": self.description,
            "horizon": self.horizon.value, "priority": self.priority.value,
            "status": self.status.value, "owner_id": self.owner_id,
            "created_at": self.created_at, "updated_at": self.updated_at,
            "due_at": self.due_at, "parent_id": self.parent_id,
            "key_results": [kr.to_dict() for kr in self.key_results],
            "milestones": [m.to_dict() for m in self.milestones],
            "depends_on": self.depends_on, "tags": self.tags,
            "metadata": self.metadata,
            "review_cadence_days": self.review_cadence_days,
            "last_reviewed_at": self.last_reviewed_at,
            "confidence": self.confidence,
            "overall_progress": self.overall_progress,
        }


@dataclass
class StrategicPlan:
    id: str
    tenant_id: str
    title: str
    horizon: Horizon
    goals: list[str]         # goal IDs
    created_at: float
    valid_until: float
    generated_by: str = "planner"
    rationale: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id, "tenant_id": self.tenant_id,
            "title": self.title, "horizon": self.horizon.value,
            "goals": self.goals, "created_at": self.created_at,
            "valid_until": self.valid_until, "generated_by": self.generated_by,
            "rationale": self.rationale,
        }
