"""One skill chain (coherence): SkillCatalog.dispatch_for_goal is the single
goal-shaped entry that the companion broker and agents share with the Executor.

Tries a tool-composing executable skill first, then the library LLM path.
"""
import sys
from types import ModuleType
from unittest.mock import MagicMock, patch

from skills.catalog import get_skill_catalog


def test_dispatch_empty_goal():
    assert get_skill_catalog().dispatch_for_goal("   ")["status"] == "error"


def test_dispatch_routes_to_executable_tool_skill():
    cat = get_skill_catalog()
    # Mock the ToolRegistry so the executable skill composes "tools" without real I/O.
    reg = MagicMock()
    reg.execute.return_value = {"ok": True, "data": "stub"}
    with patch("tools.registry.get_tool_registry", return_value=reg):
        out = cat.dispatch_for_goal("research the market for a saas product")
    assert out["status"] == "ok"
    assert out["via"] == "skill_catalog_tools"          # tool-composing chain, not LLM
    assert reg.execute.called                            # real tool dispatch happened


def test_dispatch_falls_back_to_library_llm():
    cat = get_skill_catalog()
    # No executable skill matches -> library LLM path.
    sel = ModuleType("forge.lifecycle.skill_selector")
    sel.select_skills = lambda goal, ttype, max_skills=1: [
        {"id": "poem", "name": "Poet", "system_prompt": "Write a poem.", "match_score": 0.9}
    ]
    sel._load_skills = lambda: []
    eng = ModuleType("engine.api")
    eng.generate = lambda prompt, system=None, context=None: "Roses are red."
    with patch.object(cat, "find_for_goal", return_value=[]), \
         patch.dict(sys.modules, {"forge.lifecycle.skill_selector": sel, "engine.api": eng}):
        out = cat.dispatch_for_goal("write me a short poem about the sea")
    assert out["status"] == "ok"
    assert out["via"] == "skill_library_llm"
    assert out["skill_id"] == "poem" and out["output"] == "Roses are red."


def test_dispatch_no_skill_is_honest():
    cat = get_skill_catalog()
    sel = ModuleType("forge.lifecycle.skill_selector")
    sel.select_skills = lambda goal, ttype, max_skills=1: []
    sel._load_skills = lambda: []
    with patch.object(cat, "find_for_goal", return_value=[]), \
         patch.dict(sys.modules, {"forge.lifecycle.skill_selector": sel}):
        out = cat.dispatch_for_goal("zzqq xxyy plplpl")
    assert out["status"] == "no_skill"          # honest, not a fabricated success


def test_broker_skills_run_delegates_to_catalog():
    from companion.execution_broker import ExecutionBroker
    sentinel = {"status": "ok", "via": "skill_catalog_tools", "skill_id": "x"}
    with patch("skills.catalog.get_skill_catalog") as gc:
        gc.return_value.dispatch_for_goal.return_value = sentinel
        out = ExecutionBroker._exec_skills_run(MagicMock(), {"goal": "do a thing"})
    assert out is sentinel
    gc.return_value.dispatch_for_goal.assert_called_once()
