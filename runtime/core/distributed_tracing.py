"""Distributed Tracing for ASCEND AI.

Provides end-to-end trace propagation across all subsystems — orchestrator,
agent routing, LLM calls, and memory writes — with optional OpenTelemetry
export for production observability back-ends.

────────────────────────────────────────────────────────────────
ARCHITECTURE
────────────────────────────────────────────────────────────────

Every incoming request receives a unique *trace_id* that is stored in a
process-wide ``contextvars.ContextVar``.  Because asyncio and
``run_in_executor`` (the threadpool backing ``run_in_threadpool``) both copy
the current context when scheduling work, the trace_id propagates
automatically through:

  ┌─ post_chat (async) ───────────────── trace_id set ──────────────────┐
  │   run_in_threadpool(handle_command)  ← context copied into thread   │
  │     _generate_llm_response          ← same thread, same context     │
  │   on_exchange (memory write)        ← back in async, same context   │
  └─────────────────────────────────────────────────────────────────────┘

Each significant operation adds a *span* to the trace.  Spans form a tree
via ``parent_span_id``.  The complete tree is accessible via
``get_distributed_tracer().get_trace(trace_id)``.

────────────────────────────────────────────────────────────────
OPENTELEMETRY INTEGRATION
────────────────────────────────────────────────────────────────

When ``opentelemetry-sdk`` is importable the tracer also records spans via
the OTel SDK.  Export is controlled by environment variables:

  OTEL_EXPORTER_OTLP_ENDPOINT  — gRPC endpoint (e.g. http://jaeger:4317)
  OTEL_SERVICE_NAME             — service name tag (default: ascend-ai)

Without the env-var the InMemorySpanExporter is used (spans queryable via
``get_otel_spans()``).  If the SDK is not installed at all, the tracer
falls back gracefully to pure-Python in-memory spans — no functionality is
lost.

────────────────────────────────────────────────────────────────
PUBLIC API
────────────────────────────────────────────────────────────────

::

    from core.distributed_tracing import (
        get_distributed_tracer,
        get_current_trace_id,
        set_current_trace_id,
        SpanKind,
    )

    tracer = get_distributed_tracer()

    # Start a root trace (typically done at request entry)
    trace_id = tracer.start_trace(name="chat_request", attributes={"user": uid})

    # Add a child span anywhere in the call tree — no trace_id arg needed
    with tracer.span("llm_call", kind=SpanKind.LLM, attributes={"model": "gpt-4o"}):
        answer = call_openai(...)

    # Retrieve the full trace tree
    tree = tracer.get_trace(trace_id)
"""
from __future__ import annotations

import contextvars
import logging
import threading
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Generator, Optional

logger = logging.getLogger("ai_employee.distributed_tracing")

import os as _os

# ── ContextVar — carries the active trace across async / thread boundaries ───

_TRACE_CTX: contextvars.ContextVar[str] = contextvars.ContextVar(
    "ascend_trace_id", default=""
)


def get_current_trace_id() -> str:
    """Return the trace_id active in the current context, or '' if none."""
    return _TRACE_CTX.get("")


def set_current_trace_id(trace_id: str) -> contextvars.Token[str]:
    """Set the active trace_id and return a token for ``reset()``."""
    return _TRACE_CTX.set(trace_id)


# ── SpanKind ──────────────────────────────────────────────────────────────────

class SpanKind(str, Enum):
    INTERNAL  = "internal"
    SERVER    = "server"
    CLIENT    = "client"
    LLM       = "llm"
    MEMORY    = "memory"
    DATABASE  = "database"
    AGENT     = "agent"


# ── Span ──────────────────────────────────────────────────────────────────────

@dataclass
class Span:
    """A single unit of work within a trace.

    Attributes:
        span_id:      16-char hex unique within this process.
        trace_id:     The root trace this span belongs to.
        parent_span_id: Parent span_id, or '' for root spans.
        name:         Human-readable operation name.
        kind:         SpanKind classification.
        attributes:   Arbitrary key-value annotations.
        start_time:   Monotonic start (seconds since epoch).
        end_time:     Monotonic end, or None if still active.
        status:       "ok" | "error"
        error:        Error message if status == "error".
    """
    span_id:         str
    trace_id:        str
    parent_span_id:  str
    name:            str
    kind:            SpanKind
    attributes:      dict[str, Any] = field(default_factory=dict)
    start_time:      float          = field(default_factory=time.monotonic)
    end_time:        Optional[float] = None
    status:          str            = "ok"
    error:           str            = ""

    def finish(self, *, error: str = "") -> None:
        self.end_time = time.monotonic()
        if error:
            self.status = "error"
            self.error  = error

    @property
    def duration_ms(self) -> Optional[float]:
        if self.end_time is None:
            return None
        return round((self.end_time - self.start_time) * 1000, 2)

    def to_dict(self) -> dict[str, Any]:
        return {
            "span_id":        self.span_id,
            "trace_id":       self.trace_id,
            "parent_span_id": self.parent_span_id,
            "name":           self.name,
            "kind":           self.kind.value,
            "attributes":     self.attributes,
            "duration_ms":    self.duration_ms,
            "status":         self.status,
            "error":          self.error,
        }


# ── TraceRecord ───────────────────────────────────────────────────────────────

@dataclass
class TraceRecord:
    """Container for all spans that share a trace_id."""
    trace_id:   str
    name:       str
    started_at: str
    attributes: dict[str, Any] = field(default_factory=dict)
    spans:      list[Span]     = field(default_factory=list)
    completed:  bool           = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "trace_id":   self.trace_id,
            "name":       self.name,
            "started_at": self.started_at,
            "attributes": self.attributes,
            "spans":      [s.to_dict() for s in self.spans],
            "completed":  self.completed,
            "span_count": len(self.spans),
        }


# ── OpenTelemetry bridge (optional) ──────────────────────────────────────────

_otel_tracer: Any = None
_otel_mem_exporter: Any = None
_otel_available: bool = False


def _init_otel(service_name: str) -> None:
    """Attempt to initialise the OTel SDK. Silent no-op if unavailable."""
    global _otel_tracer, _otel_mem_exporter, _otel_available
    try:
        from opentelemetry import trace as _trace  # type: ignore
        from opentelemetry.sdk.trace import TracerProvider  # type: ignore
        from opentelemetry.sdk.resources import Resource  # type: ignore

        resource = Resource.create({"service.name": service_name})
        provider = TracerProvider(resource=resource)

        otlp_endpoint = _os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "")
        if otlp_endpoint:
            try:
                from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (  # type: ignore
                    OTLPSpanExporter,
                )
                from opentelemetry.sdk.trace.export import BatchSpanProcessor  # type: ignore
                provider.add_span_processor(
                    BatchSpanProcessor(OTLPSpanExporter(endpoint=otlp_endpoint))
                )
                logger.info("OTel OTLP exporter → %s", otlp_endpoint)
            except Exception as _otlp_exc:
                logger.debug("OTel OTLP exporter not available: %s", _otlp_exc)

        # Always attach an in-memory exporter for /api/traces queries
        from opentelemetry.sdk.trace.export.in_memory_span_exporter import (  # type: ignore
            InMemorySpanExporter,
        )
        from opentelemetry.sdk.trace.export import SimpleSpanProcessor  # type: ignore
        _otel_mem_exporter = InMemorySpanExporter()
        provider.add_span_processor(SimpleSpanProcessor(_otel_mem_exporter))

        _trace.set_tracer_provider(provider)
        _otel_tracer = _trace.get_tracer(service_name)
        _otel_available = True
        logger.info("OpenTelemetry SDK initialised (service=%s)", service_name)
    except ImportError:
        logger.info("opentelemetry-sdk not installed — using pure-Python spans")
    except Exception as exc:
        logger.warning("OTel init failed (non-fatal): %s", exc)


def get_otel_spans() -> list[dict[str, Any]]:
    """Return all in-memory OTel spans as dicts (for testing / debugging)."""
    if _otel_mem_exporter is None:
        return []
    try:
        spans = _otel_mem_exporter.get_finished_spans()
        out = []
        for s in spans:
            tid = format(s.context.trace_id, "032x") if s.context else ""
            sid = format(s.context.span_id, "016x") if s.context else ""
            out.append({
                "name":       s.name,
                "trace_id":   tid,
                "span_id":    sid,
                "status":     s.status.status_code.name if s.status else "UNSET",
                "attributes": dict(s.attributes or {}),
            })
        return out
    except Exception:
        return []


# ── DistributedTracer ─────────────────────────────────────────────────────────

_SPAN_CTX: contextvars.ContextVar[str] = contextvars.ContextVar(
    "ascend_span_id", default=""
)


class DistributedTracer:
    """Process-wide distributed tracer.

    Maintains a registry of in-flight and completed traces (up to
    ``max_traces``).  All spans are stored in the ``TraceRecord`` for their
    trace_id and also forwarded to the OTel SDK when available.

    Thread-safe — can be called from asyncio tasks and thread-pool workers
    simultaneously.
    """

    def __init__(
        self,
        *,
        service_name: str = "ascend-ai",
        max_traces:   int = 500,
    ) -> None:
        self._service_name = service_name
        self._max_traces   = max_traces
        self._lock         = threading.RLock()
        self._traces:  dict[str, TraceRecord] = {}
        self._ordered: list[str]              = []   # insertion order for eviction

        _init_otel(service_name)

    # ── Trace lifecycle ───────────────────────────────────────────────────────

    def start_trace(
        self,
        name:       str,
        *,
        attributes: dict[str, Any] | None = None,
    ) -> str:
        """Create a new root trace and activate it in the current context.

        Returns the new ``trace_id``.
        """
        trace_id = f"trace-{uuid.uuid4().hex}"
        record = TraceRecord(
            trace_id=trace_id,
            name=name,
            started_at=_iso_now(),
            attributes=attributes or {},
        )
        with self._lock:
            self._traces[trace_id] = record
            self._ordered.append(trace_id)
            # Evict oldest if over capacity
            while len(self._ordered) > self._max_traces:
                oldest = self._ordered.pop(0)
                self._traces.pop(oldest, None)

        set_current_trace_id(trace_id)
        # Clear any stale parent-span from a previous request
        _SPAN_CTX.set("")

        # Add the root span immediately and make it the active parent span
        root_span = self._add_span(
            trace_id=trace_id,
            name=name,
            kind=SpanKind.SERVER,
            attributes=attributes or {},
            parent_span_id="",
        )
        _SPAN_CTX.set(root_span.span_id)
        return trace_id

    def finish_trace(self, trace_id: str) -> None:
        """Mark the trace as completed."""
        with self._lock:
            record = self._traces.get(trace_id)
            if record is not None:
                record.completed = True

    def get_trace(self, trace_id: str) -> dict[str, Any] | None:
        """Return the full trace tree as a dict, or None if not found."""
        with self._lock:
            record = self._traces.get(trace_id)
            return record.to_dict() if record else None

    def list_traces(self, limit: int = 50) -> list[dict[str, Any]]:
        """Return the most recent traces (summary only, no spans)."""
        with self._lock:
            recent = list(reversed(self._ordered))[:limit]
            out = []
            for tid in recent:
                rec = self._traces.get(tid)
                if rec:
                    out.append({
                        "trace_id":   rec.trace_id,
                        "name":       rec.name,
                        "started_at": rec.started_at,
                        "span_count": len(rec.spans),
                        "completed":  rec.completed,
                    })
            return out

    # ── Span creation ─────────────────────────────────────────────────────────

    @contextmanager
    def span(
        self,
        name:       str,
        *,
        kind:       SpanKind              = SpanKind.INTERNAL,
        attributes: dict[str, Any] | None = None,
        trace_id:   str                   = "",
    ) -> Generator[Span, None, None]:
        """Context manager that records a span for the wrapped block.

        Uses the trace_id from the current context var if not supplied.
        On ``__exit__`` the span is finished and the parent restored.

        Example::

            with tracer.span("llm_call", kind=SpanKind.LLM, attributes={"model": model}):
                answer = call_provider(...)
        """
        effective_trace_id = trace_id or get_current_trace_id()
        if not effective_trace_id:
            # No active trace — yield a dummy span
            dummy = Span(
                span_id="", trace_id="", parent_span_id="",
                name=name, kind=kind,
            )
            yield dummy
            return

        parent_span_id = _SPAN_CTX.get("")
        span_obj = self._add_span(
            trace_id=effective_trace_id,
            name=name,
            kind=kind,
            attributes=attributes or {},
            parent_span_id=parent_span_id,
        )

        # Activate this span as the new parent for nested spans
        token = _SPAN_CTX.set(span_obj.span_id)
        _otel_ctx_token: Any = None

        # OTel instrumentation
        otel_span: Any = None
        if _otel_available and _otel_tracer is not None:
            try:
                from opentelemetry import trace as _trace  # type: ignore
                otel_span = _otel_tracer.start_span(
                    name,
                    attributes={
                        "trace_id": effective_trace_id,
                        "span_id":  span_obj.span_id,
                        **(attributes or {}),
                    },
                )
                _otel_ctx_token = _trace.use_span(otel_span, end_on_exit=False)
                _otel_ctx_token.__enter__()
            except Exception:
                otel_span = None

        error_msg = ""
        try:
            yield span_obj
        except Exception as exc:
            error_msg = str(exc)
            raise
        finally:
            span_obj.finish(error=error_msg)
            _SPAN_CTX.reset(token)
            if otel_span is not None:
                try:
                    if error_msg:
                        from opentelemetry.trace import StatusCode  # type: ignore
                        otel_span.set_status(StatusCode.ERROR, error_msg)
                    otel_span.end()
                    if _otel_ctx_token is not None:
                        _otel_ctx_token.__exit__(None, None, None)
                except Exception:
                    pass

    # ── Internal ──────────────────────────────────────────────────────────────

    def _add_span(
        self,
        *,
        trace_id:       str,
        name:           str,
        kind:           SpanKind,
        attributes:     dict[str, Any],
        parent_span_id: str,
    ) -> Span:
        span_id = uuid.uuid4().hex[:16]
        span = Span(
            span_id=span_id,
            trace_id=trace_id,
            parent_span_id=parent_span_id,
            name=name,
            kind=kind,
            attributes=attributes,
        )
        with self._lock:
            record = self._traces.get(trace_id)
            if record is not None:
                record.spans.append(span)
        return span

    # ── Convenience helpers ───────────────────────────────────────────────────

    def record_llm_call(
        self,
        *,
        provider: str,
        model:    str,
        agent:    str,
        trace_id: str = "",
    ) -> "LLMSpanContext":
        """Return a context manager that records an LLM call span."""
        return LLMSpanContext(
            tracer=self,
            provider=provider,
            model=model,
            agent=agent,
            trace_id=trace_id or get_current_trace_id(),
        )

    def record_memory_write(
        self,
        *,
        agent:    str,
        summary:  str = "",
        trace_id: str = "",
    ) -> "MemorySpanContext":
        """Return a context manager that records a memory write span."""
        return MemorySpanContext(
            tracer=self,
            agent=agent,
            summary=summary,
            trace_id=trace_id or get_current_trace_id(),
        )


# ── Typed convenience context managers ───────────────────────────────────────

class LLMSpanContext:
    """Context manager for an LLM call span."""

    def __init__(
        self,
        tracer:   DistributedTracer,
        provider: str,
        model:    str,
        agent:    str,
        trace_id: str,
    ) -> None:
        self._tracer   = tracer
        self._provider = provider
        self._model    = model
        self._agent    = agent
        self._trace_id = trace_id
        self._cm: Any  = None

    def __enter__(self) -> Span:
        self._cm = self._tracer.span(
            f"llm_call:{self._provider}",
            kind=SpanKind.LLM,
            attributes={
                "provider": self._provider,
                "model":    self._model,
                "agent":    self._agent,
            },
            trace_id=self._trace_id,
        )
        return self._cm.__enter__()

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if self._cm is not None:
            self._cm.__exit__(exc_type, exc_val, exc_tb)


class MemorySpanContext:
    """Context manager for a memory write span."""

    def __init__(
        self,
        tracer:   DistributedTracer,
        agent:    str,
        summary:  str,
        trace_id: str,
    ) -> None:
        self._tracer   = tracer
        self._agent    = agent
        self._summary  = summary
        self._trace_id = trace_id
        self._cm: Any  = None

    def __enter__(self) -> Span:
        self._cm = self._tracer.span(
            "memory_write",
            kind=SpanKind.MEMORY,
            attributes={
                "agent":   self._agent,
                "summary": self._summary[:200] if self._summary else "",
            },
            trace_id=self._trace_id,
        )
        return self._cm.__enter__()

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if self._cm is not None:
            self._cm.__exit__(exc_type, exc_val, exc_tb)


# ── Utilities ─────────────────────────────────────────────────────────────────

def _iso_now() -> str:
    import time as _t
    return _t.strftime("%Y-%m-%dT%H:%M:%SZ", _t.gmtime())


# ── Singleton ─────────────────────────────────────────────────────────────────

_tracer_instance: Optional[DistributedTracer] = None
_tracer_lock = threading.Lock()


def get_distributed_tracer() -> DistributedTracer:
    """Return the process-wide :class:`DistributedTracer` singleton."""
    global _tracer_instance
    with _tracer_lock:
        if _tracer_instance is None:
            svc = _os.environ.get("OTEL_SERVICE_NAME", "ascend-ai")
            _tracer_instance = DistributedTracer(service_name=svc)
    return _tracer_instance
