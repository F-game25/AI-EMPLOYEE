"""Execution recorder — captures full execution trees for replay and debugging.

Every agent execution is captured as an ExecutionRecord with:
  - Decision trace (why the AI made each choice)
  - Span tree (what happened, in what order, how long)
  - Token accounting (per-LLM-call input/output)
  - Model attribution (which model answered which question)
  - Agent lineage (parent→child relationships)

Stored in JSONL at ~/.ai-employee/state/execution_log.jsonl
Queryable via ExecutionStore for replay debugging.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field, asdict
from pathlib import Path
from threading import RLock
from typing import Any, Optional

from infra.telemetry.otel import get_tracer, start_span

logger = logging.getLogger("telemetry.recorder")

_LOG_PATH = Path.home() / ".ai-employee" / "state" / "execution_log.jsonl"
_MAX_LOG_BYTES = 256 * 1024 * 1024  # 256MB


@dataclass
class TokenUsage:
    model_id: str
    input_tokens: int
    output_tokens: int
    cost_usd: float = 0.0
    latency_ms: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class DecisionPoint:
    id: str
    ts: float
    decision_type: str          # plan_selection | model_selection | routing | escalation | veto
    question: str
    chosen: str
    alternatives: list[str]
    rationale: str
    confidence: float

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ExecutionSpan:
    span_id: str
    parent_span_id: str | None
    name: str
    start_ts: float
    end_ts: float = 0.0
    status: str = "in_progress"   # in_progress | ok | error | timeout
    attributes: dict[str, Any] = field(default_factory=dict)
    events: list[dict] = field(default_factory=list)

    @property
    def duration_ms(self) -> float:
        return (self.end_ts - self.start_ts) * 1000 if self.end_ts else 0.0

    def to_dict(self) -> dict:
        d = asdict(self)
        d["duration_ms"] = self.duration_ms
        return d


@dataclass
class ExecutionRecord:
    """Complete execution record for one task lifecycle."""
    record_id: str
    trace_id: str
    task_id: str
    tenant_id: str
    agent_id: str
    parent_record_id: str | None        # for child workflows
    started_at: float
    completed_at: float = 0.0
    status: str = "running"             # running | success | failure | timeout | cancelled
    spans: list[ExecutionSpan] = field(default_factory=list)
    decisions: list[DecisionPoint] = field(default_factory=list)
    token_usage: list[TokenUsage] = field(default_factory=list)
    total_cost_usd: float = 0.0
    error: str = ""
    output_summary: str = ""
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "record_id": self.record_id,
            "trace_id": self.trace_id,
            "task_id": self.task_id,
            "tenant_id": self.tenant_id,
            "agent_id": self.agent_id,
            "parent_record_id": self.parent_record_id,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "status": self.status,
            "duration_ms": (self.completed_at - self.started_at) * 1000 if self.completed_at else 0,
            "spans": [s.to_dict() for s in self.spans],
            "decisions": [d.to_dict() for d in self.decisions],
            "token_usage": [t.to_dict() for t in self.token_usage],
            "total_cost_usd": self.total_cost_usd,
            "error": self.error,
            "output_summary": self.output_summary,
            "tags": self.tags,
        }


class ExecutionRecorder:
    """Thread-safe recorder; one instance per execution."""

    def __init__(
        self,
        task_id: str,
        tenant_id: str,
        agent_id: str,
        *,
        trace_id: str | None = None,
        parent_record_id: str | None = None,
    ) -> None:
        self._record = ExecutionRecord(
            record_id=str(uuid.uuid4()),
            trace_id=trace_id or str(uuid.uuid4()),
            task_id=task_id,
            tenant_id=tenant_id,
            agent_id=agent_id,
            parent_record_id=parent_record_id,
            started_at=time.time(),
        )
        self._lock = RLock()
        self._active_spans: dict[str, ExecutionSpan] = {}
        self._tracer = get_tracer("ai-employee.execution")

    # ── Span management ───────────────────────────────────────────────────────

    def start_span(self, name: str, parent_span_id: str | None = None, attributes: dict | None = None) -> str:
        span_id = str(uuid.uuid4())
        span = ExecutionSpan(
            span_id=span_id,
            parent_span_id=parent_span_id,
            name=name,
            start_ts=time.time(),
            attributes=attributes or {},
        )
        with self._lock:
            self._active_spans[span_id] = span
            self._record.spans.append(span)
        return span_id

    def end_span(self, span_id: str, status: str = "ok", error: str = "") -> None:
        with self._lock:
            span = self._active_spans.pop(span_id, None)
            if span:
                span.end_ts = time.time()
                span.status = status
                if error:
                    span.events.append({"name": "error", "ts": time.time(), "message": error})

    def add_span_event(self, span_id: str, event_name: str, attrs: dict | None = None) -> None:
        with self._lock:
            span = self._active_spans.get(span_id)
            if span:
                span.events.append({"name": event_name, "ts": time.time(), "attrs": attrs or {}})

    def set_span_attribute(self, span_id: str, key: str, value: Any) -> None:
        with self._lock:
            span = self._active_spans.get(span_id)
            if span:
                span.attributes[key] = value

    # ── Decision recording ────────────────────────────────────────────────────

    def record_decision(
        self,
        decision_type: str,
        question: str,
        chosen: str,
        alternatives: list[str] | None = None,
        rationale: str = "",
        confidence: float = 1.0,
    ) -> None:
        dp = DecisionPoint(
            id=str(uuid.uuid4()),
            ts=time.time(),
            decision_type=decision_type,
            question=question,
            chosen=chosen,
            alternatives=alternatives or [],
            rationale=rationale,
            confidence=confidence,
        )
        with self._lock:
            self._record.decisions.append(dp)

    # ── Token accounting ──────────────────────────────────────────────────────

    def record_token_usage(
        self,
        model_id: str,
        input_tokens: int,
        output_tokens: int,
        cost_usd: float = 0.0,
        latency_ms: float = 0.0,
    ) -> None:
        usage = TokenUsage(model_id=model_id, input_tokens=input_tokens,
                           output_tokens=output_tokens, cost_usd=cost_usd, latency_ms=latency_ms)
        with self._lock:
            self._record.token_usage.append(usage)
            self._record.total_cost_usd += cost_usd

    # ── Completion ────────────────────────────────────────────────────────────

    def complete(
        self,
        status: str = "success",
        output_summary: str = "",
        error: str = "",
        tags: list[str] | None = None,
    ) -> ExecutionRecord:
        with self._lock:
            # Close any still-open spans
            for span in self._active_spans.values():
                span.end_ts = time.time()
                span.status = "timeout" if not error else "error"
            self._active_spans.clear()
            self._record.completed_at = time.time()
            self._record.status = status
            self._record.output_summary = output_summary[:500]
            self._record.error = error[:500]
            if tags:
                self._record.tags = tags
        _get_store().append(self._record)
        return self._record

    @property
    def record(self) -> ExecutionRecord:
        return self._record

    @property
    def trace_id(self) -> str:
        return self._record.trace_id


class ExecutionStore:
    """Append-only JSONL store with query capabilities."""

    def __init__(self, path: Path = _LOG_PATH) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._path = path
        self._lock = RLock()
        self._in_memory: list[dict] = []  # recent records cache (last 500)
        self._load_recent()

    def append(self, record: ExecutionRecord) -> None:
        d = record.to_dict()
        with self._lock:
            self._in_memory.append(d)
            if len(self._in_memory) > 500:
                self._in_memory.pop(0)
            try:
                self._rotate_if_needed()
                with self._path.open("a") as f:
                    f.write(json.dumps(d) + "\n")
            except Exception as e:
                logger.error("ExecutionStore append failed: %s", e)

    def query(
        self,
        *,
        tenant_id: str | None = None,
        agent_id: str | None = None,
        task_id: str | None = None,
        trace_id: str | None = None,
        status: str | None = None,
        since_ts: float = 0.0,
        limit: int = 50,
    ) -> list[dict]:
        with self._lock:
            records = list(self._in_memory)
        results = []
        for r in reversed(records):
            if tenant_id and r.get("tenant_id") != tenant_id:
                continue
            if agent_id and r.get("agent_id") != agent_id:
                continue
            if task_id and r.get("task_id") != task_id:
                continue
            if trace_id and r.get("trace_id") != trace_id:
                continue
            if status and r.get("status") != status:
                continue
            if since_ts and r.get("started_at", 0) < since_ts:
                continue
            results.append(r)
            if len(results) >= limit:
                break
        return results

    def get_trace(self, trace_id: str) -> list[dict]:
        """Return all records sharing a trace_id (full distributed trace)."""
        return self.query(trace_id=trace_id, limit=100)

    def get_lineage(self, record_id: str) -> list[dict]:
        """Return record and all its descendants (child workflows)."""
        with self._lock:
            records = list(self._in_memory)
        result: list[dict] = []
        queue = [record_id]
        seen: set[str] = set()
        while queue:
            rid = queue.pop(0)
            if rid in seen:
                continue
            seen.add(rid)
            for r in records:
                if r.get("record_id") == rid or r.get("parent_record_id") == rid:
                    result.append(r)
                    if r.get("record_id") != rid:
                        queue.append(r["record_id"])
        return result

    def _load_recent(self) -> None:
        try:
            if not self._path.exists():
                return
            lines = self._path.read_text().strip().split("\n")
            for line in lines[-500:]:
                if line:
                    try:
                        self._in_memory.append(json.loads(line))
                    except Exception:
                        pass
        except Exception as e:
            logger.warning("ExecutionStore load failed: %s", e)

    def _rotate_if_needed(self) -> None:
        try:
            if self._path.exists() and self._path.stat().st_size > _MAX_LOG_BYTES:
                archive = self._path.with_suffix(f".{int(time.time())}.jsonl")
                self._path.rename(archive)
                logger.info("Rotated execution log → %s", archive)
        except Exception:
            pass


class AnomalyDetector:
    """Detects anomalous execution patterns in real time."""

    def __init__(self) -> None:
        self._latency_window: list[float] = []  # rolling last 100 durations
        self._error_window: list[bool] = []

    def analyze(self, record: ExecutionRecord) -> list[str]:
        """Return list of anomaly flags for this record."""
        flags: list[str] = []
        duration_ms = (record.completed_at - record.started_at) * 1000 if record.completed_at else 0

        # Latency anomaly
        self._latency_window.append(duration_ms)
        if len(self._latency_window) > 100:
            self._latency_window.pop(0)
        if len(self._latency_window) >= 10:
            avg = sum(self._latency_window[:-1]) / (len(self._latency_window) - 1)
            if duration_ms > avg * 3:
                flags.append(f"latency_spike:{duration_ms:.0f}ms_vs_avg_{avg:.0f}ms")

        # Error pattern
        self._error_window.append(record.status != "success")
        if len(self._error_window) > 20:
            self._error_window.pop(0)
        if len(self._error_window) >= 5:
            error_rate = sum(self._error_window) / len(self._error_window)
            if error_rate > 0.5:
                flags.append(f"high_error_rate:{error_rate:.0%}")

        # Token burst
        total_tokens = sum(u.input_tokens + u.output_tokens for u in record.token_usage)
        if total_tokens > 50000:
            flags.append(f"token_burst:{total_tokens}")

        # Cost spike
        if record.total_cost_usd > 5.0:
            flags.append(f"cost_spike:${record.total_cost_usd:.2f}")

        return flags


_store: ExecutionStore | None = None
_detector = AnomalyDetector()


def _get_store() -> ExecutionStore:
    global _store
    if _store is None:
        _store = ExecutionStore()
    return _store


def get_execution_store() -> ExecutionStore:
    return _get_store()


def get_anomaly_detector() -> AnomalyDetector:
    return _detector
