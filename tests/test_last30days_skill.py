"""last30days runtime skill — registration + dispatch + graceful behavior.

Verifies the owner's forked last30days skill is replicated into the system as a
first-class, orchestrator-dispatchable skill (not the generic library executor) and
that it runs the vendored research code in offline --mock mode without API keys.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "runtime"))

from skills.catalog import get_skill_catalog  # noqa: E402
from skills.last30days_skill import Last30DaysSkill  # noqa: E402


def test_skill_registered_as_first_class_adapter():
    cat = get_skill_catalog()
    assert cat.has("last30days")
    skill = cat.get("last30days")
    # Must be the real subprocess adapter — not the generic ExecutableContentSkill
    # auto-built from the library entry (that one can't run the vendored research).
    assert isinstance(skill, Last30DaysSkill)
    assert skill.name == "last30days"
    assert "research" in skill.capability_tags


def test_empty_topic_is_rejected_without_spawning():
    skill = Last30DaysSkill()
    res = skill.execute({"topic": "   "}, lambda a, p: {})
    assert res["status"] == "error"
    assert "topic" in res["error"].lower()


def test_mock_run_returns_grounded_structure():
    skill = Last30DaysSkill()
    res = skill.execute({"topic": "AI video tools", "mock": True, "emit": "json"},
                        lambda a, p: {})
    assert res["status"] == "success", res.get("error")
    assert res["topic"] == "AI video tools"
    result = res["result"]
    assert isinstance(result, dict)
    # vendored CLI emits clustered, multi-source structure
    assert "items_by_source" in result and "topic" in result
    assert isinstance(res["elapsed_ms"], int)


def test_diagnose_reports_keyless_sources():
    skill = Last30DaysSkill()
    diag = skill.diagnose()
    assert diag.get("available") is True, diag.get("error")
    report = diag.get("report") or {}
    sources = report.get("available_sources") or []
    # keyless sources work out of the box (no API keys configured)
    assert "reddit" in sources and "hackernews" in sources
