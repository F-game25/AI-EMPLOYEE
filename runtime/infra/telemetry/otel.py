"""OpenTelemetry integration layer.

Provides:
  - TracerProvider with OTLP gRPC export (when OTEL_EXPORTER_OTLP_ENDPOINT set)
  - MeterProvider with prometheus exporter + OTLP
  - Structured span attributes aligned to AI semantic conventions
  - Trace context propagation via W3C TraceContext headers
  - Graceful fallback to no-op when opentelemetry-sdk not installed

Usage:
    from infra.telemetry.otel import get_tracer, get_meter, start_span

    tracer = get_tracer("my.component")
    with tracer.start_as_current_span("my.operation") as span:
        span.set_attribute("ai.model_id", "claude-sonnet-4-6")
        span.set_attribute("ai.input_tokens", 500)
        ...
"""
from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from typing import Any, Generator

logger = logging.getLogger("telemetry.otel")

_SERVICE_NAME = os.environ.get("OTEL_SERVICE_NAME", "ai-employee")
_OTLP_ENDPOINT = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "")
_OTLP_GRPC_PORT = int(os.environ.get("OTEL_EXPORTER_OTLP_GRPC_PORT", "4317"))

# ── Try to import opentelemetry SDK ───────────────────────────────────────────

try:
    from opentelemetry import trace, metrics
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader, ConsoleMetricExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.trace import Status, StatusCode, NonRecordingSpan
    from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
    _SDK_AVAILABLE = True
except ImportError:
    _SDK_AVAILABLE = False
    logger.info("opentelemetry-sdk not installed — using no-op telemetry")


def _build_resource() -> Any:
    from opentelemetry.sdk.resources import Resource
    return Resource.create({
        "service.name": _SERVICE_NAME,
        "service.version": os.environ.get("APP_VERSION", "0.0.0"),
        "deployment.environment": os.environ.get("ENVIRONMENT", "development"),
    })


def _build_tracer_provider() -> Any:
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
    provider = TracerProvider(resource=_build_resource())

    if _OTLP_ENDPOINT:
        try:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
            exporter = OTLPSpanExporter(endpoint=_OTLP_ENDPOINT, insecure=True)
            provider.add_span_processor(BatchSpanProcessor(exporter))
            logger.info("OTLP trace exporter: %s", _OTLP_ENDPOINT)
        except ImportError:
            logger.warning("opentelemetry-exporter-otlp not installed — falling back to console")
            provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
    else:
        # In-memory span exporter for dev/test + replay
        from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
        global _in_memory_exporter
        _in_memory_exporter = InMemorySpanExporter()
        provider.add_span_processor(BatchSpanProcessor(_in_memory_exporter))

    return provider


def _build_meter_provider() -> Any:
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader, ConsoleMetricExporter
    readers = []
    if _OTLP_ENDPOINT:
        try:
            from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
            readers.append(PeriodicExportingMetricReader(
                OTLPMetricExporter(endpoint=_OTLP_ENDPOINT, insecure=True),
                export_interval_millis=30000,
            ))
        except ImportError:
            pass
    try:
        from opentelemetry.exporter.prometheus import PrometheusMetricExporter
        from prometheus_client import start_http_server
        readers.append(PrometheusMetricExporter())
    except Exception:
        pass
    if not readers:
        readers.append(PeriodicExportingMetricReader(ConsoleMetricExporter(), export_interval_millis=60000))
    return MeterProvider(resource=_build_resource(), metric_readers=readers)


_in_memory_exporter: Any = None
_tracer_provider: Any = None
_meter_provider: Any = None


def _init_providers() -> None:
    global _tracer_provider, _meter_provider
    if not _SDK_AVAILABLE or _tracer_provider is not None:
        return
    try:
        from opentelemetry import trace, metrics
        _tracer_provider = _build_tracer_provider()
        trace.set_tracer_provider(_tracer_provider)
        _meter_provider = _build_meter_provider()
        metrics.set_meter_provider(_meter_provider)
        logger.info("OTel providers initialized: service=%s", _SERVICE_NAME)
    except Exception as e:
        logger.warning("OTel init failed: %s", e)


def get_tracer(name: str) -> Any:
    _init_providers()
    if _SDK_AVAILABLE:
        from opentelemetry import trace
        return trace.get_tracer(name)
    return _NoOpTracer()


def get_meter(name: str) -> Any:
    _init_providers()
    if _SDK_AVAILABLE:
        from opentelemetry import metrics
        return metrics.get_meter(name)
    return _NoOpMeter()


@contextmanager
def start_span(
    name: str,
    *,
    tracer_name: str = "ai-employee",
    attributes: dict | None = None,
    parent_ctx: Any = None,
) -> Generator[Any, None, None]:
    tracer = get_tracer(tracer_name)
    ctx = parent_ctx  # W3C context propagation
    with tracer.start_as_current_span(name, context=ctx, attributes=attributes or {}) as span:
        yield span


def extract_trace_context(headers: dict) -> Any:
    if not _SDK_AVAILABLE:
        return None
    try:
        from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
        from opentelemetry import context
        return TraceContextTextMapPropagator().extract(headers)
    except Exception:
        return None


def inject_trace_headers(headers: dict) -> dict:
    if not _SDK_AVAILABLE:
        return headers
    try:
        from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
        TraceContextTextMapPropagator().inject(headers)
    except Exception:
        pass
    return headers


def get_in_memory_spans(clear: bool = False) -> list[dict]:
    if _in_memory_exporter is None:
        return []
    try:
        spans = _in_memory_exporter.get_finished_spans()
        if clear:
            _in_memory_exporter.clear()
        return [_span_to_dict(s) for s in spans]
    except Exception:
        return []


def _span_to_dict(span: Any) -> dict:
    try:
        return {
            "trace_id": format(span.context.trace_id, "032x"),
            "span_id":  format(span.context.span_id, "016x"),
            "parent_span_id": format(span.parent.span_id, "016x") if span.parent else None,
            "name": span.name,
            "start_time_ns": span.start_time,
            "end_time_ns": span.end_time,
            "duration_ms": (span.end_time - span.start_time) / 1_000_000 if span.end_time else None,
            "status": span.status.status_code.name if hasattr(span, "status") else "UNSET",
            "attributes": dict(span.attributes or {}),
            "events": [{"name": e.name, "ts_ns": e.timestamp, "attrs": dict(e.attributes or {})}
                       for e in (span.events or [])],
        }
    except Exception:
        return {}


# ── No-op fallbacks ────────────────────────────────────────────────────────────

class _NoOpSpan:
    def set_attribute(self, *a, **kw): pass
    def add_event(self, *a, **kw): pass
    def set_status(self, *a, **kw): pass
    def record_exception(self, *a, **kw): pass
    def __enter__(self): return self
    def __exit__(self, *a): pass


class _NoOpTracer:
    def start_as_current_span(self, name, **kw):
        return _NoOpSpan()
    def start_span(self, name, **kw):
        return _NoOpSpan()


class _NoOpMeter:
    def create_counter(self, *a, **kw): return _NoOpInstrument()
    def create_histogram(self, *a, **kw): return _NoOpInstrument()
    def create_gauge(self, *a, **kw): return _NoOpInstrument()


class _NoOpInstrument:
    def add(self, *a, **kw): pass
    def record(self, *a, **kw): pass
    def set(self, *a, **kw): pass
