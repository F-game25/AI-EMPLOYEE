from __future__ import annotations

import threading
import time
from typing import Any

from core.observability.event_stream import EventStream, get_event_stream
from core.observability.metrics_collector import MetricsCollector, get_metrics_collector


class AnomalyDetector:
    """Detects reliability anomalies and triggers alert events."""

    def __init__(
        self,
        metrics: MetricsCollector | None = None,
        stream: EventStream | None = None,
    ) -> None:
        self._metrics = metrics or get_metrics_collector()
        self._stream = stream or get_event_stream()
        self._lock = threading.RLock()
        self._anomalies: list[dict[str, Any]] = []

    @staticmethod
    def _ts() -> str:
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    def detect(self) -> list[dict[str, Any]]:
        snapshot = self._metrics.snapshot()
        history = snapshot.get("history", [])
        if not history:
            return []

        latest = history[0]
        anomalies: list[dict[str, Any]] = []

        errors = float(latest.get("errors_per_minute", 0) or 0)
        if errors >= 5:
            anomalies.append(self._make("sudden_error_spike", "high", {"errors_per_minute": errors}))

        queue_depth = float(latest.get("queue_depth", 0) or 0)
        task_duration = float(latest.get("task_duration_ms", 0) or 0)
        if queue_depth > 0 and task_duration > 20000:
            anomalies.append(self._make("queue_stall", "high", {"queue_depth": queue_depth, "task_duration_ms": task_duration}))

        decisions = float(latest.get("brain_decisions_per_sec", 0) or 0)
        if decisions == 0 and len(history) >= 30:
            inactive = all(float(item.get("brain_decisions_per_sec", 0) or 0) == 0 for item in history[:30])
            if inactive:
                anomalies.append(self._make("inactive_brain", "medium", {"window_seconds": 30}))

        recent_events = self._stream.recent(80)
        recent_failures = [e for e in recent_events if e.get("event_type") == "error_detected"]
        if len(recent_failures) >= 4:
            anomalies.append(self._make("task_failure_loop", "high", {"recent_failures": len(recent_failures)}))

        if anomalies:
            with self._lock:
                self._anomalies = (anomalies + self._anomalies)[:200]
            for anomaly in anomalies:
                self._stream.publish("error_detected", {"anomaly": anomaly})
                self._stream.publish("auto_debug", {"trigger": anomaly["type"], "severity": anomaly["severity"]})
        return anomalies

    def recent(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._anomalies)[:limit]

    def _make(self, anomaly_type: str, severity: str, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": f"anom-{int(time.time() * 1000)}",
            "ts": self._ts(),
            "type": anomaly_type,
            "severity": severity,
            "payload": payload,
        }


_instance: AnomalyDetector | None = None
_instance_lock = threading.Lock()


def get_anomaly_detector() -> AnomalyDetector:
    global _instance
    with _instance_lock:
        if _instance is None:
            _instance = AnomalyDetector()
    return _instance
