"""Constructive/destructive interference rules."""
from __future__ import annotations
from core.quantum.candidate import Candidate
from core.quantum.oracle import TASK_TYPE_AFFINITY


def apply(candidates: list[Candidate], query: str, task_type: str = '',
          tenant_id: str = '') -> list[Candidate]:
    affinity = TASK_TYPE_AFFINITY.get(task_type, [])

    for c in candidates:
        r = c.result
        meta = r.metadata

        # Destructive rules first (order matters — hard blocks)
        if meta.get('adversarial'):
            c.amplitude = 0.0
            c.interference = 'destructive'
            continue
        if meta.get('circuit_open'):
            c.amplitude = 0.0
            c.interference = 'destructive'
            continue
        if meta.get('permission_ok', 1) == 0:
            c.amplitude = 0.0
            c.interference = 'destructive'
            continue
        if tenant_id and r.tenant_id and r.tenant_id != tenant_id:
            c.amplitude = 0.0
            c.interference = 'destructive'
            continue
        if meta.get('deprecated'):
            c.amplitude *= 0.2
            c.interference = 'destructive'
            continue
        if r.past_success_rate < 0.1:
            c.amplitude *= 0.4
            c.interference = 'destructive'
            continue

        # Constructive rules
        boosted = False
        if r.past_success_rate > 0.7 and c.oracle_score > 0.7:
            c.amplitude = min(c.amplitude * 1.3, 1.0)
            boosted = True
        if affinity and r.source_type in affinity:
            c.amplitude = min(c.amplitude * 1.3, 1.0)
            boosted = True
        if meta.get('convergence_count', 1) > 1:
            c.amplitude = min(c.amplitude * 1.3, 1.0)
            boosted = True
        if boosted:
            c.interference = 'constructive'

        c.amplitude = min(max(c.amplitude, 0.0), 1.0)

    return candidates
