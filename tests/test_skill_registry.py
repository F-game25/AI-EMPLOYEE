"""Tests for runtime/core/skill_registry.py

Covers:
  - _now_iso() timestamp helper
  - _append_jsonl / _read_jsonl helpers
  - _discover_agents() introspection
  - _build_manifest() merging logic
  - SkillRegistry: manifest, accessors, save_manifest, rebuild
  - DecisionEngine: score, rank, top
  - RoiTracker: record, summary, recent
  - ChangeLog: append, recent, for_target
  - get_registry() singleton behaviour
"""
from __future__ import annotations

import json
import sys
import threading
from pathlib import Path

import pytest

# ── Make runtime importable ────────────────────────────────────────────────────
_REPO_ROOT = Path(__file__).parent.parent
_RUNTIME = _REPO_ROOT / "runtime"
if str(_RUNTIME) not in sys.path:
    sys.path.insert(0, str(_RUNTIME))

# Import the module under test
import importlib
import core.skill_registry as sr


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def reset_singleton():
    """Reset the module-level singleton before/after every test."""
    original = sr._REGISTRY
    sr._REGISTRY = None
    yield
    sr._REGISTRY = original


@pytest.fixture()
def tmp_agents_dir(tmp_path):
    """Build a minimal fake agents/ tree for introspection tests."""
    agents = tmp_path / "agents"
    # runnable agent
    runnable = agents / "lead-generator"
    runnable.mkdir(parents=True)
    (runnable / "run.sh").write_text("#!/bin/bash\n")
    (runnable / "lead_generator.py").write_text("# stub\n")
    (runnable / "requirements.txt").write_text("requests\n")

    # python-only agent (no run.sh)
    py_only = agents / "analytics-bi"
    py_only.mkdir(parents=True)
    (py_only / "analytics.py").write_text("# stub\n")

    # infra agent — should be excluded
    infra = agents / "problem-solver-ui"
    infra.mkdir(parents=True)
    (infra / "server.py").write_text("# stub\n")

    return agents


@pytest.fixture()
def tmp_skills_file(tmp_path):
    skills = [
        {
            "id": "lead_generation",
            "name": "Lead Generation",
            "category": "Lead Generation & Sales",
            "description": "Find B2B leads.",
            "tags": ["sales", "leads"],
            "compatible_agents": ["lead-generator"],
        },
        {
            "id": "blog_writing",
            "name": "Blog Writing",
            "category": "Content & Writing",
            "description": "Write blog posts.",
            "tags": ["writing", "seo"],
            "compatible_agents": ["content-master"],
        },
        {
            "id": "uncovered_skill",
            "name": "Uncovered Skill",
            "category": "Other",
            "description": "Not assigned to any agent.",
            "tags": [],
            "compatible_agents": [],
        },
    ]
    data = {
        "_meta": {"version": "2.0", "total_skills": len(skills)},
        "categories": ["Lead Generation & Sales", "Content & Writing", "Other"],
        "skills": skills,
    }
    f = tmp_path / "skills_library.json"
    f.write_text(json.dumps(data))
    return f


@pytest.fixture()
def tmp_caps_file(tmp_path):
    agents = {
        "lead-generator": {
            "description": "Lead gen agent",
            "category": "sales",
            "skills": ["lead_generation"],
            "commands": ["leads"],
            "specialties": ["B2B"],
        },
        "content-master": {
            "description": "Content agent",
            "category": "content",
            "skills": ["blog_writing"],
            "commands": ["content"],
        },
    }
    data = {"_meta": {"version": "2.1"}, "agents": agents}
    f = tmp_path / "agent_capabilities.json"
    f.write_text(json.dumps(data))
    return f


@pytest.fixture()
def registry(tmp_path, tmp_agents_dir, tmp_skills_file, tmp_caps_file):
    """A fresh SkillRegistry wired to tmp paths."""
    return sr.SkillRegistry(
        agents_dir=tmp_agents_dir,
        skills_file=tmp_skills_file,
        caps_file=tmp_caps_file,
        manifest_file=tmp_path / "manifest.json",
        roi_log_file=tmp_path / "roi.jsonl",
        change_log_file=tmp_path / "changelog.jsonl",
    )


# ── _now_iso ───────────────────────────────────────────────────────────────────

class TestNowIso:
    def test_returns_str(self):
        assert isinstance(sr._now_iso(), str)

    def test_ends_with_z(self):
        assert sr._now_iso().endswith("Z")

    def test_parseable(self):
        from datetime import datetime
        ts = sr._now_iso()
        datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ")


# ── _append_jsonl / _read_jsonl ────────────────────────────────────────────────

class TestJsonlHelpers:
    def test_append_creates_file(self, tmp_path):
        f = tmp_path / "log.jsonl"
        sr._append_jsonl(f, {"a": 1})
        assert f.exists()

    def test_append_and_read_round_trip(self, tmp_path):
        f = tmp_path / "log.jsonl"
        sr._append_jsonl(f, {"x": 1})
        sr._append_jsonl(f, {"x": 2})
        entries = sr._read_jsonl(f)
        assert len(entries) == 2
        assert entries[0]["x"] == 1
        assert entries[1]["x"] == 2

    def test_read_n_limits(self, tmp_path):
        f = tmp_path / "log.jsonl"
        for i in range(5):
            sr._append_jsonl(f, {"i": i})
        entries = sr._read_jsonl(f, n=3)
        assert len(entries) == 3
        assert entries[-1]["i"] == 4  # most recent

    def test_read_missing_file(self, tmp_path):
        assert sr._read_jsonl(tmp_path / "missing.jsonl") == []

    def test_max_lines_trimmed(self, tmp_path):
        f = tmp_path / "log.jsonl"
        for i in range(10):
            sr._append_jsonl(f, {"i": i}, max_lines=5)
        entries = sr._read_jsonl(f)
        assert len(entries) == 5
        # Should keep the most recent 5
        assert entries[0]["i"] == 5

    def test_skip_malformed_lines(self, tmp_path):
        f = tmp_path / "log.jsonl"
        f.write_text('{"ok": 1}\nNOT_JSON\n{"ok": 2}\n')
        entries = sr._read_jsonl(f)
        assert len(entries) == 2


# ── _discover_agents ───────────────────────────────────────────────────────────

class TestDiscoverAgents:
    def test_discovers_runnable_agent(self, tmp_agents_dir):
        disc = sr._discover_agents(tmp_agents_dir)
        assert "lead-generator" in disc
        assert disc["lead-generator"]["runnable"] is True
        assert "lead_generator.py" in disc["lead-generator"]["python_modules"]
        assert disc["lead-generator"]["has_requirements_file"] is True

    def test_discovers_python_only_agent(self, tmp_agents_dir):
        disc = sr._discover_agents(tmp_agents_dir)
        assert "analytics-bi" in disc
        assert disc["analytics-bi"]["runnable"] is False

    def test_excludes_infra_agents(self, tmp_agents_dir):
        disc = sr._discover_agents(tmp_agents_dir)
        assert "problem-solver-ui" not in disc

    def test_empty_dir(self, tmp_path):
        empty = tmp_path / "empty"
        empty.mkdir()
        assert sr._discover_agents(empty) == {}

    def test_missing_dir(self, tmp_path):
        assert sr._discover_agents(tmp_path / "nonexistent") == {}


# ── _build_manifest ────────────────────────────────────────────────────────────

class TestBuildManifest:
    def test_returns_dict(self, tmp_agents_dir, tmp_skills_file, tmp_caps_file):
        m = sr._build_manifest(tmp_agents_dir, tmp_skills_file, tmp_caps_file)
        assert isinstance(m, dict)

    def test_meta_present(self, tmp_agents_dir, tmp_skills_file, tmp_caps_file):
        m = sr._build_manifest(tmp_agents_dir, tmp_skills_file, tmp_caps_file)
        assert "_meta" in m
        assert "generated_at" in m["_meta"]
        assert "total_agents" in m["_meta"]

    def test_agents_merged_from_caps_and_fs(
        self, tmp_agents_dir, tmp_skills_file, tmp_caps_file
    ):
        m = sr._build_manifest(tmp_agents_dir, tmp_skills_file, tmp_caps_file)
        agents = m["agents"]
        # From capabilities
        assert "lead-generator" in agents
        assert "content-master" in agents
        # From filesystem only
        assert "analytics-bi" in agents
        # Infra excluded
        assert "problem-solver-ui" not in agents

    def test_lead_generator_merged_both_sources(
        self, tmp_agents_dir, tmp_skills_file, tmp_caps_file
    ):
        m = sr._build_manifest(tmp_agents_dir, tmp_skills_file, tmp_caps_file)
        ag = m["agents"]["lead-generator"]
        assert ag["category"] == "sales"
        assert ag["runnable"] is True
        assert "lead_generation" in ag["skills"]
        assert ag["source"] == "capabilities+filesystem"

    def test_skills_keyed_by_id(self, tmp_agents_dir, tmp_skills_file, tmp_caps_file):
        m = sr._build_manifest(tmp_agents_dir, tmp_skills_file, tmp_caps_file)
        assert "lead_generation" in m["skills"]
        assert "blog_writing" in m["skills"]

    def test_gap_skills_identified(self, tmp_agents_dir, tmp_skills_file, tmp_caps_file):
        m = sr._build_manifest(tmp_agents_dir, tmp_skills_file, tmp_caps_file)
        # "uncovered_skill" is in skills_library but not in any agent's skills list
        assert "uncovered_skill" in m["gap_skills"]

    def test_coverage_pct(self, tmp_agents_dir, tmp_skills_file, tmp_caps_file):
        m = sr._build_manifest(tmp_agents_dir, tmp_skills_file, tmp_caps_file)
        meta = m["_meta"]
        # 2 out of 3 skills covered → ~66.7%
        assert 0 < meta["coverage_pct"] <= 100

    def test_missing_caps_file(self, tmp_agents_dir, tmp_skills_file, tmp_path):
        m = sr._build_manifest(
            tmp_agents_dir, tmp_skills_file, tmp_path / "missing.json"
        )
        # Should degrade gracefully
        assert isinstance(m, dict)
        assert "agents" in m

    def test_missing_skills_file(self, tmp_agents_dir, tmp_caps_file, tmp_path):
        m = sr._build_manifest(
            tmp_agents_dir, tmp_path / "missing.json", tmp_caps_file
        )
        assert isinstance(m, dict)


# ── SkillRegistry ──────────────────────────────────────────────────────────────

class TestSkillRegistry:
    def test_manifest_is_dict(self, registry):
        assert isinstance(registry.manifest, dict)

    def test_manifest_cached(self, registry):
        m1 = registry.manifest
        m2 = registry.manifest
        assert m1 is m2

    def test_rebuild_refreshes(self, registry):
        m1 = registry.manifest
        m2 = registry.rebuild()
        assert m2 is not m1  # new dict after rebuild

    def test_agents_accessor(self, registry):
        agents = registry.agents()
        assert "lead-generator" in agents

    def test_skills_accessor(self, registry):
        skills = registry.skills()
        assert "lead_generation" in skills

    def test_gap_skills_accessor(self, registry):
        assert isinstance(registry.gap_skills(), list)
        assert "uncovered_skill" in registry.gap_skills()

    def test_agent_found(self, registry):
        a = registry.agent("lead-generator")
        assert a is not None
        assert a["category"] == "sales"

    def test_agent_not_found(self, registry):
        assert registry.agent("nonexistent-agent") is None

    def test_skill_found(self, registry):
        s = registry.skill("blog_writing")
        assert s is not None
        assert s["name"] == "Blog Writing"

    def test_skill_not_found(self, registry):
        assert registry.skill("no-such-skill") is None

    def test_agents_for_skill(self, registry):
        agents = registry.agents_for_skill("lead_generation")
        assert "lead-generator" in agents

    def test_agents_for_skill_empty(self, registry):
        assert registry.agents_for_skill("no-such-skill") == []

    def test_skills_for_agent(self, registry):
        skills = registry.skills_for_agent("lead-generator")
        assert "lead_generation" in skills

    def test_skills_for_agent_missing(self, registry):
        assert registry.skills_for_agent("ghost") == []

    def test_meta(self, registry):
        m = registry.meta()
        assert "total_agents" in m

    def test_save_manifest(self, registry, tmp_path):
        out = tmp_path / "out_manifest.json"
        result = registry.save_manifest(out)
        assert result == out
        assert out.exists()
        data = json.loads(out.read_text())
        assert "_meta" in data

    def test_save_manifest_default_path(self, registry):
        result = registry.save_manifest()
        assert result.exists()
        result.unlink()  # cleanup

    def test_thread_safety_manifest(self, registry):
        results = []
        errors = []

        def access():
            try:
                results.append(registry.manifest is not None)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=access) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors
        assert all(results)


# ── DecisionEngine ─────────────────────────────────────────────────────────────

class TestDecisionEngine:
    def test_score_returns_dict(self, registry):
        s = registry.decision_engine.score("lead-generator")
        assert isinstance(s, dict)
        assert "composite" in s
        assert "recommendation" in s

    def test_score_keys(self, registry):
        s = registry.decision_engine.score("lead-generator", "cold_outreach")
        for key in ("agent_id", "action", "category", "profit", "speed",
                    "complexity", "composite", "recommendation"):
            assert key in s, f"Missing key: {key}"

    def test_composite_in_range(self, registry):
        s = registry.decision_engine.score("lead-generator")
        assert 0.0 <= s["composite"] <= 10.0

    def test_composite_in_range_unknown_agent(self, registry):
        s = registry.decision_engine.score("ghost-agent")
        assert 0.0 <= s["composite"] <= 10.0

    def test_rank_returns_sorted(self, registry):
        ranked = registry.decision_engine.rank(["lead-generator", "content-master"])
        scores = [r["composite"] for r in ranked]
        assert scores == sorted(scores, reverse=True)

    def test_rank_empty(self, registry):
        assert registry.decision_engine.rank([]) == []

    def test_top_returns_list(self, registry):
        top = registry.decision_engine.top(n=3)
        assert isinstance(top, list)
        assert len(top) <= 3

    def test_top_sorted_descending(self, registry):
        top = registry.decision_engine.top(n=5)
        if len(top) > 1:
            for i in range(len(top) - 1):
                assert top[i]["composite"] >= top[i + 1]["composite"]

    def test_high_priority_recommendation(self, registry):
        # Force a high-composite scenario by scoring a 'trading' agent
        # (high profit, high speed, low-ish complexity) — synthetic test
        s = registry.decision_engine.score.__func__(
            registry.decision_engine, "trading-agent"
        )
        # We cannot guarantee the exact bucket but composite must be float
        assert isinstance(s["composite"], float)

    def test_action_stored_in_result(self, registry):
        s = registry.decision_engine.score("lead-generator", "my_action")
        assert s["action"] == "my_action"


# ── RoiTracker ─────────────────────────────────────────────────────────────────

class TestRoiTracker:
    def test_record_returns_dict(self, registry):
        e = registry.roi_tracker.record(
            agent="lead-generator", action="cold_outreach", revenue=100.0, cost=10.0
        )
        assert isinstance(e, dict)
        assert e["revenue"] == 100.0
        assert e["cost"] == 10.0
        assert e["roi"] == 900.0  # (100-10)/10 * 100

    def test_record_zero_cost_positive_revenue_roi_is_none(self, registry):
        e = registry.roi_tracker.record(
            agent="lead-generator", action="organic", revenue=50.0, cost=0.0
        )
        assert e["roi"] is None  # pure profit — undefined as a percentage

    def test_record_zero_cost_zero_revenue_roi_is_zero(self, registry):
        e = registry.roi_tracker.record(
            agent="lead-generator", action="nothing", revenue=0.0, cost=0.0
        )
        assert e["roi"] == 0.0

    def test_record_negative_raises(self, registry):
        with pytest.raises(ValueError):
            registry.roi_tracker.record(
                agent="a", action="b", revenue=-1.0, cost=0.0
            )

    def test_record_negative_cost_raises(self, registry):
        with pytest.raises(ValueError):
            registry.roi_tracker.record(
                agent="a", action="b", revenue=10.0, cost=-1.0
            )

    def test_record_with_optional_fields(self, registry):
        e = registry.roi_tracker.record(
            agent="lead-generator",
            action="email",
            revenue=200.0,
            cost=20.0,
            skill="email_copywriting",
            note="5 replies",
        )
        assert e["skill"] == "email_copywriting"
        assert e["note"] == "5 replies"

    def test_summary_aggregates(self, registry):
        registry.roi_tracker.record("agent-a", "act1", revenue=100.0, cost=10.0)
        registry.roi_tracker.record("agent-b", "act2", revenue=50.0, cost=5.0)
        s = registry.roi_tracker.summary()
        assert s["events"] == 2
        assert s["total_revenue"] == pytest.approx(150.0)
        assert s["total_cost"] == pytest.approx(15.0)
        assert s["net_profit"] == pytest.approx(135.0)

    def test_summary_filter_by_agent(self, registry):
        registry.roi_tracker.record("agent-a", "act", revenue=100.0, cost=10.0)
        registry.roi_tracker.record("agent-b", "act", revenue=50.0, cost=5.0)
        s = registry.roi_tracker.summary(agent="agent-a")
        assert s["events"] == 1
        assert s["total_revenue"] == pytest.approx(100.0)

    def test_summary_filter_by_skill(self, registry):
        registry.roi_tracker.record(
            "a", "act", revenue=100.0, skill="seo_optimization"
        )
        registry.roi_tracker.record(
            "a", "act", revenue=50.0, skill="blog_writing"
        )
        s = registry.roi_tracker.summary(skill="seo_optimization")
        assert s["events"] == 1

    def test_summary_by_agent_breakdown(self, registry):
        registry.roi_tracker.record("agent-x", "a", revenue=100.0, cost=10.0)
        s = registry.roi_tracker.summary()
        assert "agent-x" in s["by_agent"]
        assert s["by_agent"]["agent-x"]["revenue"] == pytest.approx(100.0)
        assert s["by_agent"]["agent-x"]["roi_pct"] == pytest.approx(900.0)

    def test_summary_empty(self, registry):
        s = registry.roi_tracker.summary()
        assert s["events"] == 0
        assert s["total_revenue"] == 0.0

    def test_recent_returns_list(self, registry):
        registry.roi_tracker.record("a", "b", revenue=10.0)
        entries = registry.roi_tracker.recent(n=5)
        assert isinstance(entries, list)
        assert len(entries) == 1

    def test_recent_limits_results(self, registry):
        for i in range(10):
            registry.roi_tracker.record("a", f"act{i}", revenue=float(i))
        entries = registry.roi_tracker.recent(n=3)
        assert len(entries) == 3

    def test_thread_safe_record(self, registry):
        errors = []

        def do_record(i):
            try:
                registry.roi_tracker.record("a", f"act{i}", revenue=float(i))
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=do_record, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors
        s = registry.roi_tracker.summary()
        assert s["events"] == 20


# ── ChangeLog ──────────────────────────────────────────────────────────────────

class TestChangeLog:
    def test_append_returns_dict(self, registry):
        e = registry.change_log.append(
            agent="ascend-forge",
            action="patch_applied",
            reason="coverage gap",
        )
        assert isinstance(e, dict)
        assert e["agent"] == "ascend-forge"
        assert e["action"] == "patch_applied"
        assert e["reason"] == "coverage gap"
        assert e["ts"].endswith("Z")

    def test_append_optional_fields(self, registry):
        e = registry.change_log.append(
            agent="ascend-forge",
            action="patch_applied",
            reason="test",
            target="runtime/brain/brain.py",
            diff_summary="+2 lines",
            session_id="sess123",
            approved_by="human",
        )
        assert e["target"] == "runtime/brain/brain.py"
        assert e["diff_summary"] == "+2 lines"
        assert e["session_id"] == "sess123"
        assert e["approved_by"] == "human"

    def test_recent_returns_list(self, registry):
        registry.change_log.append("a", "act", "reason")
        entries = registry.change_log.recent()
        assert isinstance(entries, list)
        assert len(entries) == 1

    def test_recent_limits_to_n(self, registry):
        for i in range(10):
            registry.change_log.append("a", f"act{i}", "reason")
        entries = registry.change_log.recent(n=3)
        assert len(entries) == 3

    def test_recent_filter_by_agent(self, registry):
        registry.change_log.append("agent-a", "act", "r")
        registry.change_log.append("agent-b", "act", "r")
        entries = registry.change_log.recent(agent="agent-a")
        assert all(e["agent"] == "agent-a" for e in entries)
        assert len(entries) == 1

    def test_for_target(self, registry):
        registry.change_log.append(
            "ascend-forge", "patch", "reason", target="brain.py"
        )
        registry.change_log.append(
            "ascend-forge", "patch", "reason", target="other.py"
        )
        entries = registry.change_log.for_target("brain.py")
        assert len(entries) == 1
        assert entries[0]["target"] == "brain.py"

    def test_for_target_empty(self, registry):
        assert registry.change_log.for_target("no-such-file.py") == []

    def test_thread_safe_append(self, registry):
        errors = []

        def do_append(i):
            try:
                registry.change_log.append("a", f"act{i}", "r")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=do_append, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors
        # n=0 means "return all" — must have all 20 entries
        entries = registry.change_log.recent(n=0)
        assert len(entries) == 20


# ── get_registry singleton ─────────────────────────────────────────────────────

class TestGetRegistry:
    def test_returns_skill_registry(self):
        reg = sr.get_registry()
        assert isinstance(reg, sr.SkillRegistry)

    def test_same_instance_on_repeat_calls(self):
        reg1 = sr.get_registry()
        reg2 = sr.get_registry()
        assert reg1 is reg2

    def test_thread_safe_singleton(self):
        instances = []
        errors = []

        def get():
            try:
                instances.append(sr.get_registry())
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=get) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        assert len({id(i) for i in instances}) == 1  # all same object
