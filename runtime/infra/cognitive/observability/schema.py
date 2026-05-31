from dataclasses import dataclass, field
from uuid import uuid4
from typing import Optional, Any
import time


@dataclass
class Span:
    id: str = field(default_factory=lambda: str(uuid4()))
    trace_id: str = ""
    parent_span_id: Optional[str] = None
    operation_name: str = ""
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    duration_ms: float = 0.0
    status: str = "pending"  # pending | success | error
    error_message: Optional[str] = None
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass
class TraceTree:
    trace_id: str = ""
    root_span_id: str = ""
    tenant_id: str = ""
    spans: list[Span] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)


@dataclass
class WorkflowLineage:
    parent_workflow_id: str = ""
    child_workflow_id: str = ""
    tenant_id: str = ""
    spawned_at: float = field(default_factory=time.time)


@dataclass
class AgentTelemetryRecord:
    agent_id: str = ""
    tenant_id: str = ""
    total_executions: int = 0
    successful_executions: int = 0
    failed_executions: int = 0
    avg_duration_ms: float = 0.0
    p95_duration_ms: float = 0.0
    p99_duration_ms: float = 0.0
    success_rate: float = 0.0
    sampled_at: float = field(default_factory=time.time)


@dataclass
class AnomalyCorrelation:
    id: str = field(default_factory=lambda: str(uuid4()))
    tenant_id: str = ""
    anomaly_ids: list[str] = field(default_factory=list)
    suspected_root_cause: str = ""
    confidence: float = 0.0
    affected_subsystems: list[str] = field(default_factory=list)
    detected_at: float = field(default_factory=time.time)
