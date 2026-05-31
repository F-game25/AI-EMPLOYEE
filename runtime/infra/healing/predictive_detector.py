"""Predictive failure detector — rolling z-score + EWMA trend."""
from __future__ import annotations
import asyncio
import logging
import math
import time
from collections import defaultdict, deque
from typing import Optional

from .schema import FailurePrediction

logger = logging.getLogger(__name__)

_WINDOW = 60        # rolling data points
_Z_THRESHOLD = 2.5
_EWMA_ALPHA = 0.1
_HORIZON_MIN = 15
_POLL_INTERVAL = 30  # seconds


class PredictiveDetector:
    def __init__(self):
        self._windows: dict[str, deque] = defaultdict(lambda: deque(maxlen=_WINDOW))
        self._ewma: dict[str, float] = {}
        self._predictions: list[FailurePrediction] = []

    def record(self, service: str, metric_name: str, value: float) -> Optional[FailurePrediction]:
        key = f"{service}:{metric_name}"
        window = self._windows[key]
        window.append(value)

        # EWMA update
        prev = self._ewma.get(key, value)
        self._ewma[key] = _EWMA_ALPHA * value + (1 - _EWMA_ALPHA) * prev

        if len(window) < 10:
            return None

        mean = sum(window) / len(window)
        var = sum((x - mean) ** 2 for x in window) / len(window)
        std = math.sqrt(var) if var > 0 else 1e-9
        z = (value - mean) / std

        if abs(z) >= _Z_THRESHOLD:
            prob = min(1.0, abs(z) / 5.0)
            pred = FailurePrediction(
                service=service,
                probability=round(prob, 3),
                horizon_minutes=_HORIZON_MIN,
                metric=metric_name,
                z_score=round(z, 2),
            )
            self._predictions.append(pred)
            # Keep only last 100
            if len(self._predictions) > 100:
                self._predictions = self._predictions[-100:]
            logger.warning("Prediction: %s %s z=%.2f prob=%.2f",
                           service, metric_name, z, prob)
            self._fire_ws_event(pred)
            return pred
        return None

    def get_predictions(self, limit: int = 20) -> list[dict]:
        return [
            {"service": p.service, "probability": p.probability,
             "metric": p.metric, "z_score": p.z_score,
             "horizon_minutes": p.horizon_minutes, "predicted_at": p.predicted_at}
            for p in self._predictions[-limit:]
        ]

    async def start_poll_loop(self) -> None:
        while True:
            await asyncio.sleep(_POLL_INTERVAL)
            self._collect_metrics()

    def _collect_metrics(self) -> None:
        try:
            import os
            with open("/proc/loadavg") as f:
                load1 = float(f.read().split()[0])
            self.record("system", "load1", load1)
        except Exception:
            pass
        try:
            from infra.telemetry.execution_recorder import get_execution_store
            store = get_execution_store()
            recent = store.query(limit=20)
            if recent:
                lats = [r.get("duration_ms", 0) for r in recent if r.get("duration_ms")]
                if lats:
                    self.record("ai_backend", "latency_ms", sum(lats) / len(lats))
        except Exception:
            pass

    @staticmethod
    def _fire_ws_event(pred: FailurePrediction) -> None:
        try:
            from infra.events.bus import get_event_bus
            import asyncio
            bus = get_event_bus()
            asyncio.create_task(bus.publish("healing:prediction", {
                "service": pred.service,
                "probability": pred.probability,
                "metric": pred.metric,
                "horizon_minutes": pred.horizon_minutes,
            }))
        except Exception:
            pass


_detector: Optional[PredictiveDetector] = None


def get_predictive_detector() -> PredictiveDetector:
    global _detector
    if _detector is None:
        _detector = PredictiveDetector()
    return _detector
