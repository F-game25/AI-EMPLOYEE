from __future__ import annotations

import sys
from pathlib import Path

_RUNTIME = Path(__file__).resolve().parent.parent / "runtime"
if str(_RUNTIME) not in sys.path:
    sys.path.insert(0, str(_RUNTIME))

from core.observability.anomaly_detector import AnomalyDetector
from core.observability.event_stream import EventStream
from core.observability.metrics_collector import MetricsCollector
from core.observability.trace_logger import TraceLogger


def test_event_stream_publishes_and_reads(tmp_path):
    stream = EventStream(db_path=tmp_path / "events.db")
    stream.publish("task_started", {"task_id": "t-1"}, trace_id="trace-1")
    recent = stream.recent(10)
    assert recent
    assert recent[0]["event_type"] == "task_started"


def test_trace_logger_emits_required_events(tmp_path):
    stream = EventStream(db_path=tmp_path / "events.db")
    logger = TraceLogger(stream=stream)
    trace_id = logger.start_trace(user_input="find leads", intent="lead_generation")
    logger.decision(trace_id, reason="lead intent", confidence=0.91, agent="lead_hunter")
    logger.step(trace_id, "execute", {"task_id": "t-2"})
    logger.complete(trace_id, result={"ok": True})
    event_types = [item["event_type"] for item in stream.recent(20)]
    assert "task_started" in event_types
    assert "brain_decision" in event_types
    assert "agent_selected" in event_types
    assert "step_progress" in event_types
    assert "task_completed" in event_types


def test_metrics_and_anomaly_detection(tmp_path):
    stream = EventStream(db_path=tmp_path / "events.db")
    metrics = MetricsCollector(stream=stream)
    for _ in range(6):
        metrics.record_error()
    snap = metrics.collect_once()
    assert "cpu_percent" in snap
    detector = AnomalyDetector(metrics=metrics, stream=stream)
    anomalies = detector.detect()
    assert any(item["type"] == "sudden_error_spike" for item in anomalies)
