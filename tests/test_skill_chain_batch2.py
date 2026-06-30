"""C2/B2 — batch-2 skill tool-chain conversions.

Proves the second batch of skills (business strategy, data analysis, and
content-writing) carry real, executable ``tool_steps`` chains:

  Pattern A (research + synthesis): web_search → llm_infer  — 8 skills
  Pattern B (pure synthesis):       llm_infer only           — 7 skills

Every step uses a risk-0 tool (auto-run, no approval gate). Pattern A
chains include the prompt-injection guard that labels web findings as
UNTRUSTED DATA. Pattern B chains operate on goal text only.

See docs/SYSTEM_COHERENCE_C2_PLAN.md step 2 / batch-2.
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "runtime"))
sys.path.insert(0, str(ROOT))

from skills.catalog import ExecutableSkillCatalog as E  # noqa: E402
from scripts.convert_batch2_skill_chains import BATCH2_RESEARCH, BATCH2_SYNTHESIS, BATCH2_ALL  # noqa: E402

LIB = ROOT / "runtime" / "config" / "skills_library.json"

_RISK = {
    "web_search": 0, "llm_infer": 0, "read_file": 0, "get_memory": 0,
    "embed_text": 0, "write_file": 1, "create_file": 1,
}


@pytest.fixture(scope="module")
def skills_by_id():
    data = json.loads(LIB.read_text(encoding="utf-8"))
    return {s["id"]: s for s in data["skills"] if isinstance(s, dict) and s.get("id")}


# ── contract shape ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("sid", BATCH2_ALL)
def test_batch2_skill_has_valid_chain(skills_by_id, sid):
    """Every batch-2 skill has a non-empty tool_steps list of risk-0 steps."""
    skill = skills_by_id.get(sid)
    assert skill is not None, f"{sid} missing from library"
    steps = skill.get("tool_steps")
    assert isinstance(steps, list) and steps, f"{sid} has no tool_steps"
    for i, step in enumerate(steps):
        assert isinstance(step, dict), f"{sid} step[{i}] not an object"
        tool = step.get("tool")
        assert tool in _RISK, f"{sid} step[{i}] tool '{tool}' not in auto-run set"
        assert _RISK[tool] <= 1, f"{sid} step[{i}] tool '{tool}' exceeds risk ceiling"
        assert isinstance(step.get("inputs"), dict), f"{sid} step[{i}] inputs not a dict"


@pytest.mark.parametrize("sid", BATCH2_RESEARCH)
def test_pattern_a_is_research_then_synthesize(skills_by_id, sid):
    """Pattern A: two-step chain — web_search → llm_infer with untrusted-data guard."""
    steps = skills_by_id[sid]["tool_steps"]
    tools = [s["tool"] for s in steps]
    assert tools == ["web_search", "llm_infer"], f"{sid} chain = {tools}"
    search_inputs = steps[0]["inputs"]
    assert "{goal}" in search_inputs.get("query", ""), f"{sid} search query lacks {{goal}}"
    prompt = steps[1]["inputs"]["prompt"]
    assert "{goal}" in prompt, f"{sid} synthesis prompt lacks {{goal}}"
    assert "{vars.research}" in prompt, f"{sid} synthesis prompt lacks {{vars.research}}"
    assert "UNTRUSTED" in prompt, f"{sid} synthesis prompt lacks injection guard"


@pytest.mark.parametrize("sid", BATCH2_SYNTHESIS)
def test_pattern_b_is_pure_synthesis(skills_by_id, sid):
    """Pattern B: single llm_infer step — no web search, goal templated in."""
    steps = skills_by_id[sid]["tool_steps"]
    tools = [s["tool"] for s in steps]
    assert tools == ["llm_infer"], f"{sid} chain = {tools}"
    prompt = steps[0]["inputs"]["prompt"]
    assert "{goal}" in prompt, f"{sid} synthesis prompt lacks {{goal}}"
    # Pattern B must NOT include {vars.research} — no prior web-search var
    assert "{vars.research}" not in prompt, f"{sid} pattern B prompt references {'{vars.research}'}"


# ── risk ceiling ──────────────────────────────────────────────────────────────

class _RecordingRegistry:
    RISK = _RISK

    def __init__(self, result_map=None):
        self.calls: list = []
        self._results = result_map or {}

    def list_tools(self, max_risk=5):
        return [{"name": n, "risk_level": r} for n, r in self.RISK.items() if r <= max_risk]

    def execute(self, name, payload, agent_id="system"):
        self.calls.append((name, payload))
        result = self._results.get(name, f"{name}:done")
        return {"ok": True, "tool": name, "result": result}


def test_batch2_all_auto_run_under_default_ceiling(skills_by_id, monkeypatch):
    """No env override: all batch-2 skills auto-run (nothing blocked)."""
    reg = _RecordingRegistry()
    monkeypatch.setattr("tools.registry.get_tool_registry", lambda: reg)
    monkeypatch.delenv("SKILL_CHAIN_MAX_AUTORISK", raising=False)
    for sid in BATCH2_ALL:
        out = E._run_tool_chain(skills_by_id[sid], "goal", {})
        assert out is not None and out["status"] == "ok", (
            f"{sid} blocked under default ceiling: {out}"
        )


# ── end-to-end execution ──────────────────────────────────────────────────────

def test_pattern_a_skill_threads_search_into_synthesis(skills_by_id, monkeypatch):
    """Pattern A: search result is threaded into the synthesis prompt."""
    reg = _RecordingRegistry(result_map={"web_search": "RESEARCH_HITS", "llm_infer": "PLAN"})
    monkeypatch.setattr("tools.registry.get_tool_registry", lambda: reg)

    skill = skills_by_id["business_plan_generation"]
    out = E._run_tool_chain(skill, "build a SaaS business plan", {})

    assert out["status"] == "ok" and out["via"] == "skill_tool_chain"
    assert out["tools"] == ["web_search", "llm_infer"]
    assert reg.calls[0] == ("web_search", {"query": "build a SaaS business plan", "limit": 6})
    synth_prompt = reg.calls[1][1]["prompt"]
    assert "RESEARCH_HITS" in synth_prompt      # threaded from step-1 output
    assert "build a SaaS business plan" in synth_prompt
    assert out["output"] == "PLAN"


def test_pattern_b_skill_runs_synthesis_directly(skills_by_id, monkeypatch):
    """Pattern B: single llm_infer call, goal in prompt, no web_search."""
    reg = _RecordingRegistry(result_map={"llm_infer": "EMAIL_DRAFT"})
    monkeypatch.setattr("tools.registry.get_tool_registry", lambda: reg)

    skill = skills_by_id["email_copywriting"]
    out = E._run_tool_chain(skill, "write a cold outreach email for AI devtools", {})

    assert out["status"] == "ok" and out["via"] == "skill_tool_chain"
    assert out["tools"] == ["llm_infer"]
    assert len(reg.calls) == 1, "Pattern B must not call web_search"
    prompt = reg.calls[0][1]["prompt"]
    assert "write a cold outreach email for AI devtools" in prompt
    assert out["output"] == "EMAIL_DRAFT"


def test_batch2_total_executable_skills():
    """Running count: 27 skills now have tool_steps (12 batch-1 + 15 batch-2)."""
    data = json.loads(LIB.read_text(encoding="utf-8"))
    total = sum(1 for s in data["skills"] if s.get("tool_steps"))
    assert total == 27, f"Expected 27 executable skills, got {total}"
