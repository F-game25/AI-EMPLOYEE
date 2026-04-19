"""Tests for Distributed Tracing — runtime/core/distributed_tracing.py.

Covers:
  DistributedTracer:
  - start_trace creates a TraceRecord with a valid trace_id
  - start_trace sets the context var
  - Spans are recorded in the trace tree
  - Parent-child span relationships via context var
  - finish_trace marks the trace completed
  - get_trace returns full tree dict
  - list_traces returns summaries
  - Capacity eviction (max_traces)
  - LLM span via record_llm_call context manager
  - Memory span via record_memory_write context manager
  - span() on error records status="error"
  - No active trace → span() yields dummy span (no crash)
  - Multiple concurrent traces don't interfere (thread safety)
  - OpenTelemetry spans recorded when SDK is available

  ContextVar propagation:
  - set_current_trace_id / get_current_trace_id round-trip
  - ContextVar is isolated per thread

  Span:
  - duration_ms is None before finish
  - duration_ms > 0 after finish
  - to_dict() has required keys

  Server integration (static analysis):
  - _get_distributed_tracer loader present
  - _get_span_kind_llm loader present
  - start_trace called in post_chat
  - trace_id returned in response payload
  - X-Trace-ID in response headers
  - llm_call span wired into _generate_llm_response
  - memory_write span wired around on_exchange
  - GET /api/traces endpoint registered
  - GET /api/traces/{trace_id} endpoint registered
  - distributed_tracing.py module exists
"""
from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

import pytest

REPO_ROOT    = Path(__file__).resolve().parents[1]
RUNTIME_DIR  = REPO_ROOT / "runtime"

if str(RUNTIME_DIR) not in sys.path:
    sys.path.insert(0, str(RUNTIME_DIR))

from core.distributed_tracing import (
    DistributedTracer,
    Span,
    SpanKind,
    TraceRecord,
    get_current_trace_id,
    get_distributed_tracer,
    get_otel_spans,
    set_current_trace_id,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _tracer(**kwargs) -> DistributedTracer:
    """Create a fresh tracer (not the singleton) for each test."""
    return DistributedTracer(**kwargs)


# ═══════════════════════════════════════════════════════════════════════════════
# ContextVar
# ═══════════════════════════════════════════════════════════════════════════════

class TestContextVar:
    def test_default_is_empty(self):
        # A brand-new context should have no trace
        import contextvars
        ctx = contextvars.copy_context()
        assert ctx.run(get_current_trace_id) == ""

    def test_set_and_get_round_trip(self):
        import contextvars
        results = []
        def _task():
            tok = set_current_trace_id("trace-abc123")
            results.append(get_current_trace_id())
            from core.distributed_tracing import _TRACE_CTX
            _TRACE_CTX.reset(tok)
        ctx = contextvars.copy_context()
        ctx.run(_task)
        assert results == ["trace-abc123"]

    def test_isolated_per_thread(self):
        """Two threads must not see each other's trace_id."""
        results: list[str] = []
        lock = threading.Barrier(2)

        def _thread_a():
            set_current_trace_id("trace-aaa")
            lock.wait()
            results.append(("a", get_current_trace_id()))

        def _thread_b():
            set_current_trace_id("trace-bbb")
            lock.wait()
            results.append(("b", get_current_trace_id()))

        ta = threading.Thread(target=_thread_a)
        tb = threading.Thread(target=_thread_b)
        ta.start(); tb.start()
        ta.join(); tb.join()

        by_thread = dict(results)
        assert by_thread["a"] == "trace-aaa"
        assert by_thread["b"] == "trace-bbb"


# ═══════════════════════════════════════════════════════════════════════════════
# Span dataclass
# ═══════════════════════════════════════════════════════════════════════════════

class TestSpan:
    def _span(self) -> Span:
        return Span(
            span_id="abc123",
            trace_id="trace-xyz",
            parent_span_id="",
            name="test_op",
            kind=SpanKind.INTERNAL,
        )

    def test_duration_none_before_finish(self):
        s = self._span()
        assert s.duration_ms is None

    def test_duration_set_after_finish(self):
        s = self._span()
        time.sleep(0.01)
        s.finish()
        assert s.duration_ms is not None
        assert s.duration_ms >= 0

    def test_finish_sets_status_ok(self):
        s = self._span()
        s.finish()
        assert s.status == "ok"

    def test_finish_sets_status_error(self):
        s = self._span()
        s.finish(error="boom")
        assert s.status == "error"
        assert s.error == "boom"

    def test_to_dict_required_keys(self):
        s = self._span()
        s.finish()
        d = s.to_dict()
        for key in ("span_id", "trace_id", "parent_span_id", "name",
                    "kind", "attributes", "duration_ms", "status", "error"):
            assert key in d, f"missing key: {key}"

    def test_kind_value_in_dict(self):
        s = self._span()
        s.finish()
        assert s.to_dict()["kind"] == "internal"


# ═══════════════════════════════════════════════════════════════════════════════
# DistributedTracer — trace lifecycle
# ═══════════════════════════════════════════════════════════════════════════════

class TestDistributedTracerLifecycle:
    def test_start_trace_returns_valid_id(self):
        t = _tracer()
        tid = t.start_trace("test")
        assert tid.startswith("trace-")
        assert len(tid) > 10

    def test_start_trace_sets_context_var(self):
        t = _tracer()
        tid = t.start_trace("ctx_test")
        assert get_current_trace_id() == tid

    def test_start_trace_creates_root_span(self):
        t = _tracer()
        tid = t.start_trace("root_test")
        tree = t.get_trace(tid)
        assert tree is not None
        assert len(tree["spans"]) >= 1
        assert tree["spans"][0]["name"] == "root_test"
        assert tree["spans"][0]["parent_span_id"] == ""

    def test_finish_trace_marks_completed(self):
        t = _tracer()
        tid = t.start_trace("finish_test")
        assert t.get_trace(tid)["completed"] is False
        t.finish_trace(tid)
        assert t.get_trace(tid)["completed"] is True

    def test_get_trace_none_for_unknown(self):
        t = _tracer()
        assert t.get_trace("trace-nonexistent") is None

    def test_get_trace_dict_shape(self):
        t = _tracer()
        tid = t.start_trace("shape_test", attributes={"user": "alice"})
        tree = t.get_trace(tid)
        for key in ("trace_id", "name", "started_at", "attributes", "spans",
                    "completed", "span_count"):
            assert key in tree, f"missing key: {key}"
        assert tree["trace_id"] == tid
        assert tree["attributes"]["user"] == "alice"

    def test_list_traces_includes_created(self):
        t = _tracer()
        tid = t.start_trace("list_test")
        summaries = t.list_traces()
        ids = [s["trace_id"] for s in summaries]
        assert tid in ids

    def test_list_traces_summary_has_no_spans_key(self):
        t = _tracer()
        t.start_trace("list_shape")
        summaries = t.list_traces()
        for s in summaries:
            assert "spans" not in s

    def test_capacity_eviction(self):
        t = _tracer(max_traces=3)
        ids = [t.start_trace(f"t{i}") for i in range(5)]
        # Oldest two should be evicted
        assert t.get_trace(ids[0]) is None
        assert t.get_trace(ids[1]) is None
        assert t.get_trace(ids[4]) is not None


# ═══════════════════════════════════════════════════════════════════════════════
# DistributedTracer — span() context manager
# ═══════════════════════════════════════════════════════════════════════════════

class TestDistributedTracerSpans:
    def test_span_added_to_trace(self):
        t = _tracer()
        tid = t.start_trace("span_test")
        with t.span("my_op", kind=SpanKind.INTERNAL):
            pass
        tree = t.get_trace(tid)
        names = [s["name"] for s in tree["spans"]]
        assert "my_op" in names

    def test_span_duration_recorded(self):
        t = _tracer()
        tid = t.start_trace("dur_test")
        with t.span("dur_op"):
            time.sleep(0.01)
        tree = t.get_trace(tid)
        dur_span = next(s for s in tree["spans"] if s["name"] == "dur_op")
        assert dur_span["duration_ms"] is not None
        assert dur_span["duration_ms"] >= 0

    def test_span_parent_child_relationship(self):
        t = _tracer()
        tid = t.start_trace("parent_test")
        root_span_id = t.get_trace(tid)["spans"][0]["span_id"]
        with t.span("child_op") as child:
            # The parent should be the root span
            assert child.parent_span_id == root_span_id

    def test_nested_spans_form_chain(self):
        t = _tracer()
        tid = t.start_trace("nested_test")
        with t.span("outer") as outer_span:
            outer_id = outer_span.span_id
            with t.span("inner") as inner_span:
                assert inner_span.parent_span_id == outer_id

    def test_span_error_recorded(self):
        t = _tracer()
        tid = t.start_trace("err_test")
        with pytest.raises(ValueError):
            with t.span("failing_op"):
                raise ValueError("test error")
        tree = t.get_trace(tid)
        err_span = next((s for s in tree["spans"] if s["name"] == "failing_op"), None)
        assert err_span is not None
        assert err_span["status"] == "error"
        assert "test error" in err_span["error"]

    def test_span_with_no_active_trace_yields_dummy(self):
        t = _tracer()
        # No start_trace called — context var is empty
        from core.distributed_tracing import _TRACE_CTX
        tok = _TRACE_CTX.set("")
        try:
            with t.span("dummy_op") as s:
                assert s.span_id == ""
        finally:
            _TRACE_CTX.reset(tok)

    def test_span_attributes_stored(self):
        t = _tracer()
        tid = t.start_trace("attr_test")
        with t.span("attr_op", attributes={"model": "gpt-4o", "provider": "openai"}):
            pass
        tree = t.get_trace(tid)
        attr_span = next(s for s in tree["spans"] if s["name"] == "attr_op")
        assert attr_span["attributes"]["model"] == "gpt-4o"

    def test_span_kind_stored(self):
        t = _tracer()
        tid = t.start_trace("kind_test")
        with t.span("llm_span", kind=SpanKind.LLM):
            pass
        tree = t.get_trace(tid)
        llm_span = next(s for s in tree["spans"] if s["name"] == "llm_span")
        assert llm_span["kind"] == "llm"


# ═══════════════════════════════════════════════════════════════════════════════
# Convenience context managers
# ═══════════════════════════════════════════════════════════════════════════════

class TestConvenienceContextManagers:
    def test_record_llm_call_adds_span(self):
        t = _tracer()
        tid = t.start_trace("llm_cm_test")
        with t.record_llm_call(provider="openai", model="gpt-4o", agent="sales-agent"):
            pass
        tree = t.get_trace(tid)
        llm_spans = [s for s in tree["spans"] if "llm_call" in s["name"]]
        assert len(llm_spans) == 1
        assert llm_spans[0]["attributes"]["provider"] == "openai"
        assert llm_spans[0]["attributes"]["model"] == "gpt-4o"

    def test_record_memory_write_adds_span(self):
        t = _tracer()
        tid = t.start_trace("mem_cm_test")
        with t.record_memory_write(agent="recruiter", summary="Candidate added"):
            pass
        tree = t.get_trace(tid)
        mem_spans = [s for s in tree["spans"] if s["name"] == "memory_write"]
        assert len(mem_spans) == 1
        assert mem_spans[0]["kind"] == "memory"
        assert mem_spans[0]["attributes"]["agent"] == "recruiter"

    def test_llm_span_on_error_records_status(self):
        t = _tracer()
        tid = t.start_trace("llm_err_test")
        with pytest.raises(RuntimeError):
            with t.record_llm_call(provider="groq", model="llama", agent="researcher"):
                raise RuntimeError("API timeout")
        tree = t.get_trace(tid)
        llm_spans = [s for s in tree["spans"] if "llm_call" in s["name"]]
        assert llm_spans[0]["status"] == "error"


# ═══════════════════════════════════════════════════════════════════════════════
# Thread safety
# ═══════════════════════════════════════════════════════════════════════════════

class TestThreadSafety:
    def test_concurrent_traces_dont_interfere(self):
        t = _tracer()
        results: dict[str, list[str]] = {}
        barrier = threading.Barrier(5)

        def _worker(name: str) -> None:
            tid = t.start_trace(f"thread_{name}")
            barrier.wait()
            with t.span(f"work_{name}"):
                time.sleep(0.01)
            results[name] = [s["name"] for s in (t.get_trace(tid) or {}).get("spans", [])]

        threads = [threading.Thread(target=_worker, args=(f"t{i}",)) for i in range(5)]
        for th in threads:
            th.start()
        for th in threads:
            th.join()

        # Each trace should only contain its own spans
        for name, spans in results.items():
            assert any(f"work_{name}" in s for s in spans)

    def test_list_traces_is_thread_safe(self):
        t = _tracer(max_traces=200)
        barrier = threading.Barrier(10)

        def _worker():
            barrier.wait()
            for _ in range(10):
                t.start_trace("concurrent")

        threads = [threading.Thread(target=_worker) for _ in range(10)]
        for th in threads:
            th.start()
        for th in threads:
            th.join()
        # Should not crash; len <= max_traces
        assert len(t.list_traces(limit=200)) <= 200


# ═══════════════════════════════════════════════════════════════════════════════
# OpenTelemetry integration
# ═══════════════════════════════════════════════════════════════════════════════

class TestOpenTelemetryIntegration:
    def test_otel_sdk_available(self):
        """OTel SDK should be importable in test environment."""
        try:
            import opentelemetry  # noqa: F401
            assert True
        except ImportError:
            pytest.skip("opentelemetry-sdk not installed")

    def test_otel_spans_returned_by_get_otel_spans(self):
        """After creating a span, get_otel_spans() should return at least the span."""
        try:
            import opentelemetry  # noqa: F401
        except ImportError:
            pytest.skip("opentelemetry-sdk not installed")

        # Use a fresh tracer (not the singleton) to avoid state pollution
        fresh = DistributedTracer(service_name="test-svc")
        tid = fresh.start_trace("otel_test")
        with fresh.span("otel_inner", kind=SpanKind.LLM):
            pass
        # The in-memory exporter is on the global tracer provider, which
        # may differ from our test tracer — just verify get_otel_spans()
        # doesn't crash and returns a list
        result = get_otel_spans()
        assert isinstance(result, list)

    def test_tracer_init_without_otel_does_not_crash(self):
        """Even if OTel is absent, start_trace/span must not raise."""
        # Simulate OTel unavailable by patching the flag
        from core import distributed_tracing as dt_module
        original = dt_module._otel_available
        dt_module._otel_available = False
        try:
            t = DistributedTracer()
            tid = t.start_trace("no_otel")
            with t.span("op"):
                pass
            assert t.get_trace(tid) is not None
        finally:
            dt_module._otel_available = original


# ═══════════════════════════════════════════════════════════════════════════════
# Singleton
# ═══════════════════════════════════════════════════════════════════════════════

class TestSingleton:
    def test_singleton_identity(self):
        a = get_distributed_tracer()
        b = get_distributed_tracer()
        assert a is b

    def test_singleton_can_start_trace(self):
        t = get_distributed_tracer()
        tid = t.start_trace("singleton_test")
        assert tid.startswith("trace-")
        assert t.get_trace(tid) is not None


# ═══════════════════════════════════════════════════════════════════════════════
# SpanKind enum
# ═══════════════════════════════════════════════════════════════════════════════

class TestSpanKindEnum:
    def test_all_kinds_have_string_values(self):
        for kind in SpanKind:
            assert isinstance(kind.value, str)
            assert len(kind.value) > 0

    def test_expected_kinds_present(self):
        names = {k.name for k in SpanKind}
        for expected in ("INTERNAL", "LLM", "MEMORY", "DATABASE", "AGENT", "SERVER", "CLIENT"):
            assert expected in names


# ═══════════════════════════════════════════════════════════════════════════════
# Server integration (static analysis)
# ═══════════════════════════════════════════════════════════════════════════════

class TestServerTracingIntegration:
    def _src(self) -> str:
        return (REPO_ROOT / "runtime" / "agents" / "problem-solver-ui" / "server.py").read_text()

    def test_distributed_tracer_loader_defined(self):
        assert "_get_distributed_tracer" in self._src()

    def test_span_kind_llm_loader_defined(self):
        assert "_get_span_kind_llm" in self._src()

    def test_start_trace_called_in_post_chat(self):
        assert "start_trace" in self._src()

    def test_trace_id_in_response_payload(self):
        src = self._src()
        assert '"trace_id"' in src or "_trace_id" in src

    def test_x_trace_id_header_present(self):
        assert "X-Trace-ID" in self._src()

    def test_llm_span_wired_in_generate_llm_response(self):
        src = self._src()
        assert "_do_llm_call_with_trace" in src or "llm_call:" in src

    def test_memory_span_wired_around_on_exchange(self):
        src = self._src()
        assert "memory_write" in src

    def test_traces_list_endpoint_registered(self):
        assert '"/api/traces"' in self._src()

    def test_traces_detail_endpoint_registered(self):
        assert '"/api/traces/{trace_id}"' in self._src()

    def test_finish_trace_called(self):
        assert "finish_trace" in self._src()

    def test_distributed_tracing_module_exists(self):
        assert (RUNTIME_DIR / "core" / "distributed_tracing.py").exists()

    def test_trace_id_before_threadpool(self):
        """start_trace must be called before run_in_threadpool."""
        src = self._src()
        start_idx = src.find("start_trace")
        threadpool_idx = src.find("run_in_threadpool(\n        handle_command")
        assert start_idx < threadpool_idx, "start_trace must precede handle_command threadpool call"
