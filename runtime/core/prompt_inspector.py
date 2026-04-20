"""Prompt Inspector — Live observability for the AI pipeline.

Captures a structured ``PromptTrace`` at every stage of the request pipeline:
  raw_input → preprocessing → context_injection → prompt_build →
  llm_call → response_processing → action_execution

Usage::

    from core.prompt_inspector import get_prompt_inspector

    inspector = get_prompt_inspector()
    trace = inspector.start_trace(user_input="Hello")
    inspector.set_context(trace.id, context_used="...")
    inspector.set_prompt(trace.id, constructed_prompt="...")
    inspector.set_model_output(trace.id, model_raw_output="...")
    inspector.finish_trace(trace.id, final_output="...", actions_triggered=["agent:hermes"])

Environment variables:
    PROMPT_INSPECTOR_ENABLED  — "1" to enable (default: "1")
    PROMPT_INSPECTOR_SAMPLE   — float 0.0–1.0 fraction to capture (default: "1.0")
    PROMPT_INSPECTOR_MAX      — max traces kept in memory (default: "200")
"""
from __future__ import annotations

import os
import random
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


# ── Configuration ─────────────────────────────────────────────────────────────

def _env_bool(key: str, default: bool) -> bool:
    v = os.environ.get(key, "").strip().lower()
    if v in ("1", "true", "yes", "on"):
        return True
    if v in ("0", "false", "no", "off"):
        return False
    return default


def _env_float(key: str, default: float) -> float:
    try:
        return float(os.environ.get(key, str(default)))
    except (TypeError, ValueError):
        return default


def _env_int(key: str, default: int) -> int:
    try:
        return int(os.environ.get(key, str(default)))
    except (TypeError, ValueError):
        return default


# ── Data structure ─────────────────────────────────────────────────────────────

@dataclass
class PromptTrace:
    """Unified trace object capturing all pipeline stages for one AI request."""

    id: str
    timestamp: str                    # ISO-8601 UTC
    user_input: str                   # raw user message
    context_used: str = ""            # injected memory / context block
    constructed_prompt: str = ""      # full system-prompt + user message
    model_raw_output: str = ""        # response directly from LLM
    final_output: str = ""            # post-processed response sent to user
    actions_triggered: List[str] = field(default_factory=list)
    execution_status: str = "pending" # pending | ok | error | fallback
    agent: str = ""                   # routed agent id
    provider: str = ""                # llm provider (groq/openai/anthropic/ollama)
    model: str = ""                   # model name
    flags: List[str] = field(default_factory=list)  # missing_context, empty_prompt, generic_output
    error: Optional[str] = None       # error detail if execution_status == "error"
    duration_ms: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "user_input": self.user_input,
            "context_used": self.context_used,
            "constructed_prompt": self.constructed_prompt,
            "model_raw_output": self.model_raw_output,
            "final_output": self.final_output,
            "actions_triggered": self.actions_triggered,
            "execution_status": self.execution_status,
            "agent": self.agent,
            "provider": self.provider,
            "model": self.model,
            "flags": self.flags,
            "error": self.error,
            "duration_ms": self.duration_ms,
        }

    def summary(self) -> Dict[str, Any]:
        """Lightweight summary for list views."""
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "user_input": self.user_input[:120],
            "agent": self.agent,
            "provider": self.provider,
            "execution_status": self.execution_status,
            "flags": self.flags,
            "duration_ms": self.duration_ms,
        }


# ── Inspector singleton ────────────────────────────────────────────────────────

class PromptInspector:
    """Thread-safe in-memory store for PromptTrace objects.

    Keeps at most ``max_traces`` entries (oldest evicted first).
    Respects ``enabled`` toggle and ``sample_rate`` to avoid overhead.
    """

    def __init__(
        self,
        enabled: bool = True,
        sample_rate: float = 1.0,
        max_traces: int = 200,
    ) -> None:
        self._enabled = enabled
        self._sample_rate = max(0.0, min(1.0, sample_rate))
        self._max_traces = max(1, max_traces)
        self._traces: Dict[str, PromptTrace] = {}
        self._order: List[str] = []  # insertion order
        self._lock = threading.Lock()
        self._start_times: Dict[str, float] = {}

    # ── Configuration ──────────────────────────────────────────────────────────

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._enabled = bool(value)

    @property
    def sample_rate(self) -> float:
        return self._sample_rate

    @sample_rate.setter
    def sample_rate(self, value: float) -> None:
        self._sample_rate = max(0.0, min(1.0, float(value)))

    # ── Pipeline hooks ─────────────────────────────────────────────────────────

    def start_trace(self, user_input: str) -> Optional[PromptTrace]:
        """Begin a new trace; returns None when disabled or sampled out."""
        if not self._enabled:
            return None
        if self._sample_rate < 1.0 and random.random() > self._sample_rate:
            return None

        trace_id = f"pt-{uuid.uuid4().hex[:16]}"
        ts = datetime.now(timezone.utc).isoformat()
        trace = PromptTrace(id=trace_id, timestamp=ts, user_input=user_input)

        import time as _time
        with self._lock:
            self._traces[trace_id] = trace
            self._order.append(trace_id)
            self._start_times[trace_id] = _time.monotonic()
            # Evict oldest if over capacity
            while len(self._order) > self._max_traces:
                old_id = self._order.pop(0)
                self._traces.pop(old_id, None)
                self._start_times.pop(old_id, None)

        return trace

    def set_context(self, trace_id: str, context_used: str) -> None:
        """Record the injected context/memory block."""
        trace = self._get(trace_id)
        if trace is None:
            return
        with self._lock:
            trace.context_used = context_used
            if not context_used.strip():
                if "missing_context" not in trace.flags:
                    trace.flags.append("missing_context")

    def set_prompt(self, trace_id: str, constructed_prompt: str) -> None:
        """Record the fully-constructed prompt sent to the LLM."""
        trace = self._get(trace_id)
        if trace is None:
            return
        with self._lock:
            trace.constructed_prompt = constructed_prompt
            if not constructed_prompt.strip():
                if "empty_prompt" not in trace.flags:
                    trace.flags.append("empty_prompt")

    def set_agent(self, trace_id: str, agent: str, provider: str = "", model: str = "") -> None:
        """Record routing metadata."""
        trace = self._get(trace_id)
        if trace is None:
            return
        with self._lock:
            trace.agent = agent
            trace.provider = provider
            trace.model = model

    def set_model_output(self, trace_id: str, model_raw_output: str) -> None:
        """Record the raw LLM response before any post-processing."""
        trace = self._get(trace_id)
        if trace is None:
            return
        with self._lock:
            trace.model_raw_output = model_raw_output
            # Detect generic / empty output
            if not model_raw_output.strip():
                if "empty_output" not in trace.flags:
                    trace.flags.append("empty_output")

    def finish_trace(
        self,
        trace_id: str,
        final_output: str,
        actions_triggered: Optional[List[str]] = None,
        execution_status: str = "ok",
        error: Optional[str] = None,
    ) -> None:
        """Finalise a trace after the full pipeline completes."""
        import time as _time
        trace = self._get(trace_id)
        if trace is None:
            return
        with self._lock:
            trace.final_output = final_output
            trace.actions_triggered = list(actions_triggered or [])
            trace.execution_status = execution_status
            trace.error = error

            # Detect generic/fallback output
            _generic_markers = (
                "I'm working on that",
                "Check dashboard for results",
                "Task is taking longer",
                "No model is available",
                "No model response was returned",
            )
            if any(m in final_output for m in _generic_markers):
                if "generic_output" not in trace.flags:
                    trace.flags.append("generic_output")

            start = self._start_times.pop(trace_id, None)
            if start is not None:
                trace.duration_ms = round((_time.monotonic() - start) * 1000, 1)

    def set_error(self, trace_id: str, error: str) -> None:
        """Mark a trace as failed."""
        trace = self._get(trace_id)
        if trace is None:
            return
        with self._lock:
            trace.execution_status = "error"
            trace.error = error
            if "error" not in trace.flags:
                trace.flags.append("error")

    # ── Retrieval ──────────────────────────────────────────────────────────────

    def get_trace(self, trace_id: str) -> Optional[Dict[str, Any]]:
        trace = self._get(trace_id)
        return trace.to_dict() if trace is not None else None

    def list_traces(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._lock:
            ids = list(reversed(self._order))[:limit]
            return [self._traces[i].summary() for i in ids if i in self._traces]

    def clear(self) -> None:
        with self._lock:
            self._traces.clear()
            self._order.clear()
            self._start_times.clear()

    def count(self) -> int:
        with self._lock:
            return len(self._traces)

    def status(self) -> Dict[str, Any]:
        return {
            "enabled": self._enabled,
            "sample_rate": self._sample_rate,
            "max_traces": self._max_traces,
            "stored_traces": self.count(),
        }

    # ── Internal ───────────────────────────────────────────────────────────────

    def _get(self, trace_id: str) -> Optional[PromptTrace]:
        with self._lock:
            return self._traces.get(trace_id)


# ── Module-level singleton ────────────────────────────────────────────────────

_inspector: Optional[PromptInspector] = None
_inspector_lock = threading.Lock()


def get_prompt_inspector() -> PromptInspector:
    """Return the global PromptInspector singleton (lazy-initialised)."""
    global _inspector
    if _inspector is None:
        with _inspector_lock:
            if _inspector is None:
                _inspector = PromptInspector(
                    enabled=_env_bool("PROMPT_INSPECTOR_ENABLED", True),
                    sample_rate=_env_float("PROMPT_INSPECTOR_SAMPLE", 1.0),
                    max_traces=_env_int("PROMPT_INSPECTOR_MAX", 200),
                )
    return _inspector
