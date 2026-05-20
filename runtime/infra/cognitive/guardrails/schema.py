from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
import time
import uuid


class TrustTier(str, Enum):
    SUPERVISED = "supervised"
    ASSISTED   = "assisted"
    AUTONOMOUS = "autonomous"
    TRUSTED    = "trusted"


class DegradationLevel(str, Enum):
    NONE      = "none"
    THROTTLED = "throttled"
    DEGRADED  = "degraded"
    EMERGENCY = "emergency"


@dataclass
class GuardrailViolation:
    tenant_id: str
    agent_id: str
    violation_type: str
    detail: str
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    occurred_at: float = field(default_factory=time.time)


@dataclass
class ThrottleState:
    agent_id: str
    tokens: float
    max_tokens: float
    refill_rate: float
    last_refill: float = field(default_factory=time.time)
