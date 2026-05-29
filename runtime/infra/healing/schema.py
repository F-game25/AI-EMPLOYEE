"""Self-healing data schemas."""
from __future__ import annotations
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class RecoveryAction(str, Enum):
    RESTART_AGENT = "restart_agent"
    SCALE_OUT = "scale_out"
    ROLLBACK = "rollback"
    DEGRADE = "degrade"
    ALERT = "alert"


class HealingEventType(str, Enum):
    ANOMALY_DETECTED = "anomaly_detected"
    CIRCUIT_OPENED = "circuit_opened"
    CIRCUIT_CLOSED = "circuit_closed"
    AGENT_QUARANTINED = "agent_quarantined"
    AGENT_RESTORED = "agent_restored"
    RECOVERY_ATTEMPTED = "recovery_attempted"
    RECOVERY_SUCCEEDED = "recovery_succeeded"
    RECOVERY_FAILED = "recovery_failed"
    PREDICTION = "prediction"
    ROLLBACK_COMPLETED = "rollback_completed"


@dataclass
class HealthScore:
    service: str
    score: float            # 0-100
    latency_score: float
    error_score: float
    cpu_score: float
    queue_score: float
    computed_at: float = field(default_factory=time.time)
    details: dict = field(default_factory=dict)


@dataclass
class CircuitBreakerState:
    service: str
    state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    success_count: int = 0
    last_probe: float = 0.0
    last_state_change: float = field(default_factory=time.time)
    threshold: int = 5          # failures before OPEN
    half_open_timeout: float = 30.0  # seconds in OPEN before probe


@dataclass
class RecoveryPolicy:
    service: str
    actions: list[RecoveryAction] = field(default_factory=lambda: [
        RecoveryAction.RESTART_AGENT,
        RecoveryAction.SCALE_OUT,
        RecoveryAction.ROLLBACK,
        RecoveryAction.DEGRADE,
        RecoveryAction.ALERT,
    ])
    restart_attempts: int = 3
    restart_backoff_s: float = 5.0
    webhook_url: Optional[str] = None


@dataclass
class HealingEvent:
    event_type: HealingEventType
    service: str
    message: str
    details: dict = field(default_factory=dict)
    ts: float = field(default_factory=time.time)


@dataclass
class FailurePrediction:
    service: str
    probability: float      # 0-1
    predicted_at: float = field(default_factory=time.time)
    horizon_minutes: int = 15
    metric: str = ""
    z_score: float = 0.0
