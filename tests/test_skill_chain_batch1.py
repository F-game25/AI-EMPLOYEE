"""C2/B2 — batch-1 skill tool-chain conversions.

Proves the first batch of revenue/lead/content/research skills carry a REAL,
executable ``tool_steps`` chain (not the LLM-only fallback): every step's tool
is registered and risk<=1 (auto-runs, no approval), the chain runs in order,
threads outputs, and synthesizes via ``llm_infer``. See
docs/SYSTEM_COHERENCE_C2_PLAN.md step 2.
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "runtime"))
sys.path.insert(0, str(ROOT))

from skills.catalog import ExecutableSkillCatalog as E  # noqa: E402
from scripts.convert_batch1_skill_chains import BATCH1  # noqa: E402

LIB = ROOT / "runtime" / "config" / "skills_library.json"

# Tools the chains may use, with their real registry risk levels.
# Both batch-1 tools are risk-0 → auto-run with no approval gate.
_RISK = {"web_search": 0, "llm_infer": 0, "read_file": 0, "get_memory": 0,
         "embed_text": 0, "write_file": 1, "create_file": 1}


@pytest.fixture(scope="module")
def skills_by_id():
    data = json.loads(LIB.read_text(encoding="utf-8"))
    return {s["id"]: s for s in data["skills"] if isinstance(s, dict) and s.get("id")}


@pytest.mark.parametrize("sid", BATCH1)
def test_batch1_skill_has_valid_chain(skills_by_id, sid):
    skill = skills_by_id.get(sid)
    assert skill is not None, f"{sid} missing from library"
    steps = skill.get("tool_steps")
    assert isinstance(steps, list) and steps, f"{sid} has no tool_steps"
    for i, step in enumerate(steps):
        assert isinstance(step, dict), f"{sid} step[{i}] not an object"
        tool = step.get("tool")
        assert tool in _RISK, f"{sid} step[{i}] tool '{tool}' not in auto-run set"
        # Auto-run safety: every batch-1 tool must be risk<=1 (no HITL gate).
        assert _RISK[tool] <= 1, f"{sid} step[{i}] tool '{tool}' exceeds risk ceiling"
        assert isinstance(step.get("inputs"), dict), f"{sid} step[{i}] inputs not a dict"


def test_batch1_chains_are_research_then_synthesize(skills_by_id):
    """Each batch-1 skill gathers evidence then synthesizes — a real multi-tool
    chain, never a single LLM blob."""
    for sid in BATCH1:
        steps = skills_by_id[sid]["tool_steps"]
        tools = [s["tool"] for s in steps]
        assert tools == ["web_search", "llm_infer"], f"{sid} chain = {tools}"
        # The synthesis prompt must carry the threaded research var + the goal,
        # and must label web findings as untrusted data (prompt-injection guard).
        prompt = steps[1]["inputs"]["prompt"]
        assert "{goal}" in prompt and "{vars.research}" in prompt, sid
        assert "UNTRUSTED" in prompt, f"{sid} prompt lacks untrusted-data guard"


class _RecordingRegistry:
    """Real risk map, recorded execute() — no network / no LLM."""
    RISK = _RISK

    def __init__(self):
        self.calls = []

    def list_tools(self, max_risk=5):
        return [{"name": n, "risk_level": r} for n, r in self.RISK.items() if r <= max_risk]

    def execute(self, name, payload, agent_id="system"):
        self.calls.append((name, payload))
        result = "SEARCH_HITS" if name == "web_search" else "SYNTHESIS"
        return {"ok": True, "tool": name, "result": result}


def test_batch1_skill_runs_real_chain(skills_by_id, monkeypatch):
    """End-to-end on a representative skill: the declared chain executes in
    order, threads the search result into the synthesis prompt, and returns
    via the tool-chain path (not the LLM fallback)."""
    reg = _RecordingRegistry()
    monkeypatch.setattr("tools.registry.get_tool_registry", lambda: reg)

    skill = skills_by_id["market_research"]
    out = E._run_tool_chain(skill, "size the EU EV-charging market", {})

    assert out["status"] == "ok" and out["via"] == "skill_tool_chain"
    assert out["tools"] == ["web_search", "llm_infer"]
    assert reg.calls[0] == ("web_search", {"query": "size the EU EV-charging market", "limit": 6})
    # search result threaded into the synthesis prompt; goal templated in
    synth_prompt = reg.calls[1][1]["prompt"]
    assert "SEARCH_HITS" in synth_prompt
    assert "size the EU EV-charging market" in synth_prompt
    assert out["output"] == "SYNTHESIS"


def test_batch1_chain_runs_with_default_risk_ceiling(skills_by_id, monkeypatch):
    """No env override: risk-0 tools must auto-run (nothing blocked)."""
    reg = _RecordingRegistry()
    monkeypatch.setattr("tools.registry.get_tool_registry", lambda: reg)
    monkeypatch.delenv("SKILL_CHAIN_MAX_AUTORISK", raising=False)
    for sid in BATCH1:
        out = E._run_tool_chain(skills_by_id[sid], "goal", {})
        assert out["status"] == "ok", f"{sid} blocked under default ceiling: {out}"
