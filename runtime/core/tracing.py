"""Distributed tracing via OpenTelemetry and Jaeger."""
import os
import logging
from opentelemetry import trace, metrics
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.jaeger.thrift import JaegerExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.psycopg import PsycopgInstrumentor
from opentelemetry.sdk.resources import SERVICE_NAME, Resource

logger = logging.getLogger(__name__)


def setup_tracing(service_name: str = "ai-employee") -> TracerProvider:
    """Initialize OpenTelemetry tracing with Jaeger exporter."""
    jaeger_host = os.environ.get("JAEGER_HOST", "localhost")
    jaeger_port = int(os.environ.get("JAEGER_PORT", 6831))
    jaeger_enabled = os.environ.get("JAEGER_ENABLED", "true").lower() == "true"

    if not jaeger_enabled:
        logger.info("Jaeger tracing disabled")
        return trace.get_tracer_provider()

    try:
        jaeger_exporter = JaegerExporter(
            agent_host_name=jaeger_host,
            agent_port=jaeger_port,
        )

        trace_provider = TracerProvider(
            resource=Resource.create({SERVICE_NAME: service_name})
        )
        trace_provider.add_span_processor(BatchSpanProcessor(jaeger_exporter))
        trace.set_tracer_provider(trace_provider)

        logger.info(f"Jaeger tracing initialized: {jaeger_host}:{jaeger_port}")
        return trace_provider
    except Exception as e:
        logger.error(f"Failed to setup Jaeger tracing: {e}")
        return trace.get_tracer_provider()


def setup_fastapi_instrumentation(app):
    """Instrument FastAPI application with tracing."""
    try:
        FastAPIInstrumentor.instrument_app(app)
        logger.info("FastAPI instrumentation enabled")
    except Exception as e:
        logger.error(f"Failed to instrument FastAPI: {e}")


def setup_psycopg_instrumentation():
    """Instrument psycopg3 database driver with tracing."""
    try:
        PsycopgInstrumentor().instrument()
        logger.info("Psycopg instrumentation enabled")
    except Exception as e:
        logger.error(f"Failed to instrument psycopg: {e}")


def get_tracer(module_name: str = __name__):
    """Get a tracer instance for a module."""
    return trace.get_tracer(module_name)
