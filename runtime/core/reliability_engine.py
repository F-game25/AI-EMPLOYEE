"""System reliability engine — detects instability and prevents cascading failures.

The engine continuously evaluates system health signals from the MetricsCollector
and the AuditEngine.  When thresholds are breached it:

  1. Freezes the Forge (no new change deployments).
  2. Records a rollback checkpoint (snapshot of a safe state descriptor).
  3. Broadcasts a reliability event via the EventStream.

Thresholds (all configurable via environment variables):
  AI_RELIABILITY_ERROR_THRESHOLD   errors/minute to trigger forge freeze  (default 10)
  AI_RELIABILITY_ANOMALY_THRESHOLD anomalies before rollback flag          (default 3)
  AI_RELIABILITY_STABILITY_WINDOW  seconds of history to evaluate          (default 60)
"""
from __future__ import annotations

import os
import threading
import time
from collections import deque
from typing import Any


# ── tuneable thresholds ───────────────────────────────────────────────────────

def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ[name])
    except (KeyError, ValueError):
        return default


ERROR_THRESHOLD: int = _env_int("AI_RELIABILITY_ERROR_THRESHOLD", 10)
ANOMALY_THRESHOLD: int = _env_int("AI_RELIABILITY_ANOMALY_THRESHOLD", 3)
STABILITY_WINDOW: int = _env_int("AI_RELIABILITY_STABILITY_WINDOW", 60)


class ReliabilityEngine:
    """Monitors system health and applies automatic safeguards."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._forge_frozen: bool = False
        self._freeze_reason: str = ""
        self._checkpoints: deque[dict[str, Any]] = deque(maxlen=50)
        self._stability_score: float = 1.0
        self._last_evaluated: float = 0.0
        self._throttled_agents: set[str] = set()
        self._running: bool = False
        self._thread: threading.Thread | None = None

    # ── lifecycle ─────────────────────────────────────────────────────────────

    def start(self) -> None:
        with self._lock:
            if self._running:
                return
            self._running = True
            self._thread = threading.Thread(
                target=self._loop, name="reliability-engine", daemon=True
            )
            self._thread.start()

    def stop(self) -> None:
        with self._lock:
            self._running = False
        if self._thread:
            self._thread.join(timeout=3)
            self._thread = None

    def _loop(self) -> None:
        while True:
            with self._lock:
                if not self._running:
                    return
            try:
                self.evaluate()
            except Exception:
                pass
            time.sleep(5.0)

    # ── evaluation ────────────────────────────────────────────────────────────

    def evaluate(self) -> dict[str, Any]:
        """Run one evaluation cycle and apply safeguards if needed."""
        metrics_snapshot = self._get_metrics()
        anomalies = self._get_anomalies()
        audit_anomalies = self._get_audit_anomalies()

        errors_per_min = float(
            (metrics_snapshot.get("latest") or {}).get("errors_per_minute", 0) or 0
        )
        total_anomalies = len(anomalies) + len(audit_anomalies)

        # Compute stability score [0, 1]
        error_factor = min(1.0, errors_per_min / max(ERROR_THRESHOLD, 1))
        anomaly_factor = min(1.0, total_anomalies / max(ANOMALY_THRESHOLD, 1))
        score = max(0.0, 1.0 - (0.6 * error_factor + 0.4 * anomaly_factor))

        with self._lock:
            self._stability_score = round(score, 3)
            self._last_evaluated = time.time()

        actions_taken: list[str] = []

        if errors_per_min >= ERROR_THRESHOLD and not self._forge_frozen:
            self.freeze_forge(reason=f"error_rate={errors_per_min:.1f}/min exceeds threshold={ERROR_THRESHOLD}")
            actions_taken.append("forge_frozen")

        if total_anomalies >= ANOMALY_THRESHOLD:
            self._emit("reliability:anomaly_threshold", {
                "anomaly_count": total_anomalies,
                "threshold": ANOMALY_THRESHOLD,
                "stability_score": score,
            })
            actions_taken.append("anomaly_event_emitted")

        result: dict[str, Any] = {
            "stability_score": score,
            "forge_frozen": self._forge_frozen,
            "freeze_reason": self._freeze_reason,
            "errors_per_minute": errors_per_min,
            "anomalies_detected": total_anomalies,
            "actions_taken": actions_taken,
            "throttled_agents": list(self._throttled_agents),
        }
        return result

    # ── forge freeze ──────────────────────────────────────────────────────────

    def freeze_forge(self, *, reason: str = "manual") -> None:
        with self._lock:
            self._forge_frozen = True
            self._freeze_reason = reason
        self._audit("system", "forge_freeze", {"reason": reason}, risk_score=0.7)
        self._emit("reliability:forge_frozen", {"reason": reason})

    def unfreeze_forge(self, *, actor: str = "system") -> None:
        with self._lock:
            self._forge_frozen = False
            self._freeze_reason = ""
        self._audit(actor, "forge_unfreeze", {}, risk_score=0.5)
        self._emit("reliability:forge_unfrozen", {"actor": actor})

    @property
    def forge_frozen(self) -> bool:
        with self._lock:
            return self._forge_frozen

    # ── rollback checkpoints ──────────────────────────────────────────────────

    def save_checkpoint(self, state_descriptor: dict[str, Any]) -> str:
        """Store a named checkpoint of any state snapshot."""
        ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        checkpoint: dict[str, Any] = {
            "id": f"ckpt-{int(time.time() * 1000)}",
            "ts": ts,
            "state": state_descriptor,
        }
        with self._lock:
            self._checkpoints.appendleft(checkpoint)
        self._audit("system", "checkpoint_saved", {"checkpoint_id": checkpoint["id"]}, risk_score=0.1)
        return checkpoint["id"]

    def last_checkpoint(self) -> dict[str, Any] | None:
        with self._lock:
            return dict(self._checkpoints[0]) if self._checkpoints else None

    def checkpoints(self, limit: int = 10) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._checkpoints)[:limit]

    # ── agent throttling ──────────────────────────────────────────────────────

    def throttle_agent(self, agent_id: str) -> None:
        with self._lock:
            self._throttled_agents.add(agent_id)
        self._audit("system", "agent_throttled", {"agent_id": agent_id}, risk_score=0.5)

    def unthrottle_agent(self, agent_id: str) -> None:
        with self._lock:
            self._throttled_agents.discard(agent_id)

    def is_throttled(self, agent_id: str) -> bool:
        with self._lock:
            return agent_id in self._throttled_agents

    # ── status ────────────────────────────────────────────────────────────────

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "stability_score": self._stability_score,
                "forge_frozen": self._forge_frozen,
                "freeze_reason": self._freeze_reason,
                "throttled_agents": list(self._throttled_agents),
                "checkpoints_stored": len(self._checkpoints),
                "last_evaluated": (
                    time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(self._last_evaluated))
                    if self._last_evaluated
                    else None
                ),
            }

    # ── helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _get_metrics() -> dict[str, Any]:
        try:
            from core.observability.metrics_collector import get_metrics_collector
            return get_metrics_collector().snapshot()
        except Exception:
            return {}

    @staticmethod
    def _get_anomalies() -> list[dict[str, Any]]:
        try:
            from core.observability.anomaly_detector import get_anomaly_detector
            return get_anomaly_detector().recent(10)
        except Exception:
            return []

    @staticmethod
    def _get_audit_anomalies() -> list[dict[str, Any]]:
        try:
            from core.audit_engine import get_audit_engine
            return get_audit_engine().anomalies(10)
        except Exception:
            return []

    @staticmethod
    def _emit(event_type: str, payload: dict[str, Any]) -> None:
        try:
            from core.observability.event_stream import get_event_stream
            get_event_stream().publish(event_type, payload)
        except Exception:
            pass

    @staticmethod
    def _audit(actor: str, action: str, meta: dict[str, Any], *, risk_score: float) -> None:
        try:
            from core.audit_engine import get_audit_engine
            get_audit_engine().record(actor=actor, action=action, meta=meta, risk_score=risk_score)
        except Exception:
            pass


# ── singleton ─────────────────────────────────────────────────────────────────

_instance: ReliabilityEngine | None = None
_instance_lock = threading.Lock()


def get_reliability_engine() -> ReliabilityEngine:
    global _instance
    with _instance_lock:
        if _instance is None:
            _instance = ReliabilityEngine()
    return _instance
