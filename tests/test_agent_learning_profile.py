"""Tests for the Agent Learning Profile module (agent ↔ ladder coupling + grading)."""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

_RUNTIME = Path(__file__).parent.parent / "runtime"
if str(_RUNTIME) not in sys.path:
    sys.path.insert(0, str(_RUNTIME))


def _reload(module_name: str):
    module = importlib.import_module(module_name)
    return importlib.reload(module)


# ── Grade mapping ─────────────────────────────────────────────────────────────

def test_grade_map_keys(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_HOME", str(tmp_path))
    mod = _reload("core.agent_learning_profile")
    assert mod.GRADE_MAP[0] == "Ungraded"
    assert mod.GRADE_MAP[1] == "Beginner"
    assert mod.GRADE_MAP[2] == "Basic"
    assert mod.GRADE_MAP[3] == "Mature"
    assert mod.GRADE_MAP[4] == "Advanced"
    assert mod.GRADE_MAP[5] == "Pro"


def test_grade_rank_inverse(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_HOME", str(tmp_path))
    mod = _reload("core.agent_learning_profile")
    for lvl, name in mod.GRADE_MAP.items():
        assert mod.GRADE_RANK[name] == lvl


# ── assign_ladder ─────────────────────────────────────────────────────────────

def test_assign_ladder_returns_ungraded_initially(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_HOME", str(tmp_path))
    _reload("core.learning_ladder_builder")
    mod = _reload("core.agent_learning_profile")
    alp = mod.get_agent_learning_profile()

    result = alp.assign_ladder("lead-hunter", "B2B Lead Generation")
    assert result["agent_id"] == "lead-hunter"
    assert result["topic"] == "B2B Lead Generation"
    assert result["grade"] == "Ungraded"
    assert "ladder_id" in result
    assert "assigned_at" in result


def test_assign_ladder_builds_ladder(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_HOME", str(tmp_path))
    _reload("core.learning_ladder_builder")
    mod = _reload("core.agent_learning_profile")
    alp = mod.get_agent_learning_profile()

    alp.assign_ladder("email-ninja", "Email Marketing")
    profile = alp.get_agent_profile("email-ninja")
    assert profile["assignment"]["topic"] == "Email Marketing"
    assert profile["ladder_progress"] is not None
    assert profile["ladder_progress"]["ladder"]["topic"] == "Email Marketing"


def test_assign_ladder_requires_agent_id(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_HOME", str(tmp_path))
    _reload("core.learning_ladder_builder")
    mod = _reload("core.agent_learning_profile")
    alp = mod.get_agent_learning_profile()
    import pytest
    with pytest.raises(ValueError, match="agent_id"):
        alp.assign_ladder("", "Some Topic")


def test_assign_ladder_requires_topic(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_HOME", str(tmp_path))
    _reload("core.learning_ladder_builder")
    mod = _reload("core.agent_learning_profile")
    alp = mod.get_agent_learning_profile()
    import pytest
    with pytest.raises(ValueError, match="topic"):
        alp.assign_ladder("agent-x", "")


# ── advance ───────────────────────────────────────────────────────────────────

def test_advance_no_assignment_raises(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_HOME", str(tmp_path))
    _reload("core.learning_ladder_builder")
    mod = _reload("core.agent_learning_profile")
    alp = mod.get_agent_learning_profile()
    import pytest
    with pytest.raises(KeyError, match="no learning ladder"):
        alp.advance(agent_id="unassigned-bot", level=1, success=True, score=0.9)


def test_advance_level1_success_grants_beginner(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_HOME", str(tmp_path))
    _reload("core.learning_ladder_builder")
    mod = _reload("core.agent_learning_profile")
    alp = mod.get_agent_learning_profile()

    alp.assign_ladder("social-guru", "Social Media Marketing")
    result = alp.advance(
        agent_id="social-guru",
        level=1,
        success=True,
        score=0.85,
        milestone_output="Posted 3 social media drafts",
    )
    assert result["learned"] is True
    assert result["grade"] == "Beginner"
    assert result["grade_level"] == 1


def test_advance_level2_after_level1_grants_basic(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_HOME", str(tmp_path))
    _reload("core.learning_ladder_builder")
    mod = _reload("core.agent_learning_profile")
    alp = mod.get_agent_learning_profile()

    alp.assign_ladder("data-analyst", "Data Analysis")
    alp.advance(agent_id="data-analyst", level=1, success=True, score=0.9, milestone_output="Done")
    result = alp.advance(agent_id="data-analyst", level=2, success=True, score=0.8, milestone_output="Done 2")

    assert result["learned"] is True
    assert result["grade"] == "Basic"
    assert result["grade_level"] == 2


def test_advance_failure_does_not_upgrade_grade(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_HOME", str(tmp_path))
    _reload("core.learning_ladder_builder")
    mod = _reload("core.agent_learning_profile")
    alp = mod.get_agent_learning_profile()

    alp.assign_ladder("bot-fail", "Python programming")
    result = alp.advance(agent_id="bot-fail", level=1, success=False, score=0.3)
    assert result["learned"] is False
    assert result["grade"] == "Ungraded"


def test_advance_low_score_fails_anti_illusion(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_HOME", str(tmp_path))
    _reload("core.learning_ladder_builder")
    mod = _reload("core.agent_learning_profile")
    alp = mod.get_agent_learning_profile()

    alp.assign_ladder("weak-bot", "JavaScript")
    result = alp.advance(agent_id="weak-bot", level=1, success=True, score=0.3)
    assert result["learned"] is False
    assert result["grade"] == "Ungraded"


def test_advance_returns_brain_stored_flag(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_HOME", str(tmp_path))
    _reload("core.learning_ladder_builder")
    mod = _reload("core.agent_learning_profile")
    alp = mod.get_agent_learning_profile()

    alp.assign_ladder("agent-brain", "Sales Strategy")
    result = alp.advance(
        agent_id="agent-brain",
        level=1,
        success=True,
        score=0.9,
        milestone_output="Created a basic sales funnel",
    )
    assert "brain_stored" in result


def test_full_5_level_progression_earns_pro(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_HOME", str(tmp_path))
    _reload("core.learning_ladder_builder")
    mod = _reload("core.agent_learning_profile")
    alp = mod.get_agent_learning_profile()

    alp.assign_ladder("pro-bot", "Machine Learning")
    for lvl in range(1, 6):
        result = alp.advance(
            agent_id="pro-bot",
            level=lvl,
            success=True,
            score=0.9,
            milestone_output=f"Level {lvl} milestone done",
        )
    assert result["grade"] == "Pro"
    assert result["grade_level"] == 5


# ── get_agent_grade ────────────────────────────────────────────────────────────

def test_get_agent_grade_unassigned_returns_ungraded(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_HOME", str(tmp_path))
    _reload("core.learning_ladder_builder")
    mod = _reload("core.agent_learning_profile")
    alp = mod.get_agent_learning_profile()

    grade = alp.get_agent_grade("ghost-agent")
    assert grade["grade"] == "Ungraded"
    assert grade["grade_level"] == 0
    assert grade["topic"] is None


def test_get_agent_grade_after_progress(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_HOME", str(tmp_path))
    _reload("core.learning_ladder_builder")
    mod = _reload("core.agent_learning_profile")
    alp = mod.get_agent_learning_profile()

    alp.assign_ladder("grade-bot", "SEO")
    alp.advance(agent_id="grade-bot", level=1, success=True, score=0.8, milestone_output="Done")
    alp.advance(agent_id="grade-bot", level=2, success=True, score=0.75, milestone_output="Done 2")

    grade = alp.get_agent_grade("grade-bot")
    assert grade["grade"] == "Basic"
    assert grade["grade_level"] == 2


# ── get_all_profiles ──────────────────────────────────────────────────────────

def test_get_all_profiles_returns_list(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_HOME", str(tmp_path))
    _reload("core.learning_ladder_builder")
    mod = _reload("core.agent_learning_profile")
    alp = mod.get_agent_learning_profile()

    alp.assign_ladder("agent-a", "Topic A")
    alp.assign_ladder("agent-b", "Topic B")

    profiles = alp.get_all_profiles()
    ids = [p["agent_id"] for p in profiles]
    assert "agent-a" in ids
    assert "agent-b" in ids


def test_get_all_profiles_includes_grade_fields(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_HOME", str(tmp_path))
    _reload("core.learning_ladder_builder")
    mod = _reload("core.agent_learning_profile")
    alp = mod.get_agent_learning_profile()

    alp.assign_ladder("inspect-bot", "Content Writing")
    profiles = alp.get_all_profiles()
    p = next((x for x in profiles if x["agent_id"] == "inspect-bot"), None)
    assert p is not None
    assert "grade" in p
    assert "grade_level" in p
    assert "levels_completed" in p
    assert p["levels_total"] == 5


# ── metrics ───────────────────────────────────────────────────────────────────

def test_metrics_tracks_completions(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_HOME", str(tmp_path))
    _reload("core.learning_ladder_builder")
    mod = _reload("core.agent_learning_profile")
    alp = mod.get_agent_learning_profile()

    alp.assign_ladder("m-bot", "Rust programming")
    alp.advance(agent_id="m-bot", level=1, success=True, score=0.8, milestone_output="Done")

    m = alp.metrics()
    assert m["total_levels_completed"] >= 1
    assert "grade_distribution" in m


def test_metrics_grade_distribution_sums_correctly(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_HOME", str(tmp_path))
    _reload("core.learning_ladder_builder")
    mod = _reload("core.agent_learning_profile")
    alp = mod.get_agent_learning_profile()

    alp.assign_ladder("dist-a", "Go programming")
    alp.assign_ladder("dist-b", "TypeScript")
    alp.advance(agent_id="dist-a", level=1, success=True, score=0.9, milestone_output="Done")

    m = alp.metrics()
    dist = m["grade_distribution"]
    total = sum(dist.values())
    assert total == 2  # two agents
    assert dist["Beginner"] == 1
    assert dist["Ungraded"] == 1


# ── persistence ───────────────────────────────────────────────────────────────

def test_state_persists_across_instances(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_HOME", str(tmp_path))
    _reload("core.learning_ladder_builder")
    mod = _reload("core.agent_learning_profile")

    path = tmp_path / "state" / "agent_learning_profiles.json"

    alp1 = mod.AgentLearningProfile(path)
    alp1.assign_ladder("persist-bot", "DevOps")
    alp1.advance(agent_id="persist-bot", level=1, success=True, score=0.9, milestone_output="Done")

    alp2 = mod.AgentLearningProfile(path)
    grade = alp2.get_agent_grade("persist-bot")
    assert grade["grade"] == "Beginner"
    assert grade["grade_level"] == 1
