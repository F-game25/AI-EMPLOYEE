from dataclasses import dataclass, field
from typing import Optional
import time
import uuid


@dataclass
class DecisionRecord:
    agent_id: str
    tenant_id: str
    decision_type: str
    input_summary: str
    output_summary: str
    memories_used: list = field(default_factory=list)
    alternatives_considered: list = field(default_factory=list)
    confidence: float = 0.8
    workflow_id: Optional[str] = None
    reasoning_trace_id: Optional[str] = None
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    decided_at: float = field(default_factory=time.time)


@dataclass
class CausalChain:
    root_event_id: str
    tenant_id: str
    chain: list = field(default_factory=list)
    reconstructed_at: float = field(default_factory=time.time)


@dataclass
class ExplanationReport:
    decision_id: str
    tenant_id: str
    summary: str
    memories_used: list = field(default_factory=list)
    causal_events: int = 0
    generated_at: float = field(default_factory=time.time)
