from dataclasses import dataclass, field
from typing import Optional
import time
import uuid


@dataclass
class Deadline:
    initiative_id: str
    tenant_id: str
    deadline_ts: float
    priority: int = 5
    status: str = "pending"
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: float = field(default_factory=time.time)


@dataclass
class UrgencyScore:
    initiative_id: str
    base_priority: int
    time_remaining_s: float
    urgency: float  # 0-100
    computed_at: float = field(default_factory=time.time)


@dataclass
class OperationalCycle:
    workflow_type: str
    tenant_id: str
    period_days: int
    confidence: float
    last_peak: float
    detected_at: float = field(default_factory=time.time)
