"""Telemetry — event counters, failure taxonomy, and dashboard payload.

Provides real-time metrics about the self-improvement loop for the
dashboard and API layer.
"""
from __future__ import annotations

import threading
import time
from collections import deque
from typing import Any


class ImprovementTelemetry:
    """Thread-safe telemetry collector for the self-improvement loop."""

    def __init__(self, max_events: int = 500) -> None:
        self._lock = threading.Lock()
        self._events: deque[dict[str, Any]] = deque(maxlen=max_events)
        self._counters: dict[str, int] = {}
        self._started_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    def record_event(self, event_type: str, **kwargs: Any) -> dict[str, Any]:
        """Record a telemetry event."""
        event = {
            "event": event_type,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            **kwargs,
        }
        with self._lock:
            self._events.appendleft(event)
            self._counters[event_type] = self._counters.get(event_type, 0) + 1
        return event

    def get_counters(self) -> dict[str, int]:
        """Return all event counters."""
        with self._lock:
            return dict(self._counters)

    def get_recent_events(self, limit: int = 20) -> list[dict[str, Any]]:
        """Return the most recent events."""
        with self._lock:
            return list(self._events)[:limit]

    def dashboard_payload(self) -> dict[str, Any]:
        """Return a structured payload for the UI dashboard.

        Includes queue depth proxy, pass/fail rates, approval ratio,
        rollback ratio, and top failure causes.
        """
        with self._lock:
            counters = dict(self._counters)
            events = list(self._events)

        total_tasks = counters.get("analyzing", 0)
        deployed = counters.get("deployed", 0)
        rolled_back = counters.get("rolled_back", 0)
        rejected = counters.get("rejected", 0) + counters.get("manual_rejected", 0)
        approved = counters.get("approved", 0) + counters.get("manual_approved", 0)
        test_failed = counters.get("test_failed", 0)
        policy_rejected = counters.get("policy_rejected", 0)
        errors = counters.get("error", 0)

        total_decisions = deployed + rolled_back + rejected + approved
        total_outcomes = deployed + rolled_back + rejected + test_failed + policy_rejected + errors

        return {
            "self_improvement": {
                "active": True,
                "started_at": self._started_at,
                "total_tasks_processed": total_tasks,
                "queue_depth": max(0, counters.get("analyzing", 0) - total_outcomes),
                "pass_rate": round(deployed / max(total_outcomes, 1), 3),
                "fail_rate": round(
                    (test_failed + policy_rejected + errors) / max(total_outcomes, 1),
                    3,
                ),
                "approval_ratio": round(approved / max(total_decisions, 1), 3),
                "rejection_ratio": round(rejected / max(total_decisions, 1), 3),
                "rollback_ratio": round(rolled_back / max(deployed + rolled_back, 1), 3),
                "deployed": deployed,
                "rolled_back": rolled_back,
                "rejected": rejected,
                "test_failures": test_failed,
                "policy_violations": policy_rejected,
                "errors": errors,
                "top_failure_causes": self._top_failure_causes(counters),
                "recent_events": events[:10],
            },
        }

    @staticmethod
    def _top_failure_causes(counters: dict[str, int]) -> list[dict[str, Any]]:
        """Extract top failure causes from counters."""
        failure_keys = ["test_failed", "policy_rejected", "error", "rolled_back", "rejected"]
        causes = [
            {"cause": k, "count": counters.get(k, 0)}
            for k in failure_keys
            if counters.get(k, 0) > 0
        ]
        return sorted(causes, key=lambda x: -x["count"])[:5]


# ── Singleton ─────────────────────────────────────────────────────────────────

_instance: ImprovementTelemetry | None = None
_instance_lock = threading.Lock()


def get_telemetry() -> ImprovementTelemetry:
    """Return the process-wide ImprovementTelemetry singleton."""
    global _instance
    with _instance_lock:
        if _instance is None:
            _instance = ImprovementTelemetry()
    return _instance
