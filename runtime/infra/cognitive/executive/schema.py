from dataclasses import dataclass, field
from typing import Optional
import time
import uuid


@dataclass
class Initiative:
    title: str
    tenant_id: str
    description: str = ""
    status: str = "pending"
    priority: int = 5
    estimated_cost_tokens: int = 0
    actual_cost_tokens: int = 0
    deadline: Optional[float] = None
    dependencies: list = field(default_factory=list)
    assigned_agents: list = field(default_factory=list)
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)


@dataclass
class WorkloadState:
    agent_id: str
    queue_depth: int = 0
    active_tasks: int = 0
    avg_latency_ms: float = 0.0
    utilization_pct: float = 0.0
    sampled_at: float = field(default_factory=time.time)


@dataclass
class ExecutiveDecision:
    tenant_id: str
    decision_type: str
    rationale: str
    affected_initiatives: list = field(default_factory=list)
    affected_agents: list = field(default_factory=list)
    confidence: float = 0.8
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    decided_at: float = field(default_factory=time.time)
