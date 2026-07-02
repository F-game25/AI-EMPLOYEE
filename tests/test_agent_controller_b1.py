"""C2/B1 — _emit_action routes through the skill catalog before bare LLM.

Verifies that AgentController._emit_action:
  1. Uses a tool-chain result when the skill has tool_steps  (via:skill_tool_chain)
  2. Uses a library-guided LLM result when no tool_steps     (via:skill_library_llm)
  3. Falls back to the bare role-prompt when skill is absent from the catalog
  4. Falls back to the bare role-prompt when the catalog import fails
  5. Propagates error status as RuntimeError (fail-closed)
  6. Propagates blocked status as RuntimeError (fail-closed)
  7. Catalog dispatch runs even with no LLM provider available (CodeRabbit,
     PR #334) — a tool_steps chain may not need an LLM at all
  8. A genuine exception from dispatch_for_goal() itself (not the catalog
     getter) is NOT silently swallowed into the bare-LLM fallback (CodeRabbit,
     PR #334) — it propagates so the caller fails closed instead of returning
     a degraded fake-success answer

All network/LLM/bus calls are mocked — no live infra required.
"""
import sys
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "runtime"))


# ── helpers ──────────────────────────────────────────────────────────────────

def _make_controller(monkeypatch):
    """Return an AgentController with heavy deps stubbed out."""
    from core.agent_controller import AgentController

    # Stub the constructor's heavy imports so we can instantiate without a
    # running backend.
    monkeypatch.setattr(
        "core.agent_controller.AgentController.__init__",
        lambda self: None,
    )
    ctrl = AgentController.__new__(AgentController)
    # _llm_provider_available must return True so we reach the executor branch.
    monkeypatch.setattr(
        "core.agent_controller.AgentController._llm_provider_available",
        lambda self: True,
    )
    return ctrl


def _stub_bus(monkeypatch, captured):
    """Patch the action bus (imported lazily inside _emit_action) so emit()
    calls executor(payload) directly and stores the result."""
    class _FakeBus:
        def emit(self, *, action_type, payload, actor, reason, executor):
            try:
                captured["result"] = executor(payload)
            except Exception as exc:
                captured["exc"] = exc
                raise
            return {"status": "executed", "result": captured["result"]}

    import actions.action_bus as _bus_mod
    monkeypatch.setattr(_bus_mod, "get_action_bus", lambda: _FakeBus())


def _stub_catalog(monkeypatch, dispatch_return):
    """Patch get_skill_catalog() (imported lazily inside executor) to return a
    fake catalog whose dispatch_for_goal returns a fixed dict."""
    class _FakeCatalog:
        def dispatch_for_goal(self, goal, ctx=None):
            return dispatch_return

    import skills.catalog as _catalog_mod
    monkeypatch.setattr(_catalog_mod, "get_skill_catalog", lambda: _FakeCatalog())


def _stub_generate(monkeypatch, text="llm-output"):
    """Patch engine.api.generate (imported lazily in the fallback branch)."""
    import engine.api as _engine_mod
    monkeypatch.setattr(_engine_mod, "generate", lambda **kw: text)


# ── test cases ────────────────────────────────────────────────────────────────

def test_tool_chain_result_used(monkeypatch):
    """via:skill_tool_chain with status:ok → executor returns the chain output."""
    ctrl = _make_controller(monkeypatch)
    captured = {}
    _stub_bus(monkeypatch, captured)
    _stub_catalog(monkeypatch, {
        "status": "ok",
        "via": "skill_tool_chain",
        "steps": [{"tool": "web_search", "result": "raw"}, {"tool": "llm_infer", "result": "SUMMARY"}],
        "output": "SUMMARY",
    })

    ctrl._emit_action("skill:market_research", {
        "skill": "market_research",
        "input": {"goal": "research SaaS market 2026"},
    })

    r = captured["result"]
    assert r["via"] == "skill_tool_chain"
    assert r["output"] == "SUMMARY"
    assert len(r["steps"]) == 2


def test_library_llm_result_used(monkeypatch):
    """via:skill_library_llm with status:ok → executor returns guided LLM output."""
    ctrl = _make_controller(monkeypatch)
    captured = {}
    _stub_bus(monkeypatch, captured)
    _stub_catalog(monkeypatch, {
        "status": "ok",
        "via": "skill_library_llm",
        "output": "GUIDED-LLM-OUTPUT",
    })

    ctrl._emit_action("skill:blog_writing", {
        "skill": "blog_writing",
        "input": {"goal": "write a blog about AI"},
    })

    r = captured["result"]
    assert r["via"] == "skill_library_llm"
    assert r["output"] == "GUIDED-LLM-OUTPUT"


def test_no_skill_falls_back_to_bare_llm(monkeypatch):
    """status:no_skill → graceful fallback to bare role-prompt LLM."""
    ctrl = _make_controller(monkeypatch)
    captured = {}
    _stub_bus(monkeypatch, captured)
    _stub_catalog(monkeypatch, {"status": "no_skill"})
    _stub_generate(monkeypatch, text="BARE-LLM-OUTPUT")

    ctrl._emit_action("skill:some_unknown_skill", {
        "skill": "some_unknown_skill",
        "input": {"goal": "do something"},
    })

    r = captured["result"]
    assert r["via"] == "llm_role_prompt"
    assert r["output"] == "BARE-LLM-OUTPUT"


def test_catalog_import_failure_falls_back_to_bare_llm(monkeypatch):
    """If get_skill_catalog() raises, treated as unavailable → bare LLM fallback."""
    ctrl = _make_controller(monkeypatch)
    captured = {}
    _stub_bus(monkeypatch, captured)

    # Simulate import failure inside the executor.
    def _raise():
        raise ImportError("catalog not importable in test")

    monkeypatch.setattr("skills.catalog.get_skill_catalog", _raise)
    _stub_generate(monkeypatch, text="FALLBACK-OUTPUT")

    ctrl._emit_action("skill:x", {
        "skill": "x",
        "input": {"goal": "do x"},
    })

    r = captured["result"]
    assert r["via"] == "llm_role_prompt"
    assert r["output"] == "FALLBACK-OUTPUT"


def test_error_status_propagates_as_runtime_error(monkeypatch):
    """status:error → executor raises RuntimeError (fail-closed, no fake success)."""
    ctrl = _make_controller(monkeypatch)
    captured = {}
    _stub_bus(monkeypatch, captured)
    _stub_catalog(monkeypatch, {
        "status": "error",
        "via": "skill_tool_chain",
        "error": "web_search: connection refused",
    })

    with pytest.raises(RuntimeError, match="web_search: connection refused"):
        ctrl._emit_action("skill:market_research", {
            "skill": "market_research",
            "input": {"goal": "research something"},
        })


def test_blocked_status_propagates_as_runtime_error(monkeypatch):
    """status:blocked → executor raises RuntimeError (deny-by-default gating)."""
    ctrl = _make_controller(monkeypatch)
    captured = {}
    _stub_bus(monkeypatch, captured)
    _stub_catalog(monkeypatch, {
        "status": "blocked",
        "via": "skill_tool_chain",
        "error": "tool 'send_email' risk_level=3 exceeds SKILL_CHAIN_MAX_AUTORISK=1",
    })

    with pytest.raises(RuntimeError, match="send_email"):
        ctrl._emit_action("skill:lead_scraping", {
            "skill": "lead_scraping",
            "input": {"goal": "find leads"},
        })


def test_catalog_dispatch_runs_without_llm_provider(monkeypatch):
    """A tool_steps chain must not require an LLM provider to run — only the
    bare role-prompt fallback branch needs one."""
    from core.agent_controller import AgentController

    monkeypatch.setattr(
        "core.agent_controller.AgentController.__init__",
        lambda self: None,
    )
    ctrl = AgentController.__new__(AgentController)
    # No LLM provider available at all.
    monkeypatch.setattr(
        "core.agent_controller.AgentController._llm_provider_available",
        lambda self: False,
    )
    captured = {}
    _stub_bus(monkeypatch, captured)
    _stub_catalog(monkeypatch, {
        "status": "ok",
        "via": "skill_tool_chain",
        "steps": [{"tool": "web_search", "result": "raw"}],
        "output": "TOOL-ONLY-OUTPUT",
    })

    ctrl._emit_action("skill:market_research", {
        "skill": "market_research",
        "input": {"goal": "research SaaS market 2026"},
    })

    r = captured["result"]
    assert r["via"] == "skill_tool_chain"
    assert r["output"] == "TOOL-ONLY-OUTPUT"


def test_dispatch_exception_not_swallowed_into_bare_llm_fallback(monkeypatch):
    """A genuine exception raised BY dispatch_for_goal() (not the catalog
    getter) must propagate, not be silently treated as 'unavailable' and
    masked by a degraded bare-LLM answer."""
    ctrl = _make_controller(monkeypatch)
    captured = {}
    _stub_bus(monkeypatch, captured)

    class _BrokenCatalog:
        def dispatch_for_goal(self, goal, ctx=None):
            raise ValueError("simulated tool-chain bug, not an import failure")

    import skills.catalog as _catalog_mod
    monkeypatch.setattr(_catalog_mod, "get_skill_catalog", lambda: _BrokenCatalog())
    _stub_generate(monkeypatch, text="SHOULD-NOT-BE-USED")

    with pytest.raises(ValueError, match="simulated tool-chain bug"):
        ctrl._emit_action("skill:market_research", {
            "skill": "market_research",
            "input": {"goal": "research something"},
        })
    assert "result" not in captured, "must not have produced a fake-success bare-LLM result"
