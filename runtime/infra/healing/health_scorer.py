"""Composite health scorer — latency + error_rate + CPU + queue_depth."""
from __future__ import annotations
import logging
import time
from typing import Optional

from .schema import HealthScore

logger = logging.getLogger(__name__)

try:
    import psutil
    _PSUTIL_OK = True
except ImportError:
    _PSUTIL_OK = False


def _cpu_score() -> float:
    """Return 0-100 score where 100 = healthy (low CPU)."""
    if _PSUTIL_OK:
        try:
            pct = psutil.cpu_percent(interval=0.1)
            return max(0.0, 100.0 - pct)
        except Exception:
            pass
    # /proc/loadavg fallback
    try:
        with open("/proc/loadavg") as f:
            load1 = float(f.read().split()[0])
        import os
        cores = os.cpu_count() or 1
        ratio = load1 / cores
        return max(0.0, 100.0 - ratio * 50)
    except Exception:
        return 80.0  # unknown, assume healthy


def _latency_score(service: str) -> float:
    """Return 0-100 score from Phase 2 ExecutionStore avg latency."""
    try:
        from infra.telemetry.execution_recorder import get_execution_store
        store = get_execution_store()
        recent = store.query(limit=50)
        latencies = [
            r.get("duration_ms", 0)
            for r in recent
            if r.get("service") == service and r.get("duration_ms") is not None
        ]
        if not latencies:
            return 90.0
        avg_ms = sum(latencies) / len(latencies)
        if avg_ms < 500:
            return 100.0
        if avg_ms > 10000:
            return 0.0
        return max(0.0, 100.0 - (avg_ms - 500) / 95)
    except Exception:
        return 80.0


def _error_score(service: str) -> float:
    """Return 0-100 score where 100 = no errors."""
    try:
        from infra.telemetry.execution_recorder import get_execution_store
        store = get_execution_store()
        recent = store.query(limit=50)
        svc_recs = [r for r in recent if r.get("service") == service]
        if not svc_recs:
            return 90.0
        errors = sum(1 for r in svc_recs if r.get("status") == "error")
        rate = errors / len(svc_recs)
        return max(0.0, 100.0 - rate * 100)
    except Exception:
        return 80.0


def score_service(service: str, queue_depth: int = 0) -> HealthScore:
    lat = _latency_score(service)
    err = _error_score(service)
    cpu = _cpu_score()
    q_score = max(0.0, 100.0 - queue_depth * 5)  # -5pts per queued item above 0

    composite = 0.30 * lat + 0.30 * err + 0.20 * cpu + 0.20 * q_score
    return HealthScore(
        service=service, score=round(composite, 1),
        latency_score=lat, error_score=err,
        cpu_score=cpu, queue_score=q_score,
        computed_at=time.time(),
        details={"queue_depth": queue_depth},
    )
