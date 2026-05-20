from dataclasses import dataclass, field
from typing import Optional
import time
import uuid


@dataclass
class OrgNode:
    name: str
    tenant_id: str
    role: str = "agent"
    node_type: str = "agent"
    reports_to: Optional[str] = None
    metadata: dict = field(default_factory=dict)
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: float = field(default_factory=time.time)


@dataclass
class WorkflowEdge:
    source_workflow: str
    target_workflow: str
    tenant_id: str
    frequency: int = 1
    avg_gap_s: float = 0.0
    last_seen: float = field(default_factory=time.time)


@dataclass
class UserBehaviorProfile:
    user_id: str
    tenant_id: str
    peak_hours: list = field(default_factory=list)
    frequent_workflows: dict = field(default_factory=dict)
    avg_session_length_m: float = 0.0
    preferred_agents: dict = field(default_factory=dict)
    updated_at: float = field(default_factory=time.time)
