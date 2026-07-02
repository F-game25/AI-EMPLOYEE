"""C2/B2 — executable skill tool-chain interpreter.

Proves a skill's declared ``tool_steps`` run real ToolRegistry calls (not an
LLM prose pass), thread outputs, gate risky tools, and fail closed — while
skills WITHOUT a chain are unchanged (LLM path). See
docs/SYSTEM_COHERENCE_C2_PLAN.md B2.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "runtime"))

from skills.catalog import ExecutableSkillCatalog as E  # noqa: E402


class FakeRegistry:
    """Minimal ToolRegistry stand-in: risk map + recorded execute() calls."""

    RISK = {
        "web_search": 0, "read_file": 0, "llm_infer": 0, "get_memory": 0,
        "write_file": 1, "create_file": 1, "update_db": 1,
        "send_email": 3, "call_api": 3, "browser_fetch": 3, "shell_exec": 3,
    }

    def __init__(self, results=None, fail=None):
        self.calls = []
        self._results = results or {}
        self._fail = fail or set()

    def list_tools(self, max_risk=5):
        return [{"name": n, "risk_level": r} for n, r in self.RISK.items() if r <= max_risk]

    def execute(self, name, payload, agent_id="system"):
        self.calls.append((name, payload, agent_id))
        if name in self._fail:
            return {"ok": False, "tool": name, "error": "boom"}
        return {"ok": True, "tool": name, "result": self._results.get(name, f"{name}:done")}


@pytest.fixture
def patch_registry(monkeypatch):
    def _install(reg):
        monkeypatch.setattr("tools.registry.get_tool_registry", lambda: reg)
        return reg
    return _install


def test_no_tool_steps_returns_none():
    assert E._run_tool_chain({"id": "x"}, "goal", {}) is None
    assert E._run_tool_chain({"id": "x", "tool_steps": []}, "goal", {}) is None


def test_chain_runs_tools_in_order_and_threads_outputs(patch_registry):
    reg = patch_registry(FakeRegistry(results={"web_search": "RAW", "llm_infer": "SUMMARY"}))
    skill = {"id": "market_research", "name": "Market Research", "tool_steps": [
        {"tool": "web_search", "inputs": {"query": "{goal}"}, "save_as": "hits"},
        {"tool": "llm_infer", "inputs": {"prompt": "summarize {vars.hits}"}, "save_as": "output"},
    ]}
    out = E._run_tool_chain(skill, "AI market size", {})
    assert out["status"] == "ok" and out["via"] == "skill_tool_chain"
    assert out["tools"] == ["web_search", "llm_infer"]
    # order + templating
    assert reg.calls[0] == ("web_search", {"query": "AI market size"}, "system")
    assert reg.calls[1][0] == "llm_infer"
    assert reg.calls[1][1]["prompt"] == "summarize RAW"  # prior output threaded in
    assert out["output"] == "SUMMARY"                    # save_as=output wins


def test_risky_tool_blocked_by_default(patch_registry):
    patch_registry(FakeRegistry())
    skill = {"id": "e", "tool_steps": [
        {"tool": "send_email", "inputs": {"to": "a@b.c", "subject": "s", "body": "b"}}]}
    out = E._run_tool_chain(skill, "g", {})
    assert out["status"] == "blocked"
    assert out["blocked_tool"] == "send_email" and out["requires_approval"] is True


def test_risky_tool_runs_when_approved(patch_registry):
    reg = patch_registry(FakeRegistry())
    skill = {"id": "e", "tool_steps": [
        {"tool": "send_email", "inputs": {"to": "a@b.c"}, "save_as": "sent"}]}
    out = E._run_tool_chain(skill, "g", {"approved_tools": ["send_email"]})
    assert out["status"] == "ok"
    assert reg.calls[0][0] == "send_email"


def test_env_raises_autorisk_ceiling(patch_registry, monkeypatch):
    reg = patch_registry(FakeRegistry())
    monkeypatch.setenv("SKILL_CHAIN_MAX_AUTORISK", "3")
    skill = {"id": "e", "tool_steps": [{"tool": "call_api", "inputs": {"url": "x"}}]}
    out = E._run_tool_chain(skill, "g", {})
    assert out["status"] == "ok"  # risk-3 now auto-runnable


def test_unknown_tool_errors_and_stops(patch_registry):
    reg = patch_registry(FakeRegistry())
    skill = {"id": "u", "tool_steps": [
        {"tool": "web_search", "inputs": {"query": "{goal}"}},
        {"tool": "nope", "inputs": {}},
    ]}
    out = E._run_tool_chain(skill, "g", {})
    assert out["status"] == "error" and "unknown tool 'nope'" in out["error"]
    # first (valid) step ran; chain stopped before the unknown one
    assert [c[0] for c in reg.calls] == ["web_search"]


def test_step_failure_fails_closed(patch_registry):
    reg = patch_registry(FakeRegistry(fail={"write_file"}))
    skill = {"id": "f", "tool_steps": [
        {"tool": "web_search", "inputs": {"query": "{goal}"}, "save_as": "h"},
        {"tool": "write_file", "inputs": {"path": "/tmp/x", "content": "{vars.h}"}},
    ]}
    out = E._run_tool_chain(skill, "g", {})
    assert out["status"] == "error" and "write_file" in out["error"]
    assert len(out["steps"]) == 2 and out["steps"][1]["ok"] is False


def test_templating_strict_and_typed():
    r = E._resolve_inputs(
        {"a": "{goal}", "b": "{vars.k}", "c": "x-{ctx.u}-y", "n": 5},
        "find leads", {"u": "bob"}, {"k": [1, 2]})
    assert r["a"] == "find leads"
    assert r["b"] == [1, 2]            # whole-string placeholder preserves type
    assert r["c"] == "x-bob-y"          # ctx interpolation in a larger string
    assert r["n"] == 5                   # non-string passthrough


def test_templating_fails_closed_on_unresolved_placeholder():
    """A typo'd / unknown / not-yet-saved placeholder must STOP the chain, not
    coerce to '' and run the tool with a mutated arg (CodeRabbit hardening)."""
    # Unknown namespace.
    with pytest.raises(E.StrictTemplateError):
        E._resolve_inputs({"x": "{unknown}"}, "g", {}, {})
    # Missing prior-step var (e.g. {vars.hit} typo for {vars.hits}).
    with pytest.raises(E.StrictTemplateError):
        E._resolve_inputs({"x": "{vars.hit}"}, "g", {}, {"hits": 1})
    # Missing ctx key.
    with pytest.raises(E.StrictTemplateError):
        E._resolve_inputs({"x": "pre-{ctx.absent}-post"}, "g", {}, {})


def test_templating_fails_closed_on_malformed_inputs():
    """Non-dict step inputs are malformed → fail closed before any tool runs."""
    with pytest.raises(E.StrictTemplateError):
        E._resolve_inputs("not-a-dict", "g", {}, {})
    with pytest.raises(E.StrictTemplateError):
        E._resolve_inputs(["list", "not", "dict"], "g", {}, {})


def test_chain_stops_before_tool_on_bad_template(patch_registry):
    """End-to-end: a step with an unresolved placeholder returns an error
    envelope and NEVER calls the registry (no side effect)."""
    reg = patch_registry(FakeRegistry(results={"web_search": "DATA"}))
    skill = {"id": "bad", "name": "Bad", "tool_steps": [
        {"tool": "web_search", "inputs": {"query": "{vars.never_saved}"}, "save_as": "output"}]}
    out = E._run_tool_chain(skill, "scan leads", {})
    assert out["status"] == "error"
    assert "unresolved placeholder" in out["error"]
    assert reg.calls == []              # tool was never executed


def test_dispatch_for_goal_uses_chain_when_present(patch_registry, monkeypatch):
    """Integration: a library skill carrying tool_steps runs the chain via the
    one dispatch path (not the LLM fallback)."""
    reg = patch_registry(FakeRegistry(results={"web_search": "DATA"}))
    skill = {"id": "lead_scan", "name": "Lead Scan", "tool_steps": [
        {"tool": "web_search", "inputs": {"query": "{goal}"}, "save_as": "output"}]}
    monkeypatch.setattr("forge.lifecycle.skill_selector._load_skills", lambda: [skill])
    monkeypatch.setattr("forge.lifecycle.skill_selector.select_skills",
                        lambda *a, **k: [skill])
    from skills.catalog import get_skill_catalog
    cat = get_skill_catalog()
    # ctx.skill_id not in the code-registered _exec_skills → routes to library path
    out = cat.dispatch_for_goal("scan for B2B leads", {"skill_id": "lead_scan"})
    assert out["via"] == "skill_tool_chain" and out["status"] == "ok"
    assert out["output"] == "DATA"
