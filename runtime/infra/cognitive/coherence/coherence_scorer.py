"""Cognitive coherence scoring engine.

Computes composite coherence across consistency, deduplication, and loop-detection.
Uses 5-minute event window for tenant-scoped metrics.
"""
import time
import collections
import logging
from .schema import CoherenceScore
from .contradiction_detector import list_contradictions
from .loop_detector import get_loop_detector
from .deduplication_engine import list_active

logger = logging.getLogger(__name__)

_event_window: collections.deque = collections.deque(maxlen=5000)
_WINDOW_S = 300  # 5-minute scoring window


def record_event(event_type: str, tenant_id: str, metadata: dict = None) -> None:
    """Record a cognitive event (contradiction, loop, duplicate)."""
    _event_window.append({
        "type": event_type,
        "tenant": tenant_id,
        "ts": time.time(),
        "meta": metadata or {},
    })


def compute(tenant_id: str) -> CoherenceScore:
    """Compute composite coherence score for tenant.

    Aggregates:
    - Consistency (contradictions): 40% weight
    - Deduplication (duplicates blocked): 30% weight
    - Loop-free (cycles detected): 30% weight

    All scores normalized to 0-100 range.
    """
    now = time.time()
    cutoff = now - _WINDOW_S
    recent = [e for e in _event_window if e["tenant"] == tenant_id and e["ts"] >= cutoff]

    contradictions = len([e for e in recent if e["type"] == "cognitive:contradiction"])
    loops = len([e for e in recent if e["type"] == "cognitive:loop_detected"])
    duplicates = len([e for e in recent if e["type"] == "cognitive:duplicate_blocked"])

    consistency = max(0.0, min(100.0, 100.0 - contradictions * 10))
    loop_free = max(0.0, min(100.0, 100.0 - loops * 20))
    dedup = max(0.0, min(100.0, 100.0 - duplicates * 5))
    overall = 0.4 * consistency + 0.3 * dedup + 0.3 * loop_free

    return CoherenceScore(
        tenant_id=tenant_id,
        overall=round(overall, 1),
        consistency_score=round(consistency, 1),
        dedup_score=round(dedup, 1),
        loop_free_score=round(loop_free, 1),
    )


def get_coherence_scorer():
    """Get singleton coherence scorer instance."""
    return type("CoherenceScorer", (), {
        "compute": staticmethod(compute),
        "record_event": staticmethod(record_event),
    })()
