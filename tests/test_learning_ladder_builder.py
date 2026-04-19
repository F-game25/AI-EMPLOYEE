"""Tests for the Learning Ladder Builder module."""
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


# ── build_ladder ──────────────────────────────────────────────────────────────

def test_build_ladder_returns_five_levels(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_HOME", str(tmp_path))
    mod = _reload("core.learning_ladder_builder")
    builder = mod.get_learning_ladder_builder()
    ladder = builder.build_ladder("Python programming")

    assert ladder["topic"] == "Python programming"
    assert len(ladder["levels"]) == 5
    for level in ladder["levels"]:
        assert "level" in level
        assert "name" in level
        assert "description" in level
        assert isinstance(level["skills"], list)
        assert 3 <= len(level["skills"]) <= 5
        assert "milestone" in level


def test_build_ladder_level_names(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_HOME", str(tmp_path))
    mod = _reload("core.learning_ladder_builder")
    builder = mod.get_learning_ladder_builder()
    ladder = builder.build_ladder("Machine learning")

    names = [lvl["name"] for lvl in ladder["levels"]]
    assert names == ["Beginner", "Basic", "Intermediate", "Advanced", "Professional"]


def test_build_ladder_interpolates_topic(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_HOME", str(tmp_path))
    mod = _reload("core.learning_ladder_builder")
    builder = mod.get_learning_ladder_builder()
    ladder = builder.build_ladder("Docker")

    for level in ladder["levels"]:
        assert "Docker" in level["description"]
        assert all("Docker" in s for s in level["skills"])
        assert "Docker" in level["milestone"]


def test_build_ladder_cached_on_second_call(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_HOME", str(tmp_path))
    mod = _reload("core.learning_ladder_builder")
    builder = mod.get_learning_ladder_builder()
    ladder1 = builder.build_ladder("Redis")
    ladder2 = builder.build_ladder("Redis")
    assert ladder1["id"] == ladder2["id"]


def test_build_ladder_invalid_topic(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_HOME", str(tmp_path))
    mod = _reload("core.learning_ladder_builder")
    builder = mod.get_learning_ladder_builder()
    try:
        builder.build_ladder("")
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_build_ladder_persists_state(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_HOME", str(tmp_path))
    mod = _reload("core.learning_ladder_builder")
    builder = mod.get_learning_ladder_builder()
    builder.build_ladder("Kubernetes")
    assert (tmp_path / "state" / "learning_ladder.json").exists()


# ── record_level_completion ───────────────────────────────────────────────────

def test_record_success_marks_level_learned(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_HOME", str(tmp_path))
    mod = _reload("core.learning_ladder_builder")
    builder = mod.get_learning_ladder_builder()
    builder.build_ladder("SQL")
    result = builder.record_level_completion(
        topic="SQL",
        level=1,
        success=True,
        milestone_output="Built a simple SELECT query",
        score=0.9,
    )
    assert result["learned"] is True
    assert result["status"] == "completed"
    assert result["next_level"] == 2


def test_record_failure_marks_level_not_learned(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_HOME", str(tmp_path))
    mod = _reload("core.learning_ladder_builder")
    builder = mod.get_learning_ladder_builder()
    builder.build_ladder("SQL")
    result = builder.record_level_completion(
        topic="SQL",
        level=1,
        success=False,
        milestone_output="Could not complete",
        score=0.2,
    )
    assert result["learned"] is False
    assert result["status"] == "failed"
    # Level 2 blocked until level 1 completed
    assert result["next_level"] == 1


def test_anti_illusion_low_score_not_learned(tmp_path, monkeypatch):
    """Success=True but score < 0.5 → NOT LEARNED (anti-illusion protocol)."""
    monkeypatch.setenv("AI_HOME", str(tmp_path))
    mod = _reload("core.learning_ladder_builder")
    builder = mod.get_learning_ladder_builder()
    builder.build_ladder("Networking")
    result = builder.record_level_completion(
        topic="Networking",
        level=1,
        success=True,       # claims success
        milestone_output="vague explanation",
        score=0.3,          # but score too low
    )
    assert result["learned"] is False


def test_progression_gating(tmp_path, monkeypatch):
    """Cannot record level 3 before levels 1 and 2 are learned."""
    monkeypatch.setenv("AI_HOME", str(tmp_path))
    mod = _reload("core.learning_ladder_builder")
    builder = mod.get_learning_ladder_builder()
    builder.build_ladder("React")
    # Complete levels 1 and 2
    builder.record_level_completion(topic="React", level=1, success=True, score=0.9)
    builder.record_level_completion(topic="React", level=2, success=True, score=0.8)
    # Next level should be 3
    progress = builder.get_progress("React")
    assert progress["next_level"] == 3


def test_get_progress_returns_structure(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_HOME", str(tmp_path))
    mod = _reload("core.learning_ladder_builder")
    builder = mod.get_learning_ladder_builder()
    builder.build_ladder("CSS")
    progress = builder.get_progress("CSS")
    assert progress["topic"] == "CSS"
    assert progress["ladder"] is not None
    assert isinstance(progress["progress"], dict)
    assert progress["next_level"] == 1
    assert progress["completed"] is False


def test_completed_flag_when_all_levels_done(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_HOME", str(tmp_path))
    mod = _reload("core.learning_ladder_builder")
    builder = mod.get_learning_ladder_builder()
    builder.build_ladder("Git")
    for lvl in range(1, 6):
        builder.record_level_completion(topic="Git", level=lvl, success=True, score=0.85)
    progress = builder.get_progress("Git")
    assert progress["completed"] is True
    assert progress["next_level"] is None


# ── Adaptive intelligence ─────────────────────────────────────────────────────

def test_adaptation_break_into_sub_levels_after_3_failures(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_HOME", str(tmp_path))
    mod = _reload("core.learning_ladder_builder")
    builder = mod.get_learning_ladder_builder()
    builder.build_ladder("Rust")
    result = None
    for _ in range(3):
        result = builder.record_level_completion(
            topic="Rust", level=1, success=False, score=0.1
        )
    assert result["adaptation"]["action"] == "break_into_sub_levels"


def test_adaptation_accelerate_on_first_high_score(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_HOME", str(tmp_path))
    mod = _reload("core.learning_ladder_builder")
    builder = mod.get_learning_ladder_builder()
    builder.build_ladder("TypeScript")
    result = builder.record_level_completion(
        topic="TypeScript", level=1, success=True, score=0.95
    )
    assert result["adaptation"]["action"] == "accelerate_progression"


# ── Metrics ───────────────────────────────────────────────────────────────────

def test_metrics_track_counts(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_HOME", str(tmp_path))
    mod = _reload("core.learning_ladder_builder")
    builder = mod.get_learning_ladder_builder()
    builder.build_ladder("Go")
    builder.build_ladder("Rust")
    builder.record_level_completion(topic="Go", level=1, success=True, score=0.8)
    builder.record_level_completion(topic="Rust", level=1, success=False, score=0.1)

    m = builder.metrics()
    assert m["total_ladders_built"] == 2
    assert m["total_levels_attempted"] == 2
    assert m["total_levels_completed"] == 1
    assert m["total_levels_failed"] == 1
    assert m["total_topics"] == 2


# ── get_all_topics ────────────────────────────────────────────────────────────

def test_get_all_topics(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_HOME", str(tmp_path))
    mod = _reload("core.learning_ladder_builder")
    builder = mod.get_learning_ladder_builder()
    builder.build_ladder("Java")
    builder.build_ladder("Scala")
    topics = builder.get_all_topics()
    assert len(topics) == 2
    topic_names = [t["topic"] for t in topics]
    assert "Java" in topic_names
    assert "Scala" in topic_names


# ── invalid inputs ────────────────────────────────────────────────────────────

def test_record_invalid_level_raises(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_HOME", str(tmp_path))
    mod = _reload("core.learning_ladder_builder")
    builder = mod.get_learning_ladder_builder()
    builder.build_ladder("Haskell")
    try:
        builder.record_level_completion(topic="Haskell", level=6, success=True, score=0.9)
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_record_empty_topic_raises(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_HOME", str(tmp_path))
    mod = _reload("core.learning_ladder_builder")
    builder = mod.get_learning_ladder_builder()
    try:
        builder.record_level_completion(topic="", level=1, success=True, score=0.9)
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_get_ladder_returns_none_for_unknown_topic(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_HOME", str(tmp_path))
    mod = _reload("core.learning_ladder_builder")
    builder = mod.get_learning_ladder_builder()
    result = builder.get_ladder("totally unknown topic xyz")
    assert result is None


# ── Skill gaps ────────────────────────────────────────────────────────────────

def test_skill_gaps_recorded_on_failure(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_HOME", str(tmp_path))
    mod = _reload("core.learning_ladder_builder")
    builder = mod.get_learning_ladder_builder()
    builder.build_ladder("C++")
    builder.record_level_completion(
        topic="C++",
        level=1,
        success=False,
        score=0.2,
        notes="Cannot manage memory manually",
    )
    progress = builder.get_progress("C++")
    gaps = progress["progress"]["1"]["skill_gaps"]
    assert any("memory" in g.lower() for g in gaps)
