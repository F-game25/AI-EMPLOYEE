import logging
import time
from typing import Optional, Dict
from uuid import uuid4
from .schema import Span, TraceTree
from ..db import cognitive_conn

logger = logging.getLogger(__name__)


def _ensure_tables() -> None:
    with cognitive_conn() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS spans (
                id TEXT PRIMARY KEY,
                trace_id TEXT NOT NULL,
                parent_span_id TEXT,
                operation_name TEXT NOT NULL,
                start_time REAL NOT NULL,
                end_time REAL,
                duration_ms REAL DEFAULT 0,
                status TEXT DEFAULT 'pending',
                error_message TEXT,
                attributes TEXT NOT NULL,
                tenant_id TEXT NOT NULL
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_span_trace ON spans(trace_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_span_parent ON spans(parent_span_id)")


_ensure_tables()


class DistributedTracer:
    def __init__(self):
        self.active_spans: Dict[str, Span] = {}
        self.completed_traces: Dict[str, TraceTree] = {}

    def start_span(
        self,
        trace_id: str,
        operation_name: str,
        tenant_id: str,
        parent_span_id: Optional[str] = None,
        attributes: dict = None,
    ) -> Span:
        span = Span(
            trace_id=trace_id,
            operation_name=operation_name,
            parent_span_id=parent_span_id,
            attributes=attributes or {},
        )
        self.active_spans[span.id] = span
        return span

    def end_span(self, span_id: str, status: str = "success", error_message: Optional[str] = None) -> None:
        if span_id not in self.active_spans:
            logger.warning("Span %s not found", span_id)
            return

        span = self.active_spans[span_id]
        span.end_time = time.time()
        span.duration_ms = (span.end_time - span.start_time) * 1000
        span.status = status
        span.error_message = error_message

        self._store_span(span)

    def _store_span(self, span: Span) -> None:
        try:
            import json
            with cognitive_conn() as c:
                c.execute(
                    "INSERT INTO spans (id, trace_id, parent_span_id, operation_name, start_time, "
                    "end_time, duration_ms, status, error_message, attributes, tenant_id) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        span.id,
                        span.trace_id,
                        span.parent_span_id,
                        span.operation_name,
                        span.start_time,
                        span.end_time,
                        span.duration_ms,
                        span.status,
                        span.error_message,
                        json.dumps(span.attributes),
                        span.attributes.get("tenant_id", "unknown"),
                    ),
                )
        except Exception as e:
            logger.warning("Failed to store span: %s", e)

    def get_trace(self, trace_id: str, tenant_id: str) -> Optional[TraceTree]:
        try:
            import json
            with cognitive_conn() as c:
                rows = c.execute(
                    "SELECT * FROM spans WHERE trace_id=? AND tenant_id=? ORDER BY start_time",
                    (trace_id, tenant_id),
                ).fetchall()

            if not rows:
                return None

            spans = [
                Span(
                    id=row["id"],
                    trace_id=row["trace_id"],
                    parent_span_id=row["parent_span_id"],
                    operation_name=row["operation_name"],
                    start_time=row["start_time"],
                    end_time=row["end_time"],
                    duration_ms=row["duration_ms"],
                    status=row["status"],
                    error_message=row["error_message"],
                    attributes=json.loads(row["attributes"]),
                )
                for row in rows
            ]

            root_span = next((s for s in spans if s.parent_span_id is None), None)
            return TraceTree(
                trace_id=trace_id,
                root_span_id=root_span.id if root_span else "",
                tenant_id=tenant_id,
                spans=spans,
            )
        except Exception as e:
            logger.warning("Failed to get trace: %s", e)
            return None


_instance: Optional[DistributedTracer] = None


def get_tracer() -> DistributedTracer:
    global _instance
    if _instance is None:
        _instance = DistributedTracer()
    return _instance
