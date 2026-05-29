from dataclasses import dataclass, field
from typing import Optional
import time
import uuid


@dataclass
class ObjectiveNode:
    title: str
    tenant_id: str
    description: str = ""
    priority: int = 5
    parent_id: Optional[str] = None
    status: str = "active"
    source_agent: Optional[str] = None
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)


@dataclass
class Contradiction:
    tenant_id: str
    agent_a: str
    agent_b: str
    claim_a: str
    claim_b: str
    resolved: bool = False
    resolution: Optional[str] = None
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    detected_at: float = field(default_factory=time.time)


@dataclass
class CoherenceScore:
    tenant_id: str
    overall: float = 100.0
    consistency_score: float = 100.0
    dedup_score: float = 100.0
    loop_free_score: float = 100.0
    computed_at: float = field(default_factory=time.time)
