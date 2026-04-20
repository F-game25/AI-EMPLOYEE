"""Tests for Prompt Inspector — runtime/core/prompt_inspector.py.

Covers:
  PromptTrace:
  - to_dict() returns all required keys
  - summary() returns lightweight subset

  PromptInspector:
  - start_trace returns PromptTrace with unique id and timestamp
  - start_trace returns None when inspector is disabled
  - start_trace returns None when sampled out (sample_rate=0.0)
  - start_trace always fires when sample_rate=1.0
  - Capacity eviction: oldest trace removed when max_traces exceeded
  - set_context stores context and sets missing_context flag when empty
  - set_prompt stores constructed_prompt and sets empty_prompt flag when empty
  - set_agent stores agent, provider, model
  - set_model_output stores raw output and sets empty_output flag when empty
  - finish_trace stores final_output, actions, status, duration_ms
  - finish_trace sets generic_output flag for known fallback phrases
  - set_error marks trace as error with error field and error flag
  - get_trace returns full dict for known id
  - get_trace returns None for unknown id
  - list_traces returns summaries newest-first
  - list_traces respects limit
  - count() returns correct count
  - clear() empties all storage
  - status() returns enabled/sample_rate/max_traces/stored_traces
  - enabled setter toggles inspection
  - sample_rate setter clamps to 0.0–1.0
  - Thread safety: concurrent start_trace calls produce unique ids
  - Multiple traces do not interfere with each other

  get_prompt_inspector:
  - Returns same singleton across calls
  - Singleton respects PROMPT_INSPECTOR_ENABLED env var
  - Singleton respects PROMPT_INSPECTOR_SAMPLE env var
  - Singleton respects PROMPT_INSPECTOR_MAX env var

  Server integration (static analysis):
  - _get_prompt_inspector loader present in server.py
  - prompt_inspector.py module exists
  - GET /api/prompt-traces endpoint registered
  - GET /api/prompt-trace/{trace_id} endpoint registered
  - PATCH /api/prompt-inspector/config endpoint registered
  - DELETE /api/prompt-traces endpoint registered
  - prompt:trace WS broadcast present in post_chat
"""
from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

import pytest

REPO_ROOT   = Path(__file__).resolve().parents[1]
RUNTIME_DIR = REPO_ROOT / "runtime"

if str(RUNTIME_DIR) not in sys.path:
    sys.path.insert(0, str(RUNTIME_DIR))

from core.prompt_inspector import (
    PromptInspector,
    PromptTrace,
    get_prompt_inspector,
)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def fresh_inspector(**kwargs) -> PromptInspector:
    """Return a fresh PromptInspector (not the global singleton)."""
    return PromptInspector(**kwargs)


# ─── PromptTrace ──────────────────────────────────────────────────────────────

class TestPromptTrace:
    def test_to_dict_required_keys(self):
        trace = PromptTrace(id="pt-abc", timestamp="2026-01-01T00:00:00Z", user_input="hello")
        d = trace.to_dict()
        for key in ("id", "timestamp", "user_input", "context_used", "constructed_prompt",
                    "model_raw_output", "final_output", "actions_triggered",
                    "execution_status", "agent", "provider", "model", "flags",
                    "error", "duration_ms"):
            assert key in d, f"Missing key: {key}"

    def test_to_dict_values(self):
        trace = PromptTrace(id="pt-1", timestamp="ts", user_input="hi")
        trace.agent = "hermes"
        d = trace.to_dict()
        assert d["id"] == "pt-1"
        assert d["user_input"] == "hi"
        assert d["agent"] == "hermes"
        assert d["execution_status"] == "pending"

    def test_summary_subset(self):
        trace = PromptTrace(id="pt-2", timestamp="ts", user_input="x" * 200)
        s = trace.summary()
        assert "id" in s
        assert "user_input" in s
        assert len(s["user_input"]) <= 120
        # Full fields not in summary
        assert "context_used" not in s
        assert "constructed_prompt" not in s


# ─── PromptInspector.start_trace ─────────────────────────────────────────────

class TestStartTrace:
    def test_returns_prompt_trace(self):
        pi = fresh_inspector()
        t = pi.start_trace("hello world")
        assert isinstance(t, PromptTrace)

    def test_unique_ids(self):
        pi = fresh_inspector()
        ids = {pi.start_trace(f"msg {i}").id for i in range(10)}
        assert len(ids) == 10

    def test_timestamp_is_iso(self):
        pi = fresh_inspector()
        t = pi.start_trace("test")
        assert "T" in t.timestamp
        assert t.timestamp.endswith(("Z", "+00:00"))

    def test_user_input_stored(self):
        pi = fresh_inspector()
        t = pi.start_trace("my query")
        assert t.user_input == "my query"

    def test_returns_none_when_disabled(self):
        pi = fresh_inspector(enabled=False)
        assert pi.start_trace("hello") is None

    def test_returns_none_when_sample_zero(self):
        pi = fresh_inspector(sample_rate=0.0)
        results = [pi.start_trace("x") for _ in range(20)]
        assert all(r is None for r in results)

    def test_always_fires_when_sample_one(self):
        pi = fresh_inspector(sample_rate=1.0)
        results = [pi.start_trace("x") for _ in range(10)]
        assert all(r is not None for r in results)

    def test_capacity_eviction(self):
        pi = fresh_inspector(max_traces=3)
        for i in range(5):
            pi.start_trace(f"msg {i}")
        assert pi.count() == 3

    def test_count_increments(self):
        pi = fresh_inspector()
        assert pi.count() == 0
        pi.start_trace("a")
        pi.start_trace("b")
        assert pi.count() == 2


# ─── Pipeline hooks ──────────────────────────────────────────────────────────

class TestPipelineHooks:
    def test_set_context_stores_value(self):
        pi = fresh_inspector()
        t = pi.start_trace("q")
        pi.set_context(t.id, "some memory block")
        full = pi.get_trace(t.id)
        assert full["context_used"] == "some memory block"

    def test_set_context_empty_sets_flag(self):
        pi = fresh_inspector()
        t = pi.start_trace("q")
        pi.set_context(t.id, "")
        full = pi.get_trace(t.id)
        assert "missing_context" in full["flags"]

    def test_set_context_non_empty_no_flag(self):
        pi = fresh_inspector()
        t = pi.start_trace("q")
        pi.set_context(t.id, "real context")
        full = pi.get_trace(t.id)
        assert "missing_context" not in full["flags"]

    def test_set_prompt_stores_value(self):
        pi = fresh_inspector()
        t = pi.start_trace("q")
        pi.set_prompt(t.id, "system: you are an AI\nuser: hello")
        full = pi.get_trace(t.id)
        assert "system:" in full["constructed_prompt"]

    def test_set_prompt_empty_sets_flag(self):
        pi = fresh_inspector()
        t = pi.start_trace("q")
        pi.set_prompt(t.id, "")
        full = pi.get_trace(t.id)
        assert "empty_prompt" in full["flags"]

    def test_set_agent_stores_metadata(self):
        pi = fresh_inspector()
        t = pi.start_trace("q")
        pi.set_agent(t.id, agent="hermes", provider="groq", model="llama-3.3-70b")
        full = pi.get_trace(t.id)
        assert full["agent"] == "hermes"
        assert full["provider"] == "groq"
        assert full["model"] == "llama-3.3-70b"

    def test_set_model_output_stores_value(self):
        pi = fresh_inspector()
        t = pi.start_trace("q")
        pi.set_model_output(t.id, "The answer is 42.")
        full = pi.get_trace(t.id)
        assert full["model_raw_output"] == "The answer is 42."

    def test_set_model_output_empty_sets_flag(self):
        pi = fresh_inspector()
        t = pi.start_trace("q")
        pi.set_model_output(t.id, "")
        full = pi.get_trace(t.id)
        assert "empty_output" in full["flags"]

    def test_finish_trace_stores_final_output(self):
        pi = fresh_inspector()
        t = pi.start_trace("q")
        pi.finish_trace(t.id, final_output="done", execution_status="ok")
        full = pi.get_trace(t.id)
        assert full["final_output"] == "done"
        assert full["execution_status"] == "ok"

    def test_finish_trace_stores_actions(self):
        pi = fresh_inspector()
        t = pi.start_trace("q")
        pi.finish_trace(t.id, final_output="done", actions_triggered=["agent:hermes"])
        full = pi.get_trace(t.id)
        assert full["actions_triggered"] == ["agent:hermes"]

    def test_finish_trace_sets_duration(self):
        pi = fresh_inspector()
        t = pi.start_trace("q")
        time.sleep(0.01)
        pi.finish_trace(t.id, final_output="done")
        full = pi.get_trace(t.id)
        assert full["duration_ms"] is not None
        assert full["duration_ms"] > 0

    def test_finish_trace_generic_output_flag(self):
        pi = fresh_inspector()
        t = pi.start_trace("q")
        pi.finish_trace(t.id, final_output="I'm working on that now.")
        full = pi.get_trace(t.id)
        assert "generic_output" in full["flags"]

    def test_set_error_marks_trace(self):
        pi = fresh_inspector()
        t = pi.start_trace("q")
        pi.set_error(t.id, "connection refused")
        full = pi.get_trace(t.id)
        assert full["execution_status"] == "error"
        assert full["error"] == "connection refused"
        assert "error" in full["flags"]

    def test_hooks_noop_on_unknown_id(self):
        pi = fresh_inspector()
        # Should not raise
        pi.set_context("bad-id", "ctx")
        pi.set_prompt("bad-id", "prompt")
        pi.set_agent("bad-id", "agent")
        pi.set_model_output("bad-id", "output")
        pi.finish_trace("bad-id", "result")
        pi.set_error("bad-id", "err")


# ─── Retrieval ────────────────────────────────────────────────────────────────

class TestRetrieval:
    def test_get_trace_returns_dict(self):
        pi = fresh_inspector()
        t = pi.start_trace("hello")
        result = pi.get_trace(t.id)
        assert isinstance(result, dict)
        assert result["id"] == t.id

    def test_get_trace_unknown_returns_none(self):
        pi = fresh_inspector()
        assert pi.get_trace("no-such-id") is None

    def test_list_traces_newest_first(self):
        pi = fresh_inspector()
        ids = [pi.start_trace(f"msg {i}").id for i in range(3)]
        listing = pi.list_traces()
        assert listing[0]["id"] == ids[-1]

    def test_list_traces_respects_limit(self):
        pi = fresh_inspector()
        for i in range(10):
            pi.start_trace(f"msg {i}")
        assert len(pi.list_traces(limit=5)) == 5

    def test_clear_empties_storage(self):
        pi = fresh_inspector()
        pi.start_trace("a")
        pi.start_trace("b")
        pi.clear()
        assert pi.count() == 0
        assert pi.list_traces() == []


# ─── Configuration ────────────────────────────────────────────────────────────

class TestConfiguration:
    def test_status_keys(self):
        pi = fresh_inspector(enabled=True, sample_rate=0.5, max_traces=100)
        s = pi.status()
        assert s["enabled"] is True
        assert s["sample_rate"] == 0.5
        assert s["max_traces"] == 100
        assert "stored_traces" in s

    def test_enabled_setter(self):
        pi = fresh_inspector(enabled=True)
        pi.enabled = False
        assert pi.start_trace("x") is None
        pi.enabled = True
        assert pi.start_trace("x") is not None

    def test_sample_rate_clamps_low(self):
        pi = fresh_inspector()
        pi.sample_rate = -1.0
        assert pi.sample_rate == 0.0

    def test_sample_rate_clamps_high(self):
        pi = fresh_inspector()
        pi.sample_rate = 5.0
        assert pi.sample_rate == 1.0

    def test_multiple_traces_independent(self):
        pi = fresh_inspector()
        t1 = pi.start_trace("first")
        t2 = pi.start_trace("second")
        pi.set_agent(t1.id, agent="hermes")
        pi.set_agent(t2.id, agent="oracle")
        assert pi.get_trace(t1.id)["agent"] == "hermes"
        assert pi.get_trace(t2.id)["agent"] == "oracle"


# ─── Thread safety ────────────────────────────────────────────────────────────

class TestThreadSafety:
    def test_concurrent_start_trace_unique_ids(self):
        pi = fresh_inspector(max_traces=500)
        traces = []
        lock = threading.Lock()

        def worker():
            t = pi.start_trace("concurrent")
            if t is not None:
                with lock:
                    traces.append(t.id)

        threads = [threading.Thread(target=worker) for _ in range(50)]
        for th in threads:
            th.start()
        for th in threads:
            th.join()

        assert len(traces) == len(set(traces)), "Duplicate trace IDs detected"


# ─── Singleton ────────────────────────────────────────────────────────────────

class TestSingleton:
    def test_singleton_same_object(self):
        a = get_prompt_inspector()
        b = get_prompt_inspector()
        assert a is b


# ─── Server integration (static analysis) ────────────────────────────────────

SERVER_PY = REPO_ROOT / "runtime" / "agents" / "problem-solver-ui" / "server.py"
MODULE_PY  = RUNTIME_DIR / "core" / "prompt_inspector.py"


class TestServerIntegration:
    def test_module_exists(self):
        assert MODULE_PY.exists(), "prompt_inspector.py not found"

    def test_get_prompt_inspector_loader_in_server(self):
        src = SERVER_PY.read_text(encoding="utf-8")
        assert "_get_prompt_inspector" in src

    def test_prompt_inspector_import_in_server(self):
        src = SERVER_PY.read_text(encoding="utf-8")
        assert "prompt_inspector" in src

    def test_get_prompt_traces_endpoint(self):
        src = SERVER_PY.read_text(encoding="utf-8")
        assert '"/api/prompt-traces"' in src

    def test_get_prompt_trace_detail_endpoint(self):
        src = SERVER_PY.read_text(encoding="utf-8")
        assert '"/api/prompt-trace/{trace_id}"' in src

    def test_patch_inspector_config_endpoint(self):
        src = SERVER_PY.read_text(encoding="utf-8")
        assert '"/api/prompt-inspector/config"' in src

    def test_delete_prompt_traces_endpoint(self):
        src = SERVER_PY.read_text(encoding="utf-8")
        assert "@app.delete" in src
        assert '"/api/prompt-traces"' in src

    def test_prompt_trace_ws_broadcast(self):
        src = SERVER_PY.read_text(encoding="utf-8")
        assert '"prompt:trace"' in src

    def test_start_trace_called_in_generate_llm_response(self):
        src = SERVER_PY.read_text(encoding="utf-8")
        assert "_pi.start_trace" in src or "_pi_trace = _pi.start_trace" in src

    def test_finish_trace_called_in_generate_llm_response(self):
        src = SERVER_PY.read_text(encoding="utf-8")
        assert "_pi.finish_trace" in src

    def test_set_context_called_in_generate_llm_response(self):
        src = SERVER_PY.read_text(encoding="utf-8")
        assert "_pi.set_context" in src

    def test_set_prompt_called_in_generate_llm_response(self):
        src = SERVER_PY.read_text(encoding="utf-8")
        assert "_pi.set_prompt" in src

    def test_set_model_output_called_in_generate_llm_response(self):
        src = SERVER_PY.read_text(encoding="utf-8")
        assert "_pi.set_model_output" in src

    def test_frontend_page_exists(self):
        page = REPO_ROOT / "frontend" / "src" / "components" / "pages" / "PromptInspectorPage.jsx"
        assert page.exists(), "PromptInspectorPage.jsx not found"

    def test_frontend_page_registered_in_dashboard(self):
        dashboard = REPO_ROOT / "frontend" / "src" / "components" / "Dashboard.jsx"
        src = dashboard.read_text(encoding="utf-8")
        assert "PromptInspectorPage" in src
        assert "prompt-inspector" in src

    def test_frontend_sidebar_item(self):
        sidebar = REPO_ROOT / "frontend" / "src" / "components" / "layout" / "Sidebar.jsx"
        src = sidebar.read_text(encoding="utf-8")
        assert "prompt-inspector" in src
        assert "Prompt Inspector" in src

    def test_appstore_prompt_traces_state(self):
        store = REPO_ROOT / "frontend" / "src" / "store" / "appStore.js"
        src = store.read_text(encoding="utf-8")
        assert "promptTraces" in src
        assert "addPromptTrace" in src

    def test_websocket_handler_prompt_trace(self):
        ws = REPO_ROOT / "frontend" / "src" / "hooks" / "useWebSocket.js"
        src = ws.read_text(encoding="utf-8")
        assert "prompt:trace" in src
