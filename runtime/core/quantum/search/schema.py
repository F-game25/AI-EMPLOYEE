from __future__ import annotations
from dataclasses import dataclass, field
from typing import Literal

SourceType = Literal[
    'web', 'memory', 'graph_memory', 'rag', 'agent',
    'skill', 'code_file', 'route', 'tool', 'task_log',
    'event_log', 'ui_component', 'roadmap', 'test_log', 'doc', 'artifact'
]


@dataclass
class NormalizedSearchResult:
    id: str
    title: str
    content: str          # <= 500 chars
    source_type: SourceType
    url: str = ''         # file path or external URL
    engine: str = ''
    score: float = 0.0    # raw engine relevance 0-1
    amplitude: float = 0.0
    metadata: dict = field(default_factory=dict)
    skills: list[str] = field(default_factory=list)
    agent_id: str = ''
    graph_neighbors: list[str] = field(default_factory=list)
    past_success_rate: float = 0.0
    tenant_id: str = ''


@dataclass
class SearchRequest:
    query: str
    bangs: list[str] = field(default_factory=list)
    engine_filter: list[str] = field(default_factory=list)
    complexity: str = 'medium'   # simple / medium / complex / critical
    task_type: str = ''
    tenant_id: str = ''
    max_results_per_engine: int = 50
    timeout_ms: int = 2000


@dataclass
class IntentCandidate:
    text: str
    amplitude: float = 0.0
    rationale: str = ''


@dataclass
class ContextPack:
    search_id: str
    query: str
    candidates: list[NormalizedSearchResult]
    confidence: float
    intent: IntentCandidate | None = None
    top_agents: list[str] = field(default_factory=list)
    top_tools: list[str] = field(default_factory=list)
    suggested_model: str = ''
    reasoning: str = ''
    engine_stats: dict = field(default_factory=dict)
    tenant_id: str = ''
