"""Model drift and performance monitoring — periodic evaluation against baseline."""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Optional

logger = logging.getLogger("ai_employee.drift_monitor")


@dataclass
class DriftMetrics:
    model: str
    window_hours: int
    sample_count: int
    avg_latency_ms: float
    p95_latency_ms: float
    error_rate: float
    avg_cost_per_call: float
    safety_flag_rate: float
    ts: str


def _compute_p95(values: list[float]) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    idx = max(0, int(len(s) * 0.95) - 1)
    return s[idx]


class DriftMonitor:
    _timer: threading.Timer | None = None
    _timer_lock = threading.Lock()

    def compute_metrics(self, model: str | None = None, window_hours: int = 24) -> list[DriftMetrics]:
        from core.model_decision_audit import get_model_audit

        cutoff = (datetime.now(timezone.utc) - timedelta(hours=window_hours)).isoformat()
        records = get_model_audit().get_recent(limit=5000)
        records = [r for r in records if r.get("ts", "") >= cutoff]

        if model:
            records = [r for r in records if r.get("model") == model]

        # Group by model
        by_model: dict[str, list[dict]] = {}
        for r in records:
            m = r.get("model", "unknown")
            by_model.setdefault(m, []).append(r)

        results: list[DriftMetrics] = []
        ts = datetime.now(timezone.utc).isoformat()

        for m, recs in by_model.items():
            latencies = [r.get("latency_ms", 0.0) for r in recs]
            errors = sum(1 for r in recs if r.get("outcome") == "error")
            costs = [r.get("cost_usd", 0.0) for r in recs]
            flagged = sum(1 for r in recs if r.get("safety_flags"))
            n = len(recs)

            results.append(DriftMetrics(
                model=m,
                window_hours=window_hours,
                sample_count=n,
                avg_latency_ms=round(sum(latencies) / n, 2) if n else 0.0,
                p95_latency_ms=round(_compute_p95(latencies), 2),
                error_rate=round(errors / n, 4) if n else 0.0,
                avg_cost_per_call=round(sum(costs) / n, 6) if n else 0.0,
                safety_flag_rate=round(flagged / n, 4) if n else 0.0,
                ts=ts,
            ))

        return results

    def detect_drift(self, baseline_window_hours: int = 168, current_window_hours: int = 24) -> list[dict]:
        baseline = {m.model: m for m in self.compute_metrics(window_hours=baseline_window_hours)}
        current = {m.model: m for m in self.compute_metrics(window_hours=current_window_hours)}

        alerts: list[dict] = []
        _ALERT_METRICS = {
            "avg_latency_ms": 0.20,
            "error_rate": 0.20,
            "safety_flag_rate": 0.20,
        }

        for model, cur in current.items():
            base = baseline.get(model)
            if not base or base.sample_count == 0:
                continue
            for metric, threshold in _ALERT_METRICS.items():
                base_val = getattr(base, metric, 0.0)
                cur_val = getattr(cur, metric, 0.0)
                if base_val == 0.0:
                    change_pct = 0.0
                else:
                    change_pct = (cur_val - base_val) / base_val

                fire = abs(change_pct) > threshold
                alerts.append({
                    "model": model,
                    "metric": metric,
                    "baseline_value": round(base_val, 6),
                    "current_value": round(cur_val, 6),
                    "change_pct": round(change_pct * 100, 2),
                    "alert": fire,
                })

        return alerts

    def get_report(self) -> dict:
        metrics = self.compute_metrics()
        drift_alerts = self.detect_drift()
        fired = [a for a in drift_alerts if a["alert"]]
        return {
            "models": [
                {
                    "model": m.model,
                    "window_hours": m.window_hours,
                    "sample_count": m.sample_count,
                    "avg_latency_ms": m.avg_latency_ms,
                    "p95_latency_ms": m.p95_latency_ms,
                    "error_rate": m.error_rate,
                    "avg_cost_per_call": m.avg_cost_per_call,
                    "safety_flag_rate": m.safety_flag_rate,
                }
                for m in metrics
            ],
            "alerts": drift_alerts,
            "active_alerts": fired,
            "computed_at": datetime.now(timezone.utc).isoformat(),
        }

    def schedule_check(self, interval_hours: int = 6) -> None:
        with DriftMonitor._timer_lock:
            if DriftMonitor._timer is not None:
                return  # already running

        def _run() -> None:
            try:
                result = self.detect_drift()
                fired = [a for a in result if a["alert"]]
                if fired:
                    logger.warning("drift_monitor: %d drift alerts fired: %s", len(fired), fired)
                else:
                    logger.info("drift_monitor: check complete, no alerts")
            except Exception as exc:
                logger.warning("drift_monitor: check failed: %s", exc)
            finally:
                with DriftMonitor._timer_lock:
                    DriftMonitor._timer = None
                # Reschedule
                self.schedule_check(interval_hours)

        with DriftMonitor._timer_lock:
            DriftMonitor._timer = threading.Timer(interval_hours * 3600, _run)
            DriftMonitor._timer.daemon = True
            DriftMonitor._timer.start()
        logger.info("drift_monitor: scheduled check every %dh", interval_hours)
