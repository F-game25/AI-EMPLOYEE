"""Multi-signal oracle scorer."""
from __future__ import annotations
import logging
from datetime import datetime, timezone, timedelta
from core.quantum.candidate import Candidate

log = logging.getLogger(__name__)

WEIGHTS = {
    'semantic':         0.25,
    'keyword':          0.08,
    'graph_centrality': 0.12,
    'recency':          0.05,
    'past_success':     0.12,
    'task_type_fit':    0.10,
    'dependency_prox':  0.08,
    'permission_ok':    0.05,
    'user_context':     0.05,
    'intent_alignment': 0.10,
}

TASK_TYPE_AFFINITY: dict[str, list[str]] = {
    'coding':    ['code_file', 'tool', 'doc'],
    'planning':  ['agent', 'roadmap', 'task_log'],
    'research':  ['web', 'rag', 'memory', 'graph_memory'],
    'security':  ['doc', 'agent', 'code_file'],
    'execution': ['agent', 'tool', 'task_log'],
    'memory':    ['memory', 'graph_memory', 'rag'],
}


def _token_overlap(a: str, b: str) -> float:
    ta = set(a.lower().split())
    tb = set(b.lower().split())
    if not ta:
        return 0.0
    return len(ta & tb) / max(len(ta), 1)


def _recency_score(metadata: dict) -> float:
    updated = metadata.get('updated_at')
    if not updated:
        return 0.5
    try:
        if isinstance(updated, str):
            ts = datetime.fromisoformat(updated.replace('Z', '+00:00'))
        else:
            ts = datetime.fromtimestamp(float(updated), tz=timezone.utc)
        now = datetime.now(tz=timezone.utc)
        age = now - ts
        if age <= timedelta(hours=24):
            return 1.0
        if age <= timedelta(days=7):
            return 0.7
        if age <= timedelta(days=30):
            return 0.4
        return 0.2
    except Exception:
        return 0.5


class OracleScorer:
    def __init__(self, weights: dict | None = None):
        self._w = weights or WEIGHTS

    def score(self, candidate: Candidate, query: str, task_type: str = '',
              intent_text: str = '', tenant_id: str = '') -> float:
        r = candidate.result
        content = f"{r.title} {r.content}"

        signals: dict[str, float] = {}
        signals['semantic']         = _token_overlap(query, content)
        signals['keyword']          = 1.0 if query.lower() in content.lower() else _token_overlap(query, content)
        signals['graph_centrality'] = min(len(r.graph_neighbors) / 20.0, 1.0)
        signals['recency']          = _recency_score(r.metadata)
        signals['past_success']     = r.past_success_rate
        affinity = TASK_TYPE_AFFINITY.get(task_type, [])
        signals['task_type_fit']    = 1.0 if r.source_type in affinity else 0.5
        signals['dependency_prox']  = 0.5  # TODO: real graph traversal
        signals['permission_ok']    = float(r.metadata.get('permission_ok', 1.0))
        signals['user_context']     = 1.0 if (not tenant_id or r.tenant_id == tenant_id or r.tenant_id == '') else 0.0
        signals['intent_alignment'] = _token_overlap(intent_text or query, content)

        total = sum(self._w[k] * signals[k] for k in self._w)
        candidate.oracle_score = round(min(max(total, 0.0), 1.0), 4)

        top2 = sorted(self._w, key=lambda k: self._w[k] * signals[k], reverse=True)[:2]
        candidate.why = ', '.join(f"{k}={signals[k]:.2f}" for k in top2)

        return candidate.oracle_score
