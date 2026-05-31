from dataclasses import dataclass, field
from typing import Optional
import time
import uuid


@dataclass
class TeammateIdentity:
    tenant_id: str
    name: str = "Aeternus"
    persona_summary: str = "An autonomous AI enterprise intelligence."
    operational_focus: str = "general"
    expertise_areas: list = field(default_factory=list)
    interaction_count: int = 0
    formed_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)


@dataclass
class HabitPattern:
    user_id: str
    tenant_id: str
    workflow_type: str
    typical_hour: int
    frequency: int
    confidence: float
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    detected_at: float = field(default_factory=time.time)


@dataclass
class ProactiveInsight:
    tenant_id: str
    title: str
    body: str
    insight_type: str  # habit_reminder | blocked_initiative | anomaly
    user_id: Optional[str] = None
    priority: int = 5
    dismissed: bool = False
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: float = field(default_factory=time.time)
