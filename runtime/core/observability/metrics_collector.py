from __future__ import annotations

import os
import threading
import time
from collections import deque
from typing import Any

from core.observability.event_stream import EventStream, get_event_stream

DECISION_WINDOW_SECONDS = 10.0


class MetricsCollector:
    """Collects runtime metrics every second."""

    def __init__(self, stream: EventStream | None = None) -> None:
        self._stream = stream or get_event_stream()
        self._lock = threading.RLock()
        self._running = False
        self._thread: threading.Thread | None = None
        self._metrics: deque[dict[str, Any]] = deque(maxlen=3600)
        self._task_durations: deque[float] = deque(maxlen=300)
        self._api_latencies: deque[float] = deque(maxlen=300)
        self._errors: deque[float] = deque(maxlen=600)
        self._brain_decisions: deque[float] = deque(maxlen=600)

    @staticmethod
    def _ts() -> str:
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    @staticmethod
    def _cpu_percent() -> float:
        try:
            load = os.getloadavg()[0]
            cpus = os.cpu_count() or 1
            return round(max(0.0, min(100.0, (load / cpus) * 100)), 2)
        except Exception:
            return 0.0

    @staticmethod
    def _memory_percent() -> float:
        try:
            import resource

            rss_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            total = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
            rss = rss_kb * 1024
            return round(max(0.0, min(100.0, (rss / max(total, 1)) * 100)), 2)
        except Exception:
            return 0.0

    def record_task_duration(self, duration_ms: float) -> None:
        with self._lock:
            self._task_durations.append(max(0.0, float(duration_ms)))

    def record_api_latency(self, latency_ms: float) -> None:
        with self._lock:
            self._api_latencies.append(max(0.0, float(latency_ms)))

    def record_error(self) -> None:
        with self._lock:
            self._errors.append(time.time())

    def record_brain_decision(self) -> None:
        with self._lock:
            self._brain_decisions.append(time.time())

    def start(self) -> None:
        with self._lock:
            if self._running:
                return
            self._running = True
            self._thread = threading.Thread(target=self._loop, name="metrics-collector", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        with self._lock:
            self._running = False
        if self._thread:
            self._thread.join(timeout=2)
            self._thread = None

    def _loop(self) -> None:
        while True:
            with self._lock:
                if not self._running:
                    return
            snapshot = self.collect_once()
            self._stream.publish("metrics_tick", snapshot)
            time.sleep(1.0)

    def collect_once(self) -> dict[str, Any]:
        now_t = time.time()
        with self._lock:
            errors_last_min = len([t for t in self._errors if now_t - t <= 60])
            decisions_last_10 = len([t for t in self._brain_decisions if now_t - t <= DECISION_WINDOW_SECONDS])
            avg_task = round(sum(self._task_durations) / max(len(self._task_durations), 1), 2) if self._task_durations else 0.0
            avg_latency = round(sum(self._api_latencies) / max(len(self._api_latencies), 1), 2) if self._api_latencies else 0.0
            snapshot = {
                "ts": self._ts(),
                "cpu_percent": self._cpu_percent(),
                "memory_percent": self._memory_percent(),
                "active_agents": threading.active_count(),
                "queue_depth": 0,
                "task_duration_ms": avg_task,
                "errors_per_minute": errors_last_min,
                "api_latency_ms": avg_latency,
                "brain_decisions_per_sec": round(decisions_last_10 / DECISION_WINDOW_SECONDS, 3),
            }
            self._metrics.appendleft(snapshot)
        return snapshot

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            latest = self._metrics[0] if self._metrics else self.collect_once()
            return {
                "latest": latest,
                "history": list(self._metrics)[:120],
            }


_instance: MetricsCollector | None = None
_instance_lock = threading.Lock()


def get_metrics_collector() -> MetricsCollector:
    global _instance
    with _instance_lock:
        if _instance is None:
            _instance = MetricsCollector()
    return _instance
