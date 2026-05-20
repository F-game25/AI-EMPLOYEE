from dataclasses import dataclass, field
from typing import Optional
import time
import uuid


@dataclass
class OutcomeRecord:
    workflow_id: str
    agent_id: str
    tenant_id: str
    success: bool
    quality_score: float
    duration_ms: float
    cost_tokens: int = 0
    user_feedback: Optional[int] = None
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    recorded_at: float = field(default_factory=time.time)


@dataclass
class RoutingAdjustment:
    task_type: str
    from_agent: str
    to_agent: str
    tenant_id: str
    confidence: float
    sample_size: int
    quality_delta: float
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    suggested_at: float = field(default_factory=time.time)
    accepted: Optional[bool] = None


@dataclass
class EffectivenessScore:
    agent_id: str
    tenant_id: str
    score: float
    sample_count: int
    trend: str  # improving | degrading | stable
    computed_at: float = field(default_factory=time.time)
