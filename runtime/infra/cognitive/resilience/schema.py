from dataclasses import dataclass, field
from enum import Enum
from uuid import uuid4
from typing import Optional
import time


class DegradationLevel(str, Enum):
    NONE = "none"
    LIGHT = "light"          # 70% CPU: throttle P3
    MODERATE = "moderate"    # 85% CPU: throttle P2+P3
    SEVERE = "severe"        # 95% CPU: emergency mode P0 only
    CRITICAL = "critical"    # >100k queue: shed everything except P0


class EventTier(str, Enum):
    P0 = "p0"                # healing/guardrail events: immediate, never dropped
    P1 = "p1"                # agent results: high priority
    P2 = "p2"                # notifications: medium priority
    P3 = "p3"                # logs: low priority, first to drop


@dataclass
class ResilienceEvent:
    id: str = field(default_factory=lambda: str(uuid4()))
    tenant_id: str = ""
    event_type: str = ""     # subsystem_failure, event_storm, queue_overflow, etc.
    degradation_level: DegradationLevel = DegradationLevel.NONE
    message: str = ""
    affected_subsystems: list[str] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)


@dataclass
class BackpressureState:
    subsystem_id: str = ""
    queue_depth: int = 0
    queue_max_depth: int = 10000
    is_backpressured: bool = False
    backpressure_triggered_at: Optional[float] = None
    threshold_high: float = 0.8      # 80% → emit slow_down
    threshold_clear: float = 0.4     # 40% → clear slow_down
    timestamp: float = field(default_factory=time.time)


@dataclass
class QueueMetrics:
    subsystem_id: str = ""
    queue_depth: int = 0
    peak_depth: int = 0
    avg_depth: float = 0.0
    p90_depth: int = 0
    dropped_count: int = 0
    sampled_at: float = field(default_factory=time.time)
