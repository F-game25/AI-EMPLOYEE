"""Neural Brain Health Monitor — self-healing backbone.

Tracks error rate, latency, and per-arch failures. When thresholds are
breached it:
1. Emits system:degraded / system:recovered on the event bus
2. Auto-triggers a debounced Forge goal to patch the broken subsystem
3. Blacklists the worst-performing model providers

Runs as a background daemon thread — start once at process boot.
"""
from __future__ import annotations

import logging
import threading
import time
from collections import deque
from typing import Any

logger = logging.getLogger(__name__)

# Thresholds (overrideable via env)
import os
_ERROR_RATE_THRESHOLD = float(os.getenv("NB_HEALTH_ERROR_RATE", "0.25"))   # 25% errors
_LATENCY_THRESHOLD_MS = float(os.getenv("NB_HEALTH_LATENCY_MS", "8000"))   # 8s
_WINDOW_S = int(os.getenv("NB_HEALTH_WINDOW_S", "120"))                     # 2-min rolling window
_FORGE_DEBOUNCE_S = int(os.getenv("NB_HEALTH_FORGE_DEBOUNCE_S", "300"))    # 5-min debounce
_CHECK_INTERVAL_S = float(os.getenv("NB_HEALTH_CHECK_INTERVAL_S", "10"))   # check every 10s


class HealthRecord:
    __slots__ = ("ts", "latency_ms", "ok", "source")

    def __init__(self, *, ts: float, latency_ms: float, ok: bool, source: str) -> None:
        self.ts = ts
        self.latency_ms = latency_ms
        self.ok = ok
        self.source = source


class HealthMonitor:
    """Background monitor — call record() after every operation."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._records: deque[HealthRecord] = deque()
        self._degraded = False
        self._last_forge_trigger: float = 0.0
        self._running = False
        self._thread: threading.Thread | None = None
        # Per-source blacklist (source string → until_ts)
        self._blacklist: dict[str, float] = {}

    # ── Public record API ─────────────────────────────────────────────────

    def record(self, *, latency_ms: float, ok: bool, source: str = "neural_brain") -> None:
        """Call after every LLM / agent / pipeline operation."""
        with self._lock:
            self._records.append(HealthRecord(ts=time.time(), latency_ms=latency_ms, ok=ok, source=source))

    # ── Blacklist API ─────────────────────────────────────────────────────

    def blacklist(self, source: str, duration_s: float = 300.0) -> None:
        with self._lock:
            self._blacklist[source] = time.time() + duration_s
        logger.warning("HealthMonitor: blacklisted %s for %.0fs", source, duration_s)
        try:
            from neural_brain.utils.event_bus import publish
            publish("system:source_blacklisted", source="system", payload={"source": source, "duration_s": duration_s})
        except Exception:
            pass

    def is_blacklisted(self, source: str) -> bool:
        with self._lock:
            until = self._blacklist.get(source, 0)
            if until and time.time() < until:
                return True
            if source in self._blacklist:
                del self._blacklist[source]
            return False

    # ── Start ─────────────────────────────────────────────────────────────

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="nb_health_monitor")
        self._thread.start()
        logger.info("HealthMonitor started (window=%ds, error_threshold=%.0f%%)", _WINDOW_S, _ERROR_RATE_THRESHOLD * 100)

    def stop(self) -> None:
        self._running = False

    # ── Internal loop ─────────────────────────────────────────────────────

    def _loop(self) -> None:
        while self._running:
            try:
                self._evaluate()
            except Exception as e:
                logger.debug("HealthMonitor evaluate error: %s", e)
            time.sleep(_CHECK_INTERVAL_S)

    def _evaluate(self) -> None:
        now = time.time()
        cutoff = now - _WINDOW_S

        with self._lock:
            # Evict old records
            while self._records and self._records[0].ts < cutoff:
                self._records.popleft()

            records = list(self._records)

        if not records:
            return

        total = len(records)
        errors = sum(1 for r in records if not r.ok)
        avg_latency = sum(r.latency_ms for r in records) / total
        error_rate = errors / total

        degraded = error_rate >= _ERROR_RATE_THRESHOLD or avg_latency >= _LATENCY_THRESHOLD_MS

        # Emit state change events
        if degraded and not self._degraded:
            self._degraded = True
            self._emit_degraded(error_rate, avg_latency)
            self._maybe_trigger_forge(error_rate, avg_latency)
        elif not degraded and self._degraded:
            self._degraded = False
            self._emit_recovered(error_rate, avg_latency)

        # Auto-blacklist sources with >50% error rate
        source_stats: dict[str, list[bool]] = {}
        for r in records:
            source_stats.setdefault(r.source, []).append(r.ok)
        for src, outcomes in source_stats.items():
            src_error_rate = 1 - (sum(outcomes) / len(outcomes))
            if src_error_rate > 0.5 and len(outcomes) >= 5:
                self.blacklist(src, duration_s=180.0)

    def _emit_degraded(self, error_rate: float, avg_latency: float) -> None:
        try:
            from neural_brain.utils.event_bus import publish
            publish("system:degraded", source="system", payload={
                "error_rate": round(error_rate, 3),
                "avg_latency_ms": round(avg_latency, 1),
                "threshold_error_rate": _ERROR_RATE_THRESHOLD,
                "threshold_latency_ms": _LATENCY_THRESHOLD_MS,
            })
        except Exception:
            pass
        logger.warning("HealthMonitor: DEGRADED — error_rate=%.1f%%, avg_latency=%.0fms", error_rate * 100, avg_latency)

    def _emit_recovered(self, error_rate: float, avg_latency: float) -> None:
        try:
            from neural_brain.utils.event_bus import publish
            publish("system:recovered", source="system", payload={
                "error_rate": round(error_rate, 3),
                "avg_latency_ms": round(avg_latency, 1),
            })
        except Exception:
            pass
        logger.info("HealthMonitor: RECOVERED — error_rate=%.1f%%", error_rate * 100)

    def _maybe_trigger_forge(self, error_rate: float, avg_latency: float) -> None:
        now = time.time()
        if now - self._last_forge_trigger < _FORGE_DEBOUNCE_S:
            return
        self._last_forge_trigger = now
        # Publish event — ConsciousnessEngine or ForgeController subscribes and acts
        # NEVER call forge_controller directly from a monitor (avoids circular deps + enforces kernel routing)
        try:
            from neural_brain.utils.event_bus import publish
            goal = (
                f"System degraded: error_rate={error_rate:.0%}, latency={avg_latency:.0f}ms. "
                "Analyse neural brain pipeline for bottlenecks and improve fault tolerance."
            )
            publish("forge:health_trigger", source="health_monitor", payload={
                "goal": goal[:120],
                "module": "runtime/neural_brain/workflows/nodes.py",
                "trigger": "health_monitor",
                "error_rate": round(error_rate, 3),
                "avg_latency_ms": round(avg_latency, 1),
                "severity": "CRITICAL" if error_rate >= 0.40 else "HIGH",
            })
            logger.info("HealthMonitor: forge:health_trigger emitted (debounce %ds)", _FORGE_DEBOUNCE_S)
        except Exception as e:
            logger.debug("HealthMonitor forge trigger skipped: %s", e)

    def current_stats(self) -> dict:
        now = time.time()
        cutoff = now - _WINDOW_S
        with self._lock:
            records = [r for r in self._records if r.ts >= cutoff]
        if not records:
            return {"error_rate": 0.0, "avg_latency_ms": 0.0, "sample_count": 0, "degraded": self._degraded}
        total = len(records)
        errors = sum(1 for r in records if not r.ok)
        return {
            "error_rate": round(errors / total, 3),
            "avg_latency_ms": round(sum(r.latency_ms for r in records) / total, 1),
            "sample_count": total,
            "degraded": self._degraded,
            "blacklisted_sources": [s for s, until in self._blacklist.items() if time.time() < until],
        }


# ── Singleton ─────────────────────────────────────────────────────────────────

_monitor_instance: HealthMonitor | None = None
_monitor_lock = threading.Lock()


def get_health_monitor() -> HealthMonitor:
    global _monitor_instance
    if _monitor_instance is None:
        with _monitor_lock:
            if _monitor_instance is None:
                _monitor_instance = HealthMonitor()
                _monitor_instance.start()
    return _monitor_instance
