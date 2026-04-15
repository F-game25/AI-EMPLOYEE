from __future__ import annotations

import threading
import time
import uuid
from typing import Any

from core.observability.event_stream import EventStream, get_event_stream


class TraceLogger:
    """Distributed tracing helper for task execution flow."""

    def __init__(self, stream: EventStream | None = None) -> None:
        self._stream = stream or get_event_stream()
        self._lock = threading.RLock()
        self._traces: dict[str, dict[str, Any]] = {}

    @staticmethod
    def _ts() -> str:
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    def start_trace(self, *, user_input: str, intent: str, metadata: dict[str, Any] | None = None) -> str:
        trace_id = f"trace-{uuid.uuid4().hex[:12]}"
        row = {
            "trace_id": trace_id,
            "started_at": self._ts(),
            "user_input": user_input,
            "intent": intent,
            "metadata": metadata or {},
            "steps": [],
            "result": None,
        }
        with self._lock:
            self._traces[trace_id] = row
        self._stream.publish(
            "task_started",
            {
                "user_input": user_input,
                "intent": intent,
                "metadata": metadata or {},
            },
            trace_id=trace_id,
        )
        return trace_id

    def step(self, trace_id: str, step_name: str, payload: dict[str, Any] | None = None) -> None:
        event_payload = {"step": step_name, **(payload or {})}
        with self._lock:
            trace = self._traces.get(trace_id)
            if trace is not None:
                trace["steps"].append({"ts": self._ts(), **event_payload})
        self._stream.publish("step_progress", event_payload, trace_id=trace_id)

    def decision(self, trace_id: str, *, reason: str, confidence: float, agent: str) -> None:
        self._stream.publish(
            "brain_decision",
            {
                "reason": reason,
                "confidence": float(confidence),
                "agent": agent,
            },
            trace_id=trace_id,
        )
        self._stream.publish(
            "agent_selected",
            {
                "agent": agent,
                "confidence": float(confidence),
            },
            trace_id=trace_id,
        )

    def complete(self, trace_id: str, *, result: dict[str, Any] | None = None, error: str = "") -> None:
        with self._lock:
            trace = self._traces.get(trace_id)
            if trace is not None:
                trace["result"] = result or {}
                trace["error"] = error
                trace["completed_at"] = self._ts()
        event_name = "task_completed" if not error else "error_detected"
        self._stream.publish(
            event_name,
            {
                "result": result or {},
                "error": error,
            },
            trace_id=trace_id,
        )

    def get_trace(self, trace_id: str) -> dict[str, Any] | None:
        with self._lock:
            trace = self._traces.get(trace_id)
            return dict(trace) if trace else None


_instance: TraceLogger | None = None
_instance_lock = threading.Lock()


def get_trace_logger() -> TraceLogger:
    global _instance
    with _instance_lock:
        if _instance is None:
            _instance = TraceLogger()
    return _instance
