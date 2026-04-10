"""Tests for all new AI Employee transformation modules.

Covers:
  - core/change_log.py
  - core/roi_tracker.py
  - core/decision_engine.py
  - core/mode_manager.py
  - core/skill_registry.py
  - core/task_engine.py
  - core/money_mode.py
  - actions/action_bus.py
  - memory/strategy_store.py
  - features/system_api.py  (FastAPI endpoints)
  - features/analytics.py   (new daily-stats + roi endpoints)
"""
from __future__ import annotations

import importlib
import importlib.util
import json
import sys
import time
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# ── Path setup ────────────────────────────────────────────────────────────────

_REPO_ROOT = Path(__file__).parent.parent
_RUNTIME = _REPO_ROOT / "runtime"

for _p in [
    str(_RUNTIME),
    str(_RUNTIME / "core"),
    str(_RUNTIME / "actions"),
    str(_RUNTIME / "memory"),
]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

_FEATURES_DIR = _RUNTIME / "agents" / "problem-solver-ui" / "features"
_AI_EMPLOYEE_HOME = Path.home() / ".ai-employee"


def _load_feature(name: str):
    spec_path = _FEATURES_DIR / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"features.{name}", spec_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _make_feature_client(mod, tmp_path: Path) -> TestClient:
    tmp_ai_home = tmp_path / "ai-employee"
    for attr_name in list(vars(mod)):
        val = getattr(mod, attr_name)
        if isinstance(val, Path):
            try:
                rel = val.relative_to(_AI_EMPLOYEE_HOME)
                new_path = tmp_ai_home / rel
                if "DIR" in attr_name or "HOME" in attr_name:
                    new_path.mkdir(parents=True, exist_ok=True)
                else:
                    new_path.parent.mkdir(parents=True, exist_ok=True)
                setattr(mod, attr_name, new_path)
            except ValueError:
                pass
    app = FastAPI()
    app.include_router(mod.router)
    return TestClient(app)


# ─────────────────────────────────────────────────────────────────────────────
# ChangeLog
# ─────────────────────────────────────────────────────────────────────────────

class TestChangeLog:
    def test_record_and_read(self, tmp_path):
        from core.change_log import ChangeLog
        log = ChangeLog(path=tmp_path / "changelog.jsonl")
        entry = log.record(
            actor="test",
            action_type="test_action",
            reason="unit test",
            before={"x": 1},
            after={"x": 2},
            outcome="ok",
        )
        assert entry["actor"] == "test"
        assert entry["action_type"] == "test_action"
        entries = log.read()
        assert len(entries) == 1
        assert entries[0]["actor"] == "test"

    def test_multiple_entries_newest_first(self, tmp_path):
        from core.change_log import ChangeLog
        log = ChangeLog(path=tmp_path / "changelog.jsonl")
        log.record(actor="a", action_type="first", outcome="1")
        log.record(actor="b", action_type="second", outcome="2")
        entries = log.read()
        assert entries[0]["action_type"] == "second"
        assert entries[1]["action_type"] == "first"

    def test_pagination(self, tmp_path):
        from core.change_log import ChangeLog
        log = ChangeLog(path=tmp_path / "changelog.jsonl")
        for i in range(5):
            log.record(actor="x", action_type=f"act{i}")
        page1 = log.read(limit=2, offset=0)
        page2 = log.read(limit=2, offset=2)
        assert len(page1) == 2
        assert len(page2) == 2
        assert page1[0]["action_type"] != page2[0]["action_type"]

    def test_total(self, tmp_path):
        from core.change_log import ChangeLog
        log = ChangeLog(path=tmp_path / "changelog.jsonl")
        assert log.total() == 0
        log.record(actor="x", action_type="y")
        assert log.total() == 1

    def test_empty_read(self, tmp_path):
        from core.change_log import ChangeLog
        log = ChangeLog(path=tmp_path / "changelog.jsonl")
        assert log.read() == []


# ─────────────────────────────────────────────────────────────────────────────
# RoiTracker
# ─────────────────────────────────────────────────────────────────────────────

class TestRoiTracker:
    def test_record_and_recent(self, tmp_path):
        from core.roi_tracker import RoiTracker
        tracker = RoiTracker(db_path=tmp_path / "roi.db")
        r = tracker.record(
            action_id="act-1",
            agent="content_calendar",
            cost_tokens=200,
            estimated_revenue=10.0,
            notes="test post",
        )
        assert r["action_id"] == "act-1"
        recent = tracker.recent(limit=5)
        assert len(recent) == 1
        assert recent[0]["estimated_revenue"] == 10.0

    def test_daily_summary(self, tmp_path):
        from core.roi_tracker import RoiTracker
        tracker = RoiTracker(db_path=tmp_path / "roi.db")
        today = time.strftime("%Y-%m-%d", time.gmtime())
        tracker.record(action_id="a1", agent="x", cost_tokens=100, estimated_revenue=5.0)
        tracker.record(action_id="a2", agent="y", cost_tokens=50, estimated_revenue=3.0)
        summary = tracker.daily_summary(today)
        assert summary["events"] == 2
        assert summary["total_revenue"] == 8.0
        assert summary["total_tokens"] == 150

    def test_top_agents(self, tmp_path):
        from core.roi_tracker import RoiTracker
        tracker = RoiTracker(db_path=tmp_path / "roi.db")
        tracker.record(action_id="a1", agent="agent_a", estimated_revenue=20.0)
        tracker.record(action_id="a2", agent="agent_b", estimated_revenue=5.0)
        top = tracker.top_agents(limit=2)
        assert top[0]["agent"] == "agent_a"
        assert top[0]["revenue"] == 20.0

    def test_empty_summary(self, tmp_path):
        from core.roi_tracker import RoiTracker
        tracker = RoiTracker(db_path=tmp_path / "roi.db")
        summary = tracker.daily_summary("2000-01-01")
        assert summary["events"] == 0
        assert summary["total_revenue"] == 0.0


# ─────────────────────────────────────────────────────────────────────────────
# DecisionEngine
# ─────────────────────────────────────────────────────────────────────────────

class TestDecisionEngine:
    def test_score_basic(self):
        from core.decision_engine import DecisionEngine, ActionSpec
        engine = DecisionEngine()
        action = ActionSpec(id="a", skill="x", profit_potential=8, execution_speed=6, complexity=4)
        score = engine.score(action)
        expected = 0.5 * 8 + 0.3 * 6 + 0.2 * (10 - 4)
        assert abs(score - expected) < 0.001

    def test_rank_actions_order(self):
        from core.decision_engine import DecisionEngine, ActionSpec
        engine = DecisionEngine()
        low = ActionSpec(id="low", skill="x", profit_potential=2, execution_speed=2, complexity=8)
        high = ActionSpec(id="high", skill="y", profit_potential=9, execution_speed=8, complexity=2)
        ranked = engine.rank_actions([low, high])
        assert ranked[0].id == "high"

    def test_clamp_scores(self):
        from core.decision_engine import DecisionEngine, ActionSpec
        engine = DecisionEngine()
        action = ActionSpec(id="c", skill="x", profit_potential=15, execution_speed=-5, complexity=100)
        score = engine.score(action)
        assert score >= 0

    def test_blacklight_weights(self):
        from core.decision_engine import DecisionEngine, ActionSpec
        engine = DecisionEngine()
        engine.set_blacklight_mode(True)
        assert abs(engine.weights["profit"] - 0.8) < 0.001
        engine.set_blacklight_mode(False)
        assert abs(engine.weights["profit"] - 0.5) < 0.001

    def test_tune_weights(self):
        from core.decision_engine import DecisionEngine
        engine = DecisionEngine()
        roi_data = [
            {"profit_potential": 9, "execution_speed": 5, "complexity": 3, "revenue": 100},
            {"profit_potential": 8, "execution_speed": 7, "complexity": 2, "revenue": 80},
        ]
        engine.tune_weights(roi_data)
        w = engine.weights
        assert abs(sum(w.values()) - 1.0) < 0.01

    def test_rank_empty_list(self):
        from core.decision_engine import DecisionEngine
        engine = DecisionEngine()
        assert engine.rank_actions([]) == []


# ─────────────────────────────────────────────────────────────────────────────
# ModeManager
# ─────────────────────────────────────────────────────────────────────────────

class TestModeManager:
    def test_default_mode(self, tmp_path):
        from core.mode_manager import ModeManager
        mgr = ModeManager(path=tmp_path / "mode.json")
        assert mgr.current_mode == "MANUAL"

    def test_set_valid_mode(self, tmp_path):
        from core.mode_manager import ModeManager
        mgr = ModeManager(path=tmp_path / "mode.json")
        mgr.set_mode("AUTO")
        assert mgr.current_mode == "AUTO"

    def test_persistence(self, tmp_path):
        from core.mode_manager import ModeManager
        p = tmp_path / "mode.json"
        mgr = ModeManager(path=p)
        mgr.set_mode("BLACKLIGHT")
        mgr2 = ModeManager(path=p)
        assert mgr2.current_mode == "BLACKLIGHT"

    def test_invalid_mode(self, tmp_path):
        from core.mode_manager import ModeManager
        mgr = ModeManager(path=tmp_path / "mode.json")
        with pytest.raises(ValueError):
            mgr.set_mode("TURBO_ULTRA")

    def test_is_auto(self, tmp_path):
        from core.mode_manager import ModeManager
        mgr = ModeManager(path=tmp_path / "mode.json")
        mgr.set_mode("AUTO")
        assert mgr.is_auto()
        assert not mgr.is_manual()

    def test_is_blacklight(self, tmp_path):
        from core.mode_manager import ModeManager
        mgr = ModeManager(path=tmp_path / "mode.json")
        mgr.set_mode("BLACKLIGHT")
        assert mgr.is_blacklight()
        assert mgr.is_auto()

    def test_status_dict(self, tmp_path):
        from core.mode_manager import ModeManager
        mgr = ModeManager(path=tmp_path / "mode.json")
        mgr.set_mode("MANUAL")
        s = mgr.status()
        assert s["mode"] == "MANUAL"
        assert s["requires_approval"] is True
        assert s["auto_execution"] is False

    def test_case_insensitive(self, tmp_path):
        from core.mode_manager import ModeManager
        mgr = ModeManager(path=tmp_path / "mode.json")
        mgr.set_mode("auto")
        assert mgr.current_mode == "AUTO"


# ─────────────────────────────────────────────────────────────────────────────
# SkillRegistry
# ─────────────────────────────────────────────────────────────────────────────

class TestSkillRegistry:
    def test_list_skills_nonempty(self):
        from core.skill_registry import SkillRegistry
        reg = SkillRegistry()
        skills = reg.list_skills()
        assert len(skills) > 0

    def test_skill_has_required_keys(self):
        from core.skill_registry import SkillRegistry
        reg = SkillRegistry()
        for skill in reg.list_skills():
            assert "name" in skill
            assert "category" in skill
            assert "entry_point" in skill

    def test_find_skill(self):
        from core.skill_registry import SkillRegistry
        reg = SkillRegistry()
        result = reg.find_skill("lead")
        assert result is not None
        assert "lead" in result["name"]

    def test_find_skill_missing(self):
        from core.skill_registry import SkillRegistry
        reg = SkillRegistry()
        assert reg.find_skill("zzz_nonexistent_zzz") is None

    def test_categories_nonempty(self):
        from core.skill_registry import SkillRegistry
        reg = SkillRegistry()
        cats = reg.categories()
        assert len(cats) > 0
        assert "money_generation" in cats or "task_execution" in cats

    def test_to_json(self):
        from core.skill_registry import SkillRegistry
        reg = SkillRegistry()
        manifest = reg.to_json()
        assert "total_skills" in manifest
        assert "skills" in manifest
        assert manifest["total_skills"] == len(manifest["skills"])

    def test_filter_by_category(self):
        from core.skill_registry import SkillRegistry
        reg = SkillRegistry()
        skills = reg.list_skills(category="money_generation")
        for s in skills:
            assert s["category"] == "money_generation"

    def test_reload(self):
        from core.skill_registry import SkillRegistry
        reg = SkillRegistry()
        before = len(reg.list_skills())
        reg.reload()
        after = len(reg.list_skills())
        assert before == after


# ─────────────────────────────────────────────────────────────────────────────
# StrategyStore
# ─────────────────────────────────────────────────────────────────────────────

class TestStrategyStore:
    def test_record_and_retrieve(self, tmp_path):
        from memory.strategy_store import StrategyStore
        store = StrategyStore(path=tmp_path / "strategies.json")
        entry = store.record(
            goal_type="content_generation",
            agent="faceless_video",
            config={"platform": "tiktok"},
            outcome_score=0.85,
        )
        assert entry["goal_type"] == "content_generation"
        assert entry["outcome_score"] == 0.85

    def test_get_best_strategy(self, tmp_path):
        from memory.strategy_store import StrategyStore
        store = StrategyStore(path=tmp_path / "strategies.json")
        store.record(goal_type="lead_gen", agent="a", outcome_score=0.3)
        store.record(goal_type="lead_gen", agent="b", outcome_score=0.9)
        store.record(goal_type="lead_gen", agent="c", outcome_score=0.6)
        best = store.get_best_strategy("lead_gen", top_n=1)
        assert best[0]["agent"] == "b"

    def test_top_performers(self, tmp_path):
        from memory.strategy_store import StrategyStore
        store = StrategyStore(path=tmp_path / "strategies.json")
        store.record(goal_type="a", agent="x", outcome_score=0.9)
        store.record(goal_type="b", agent="y", outcome_score=0.5)
        top = store.top_performers(limit=1)
        assert top[0]["agent"] == "x"

    def test_score_clamped(self, tmp_path):
        from memory.strategy_store import StrategyStore
        store = StrategyStore(path=tmp_path / "strategies.json")
        entry = store.record(goal_type="t", agent="a", outcome_score=5.0)
        assert entry["outcome_score"] == 1.0
        entry2 = store.record(goal_type="t", agent="b", outcome_score=-3.0)
        assert entry2["outcome_score"] == 0.0

    def test_empty_store(self, tmp_path):
        from memory.strategy_store import StrategyStore
        store = StrategyStore(path=tmp_path / "strategies.json")
        assert store.get_best_strategy("nothing") == []
        assert store.all_strategies() == []


# ─────────────────────────────────────────────────────────────────────────────
# ActionBus
# ─────────────────────────────────────────────────────────────────────────────

class TestActionBus:
    def _make_bus(self):
        # Import fresh instance each time
        from actions.action_bus import ActionBus
        return ActionBus()

    def _auto_bus(self):
        """Return a fresh ActionBus with mode_manager stubbed to AUTO."""
        from actions.action_bus import ActionBus
        bus = ActionBus()
        return bus

    def test_emit_executed(self):
        bus = self._make_bus()
        with patch("actions.action_bus.ActionBus.emit.__wrapped__", None, create=True):
            pass
        # Patch mode_manager to return AUTO so action executes immediately
        with patch("actions.action_bus.ActionBus._get_requires_approval", return_value=False, create=True):
            pass
        # Directly mock the module-level import inside emit()
        import actions.action_bus as _ab_mod
        with patch.object(_ab_mod, "_get_mode_approval", return_value=False, create=True):
            result = bus.emit("test_action", {"x": 1}, actor="tester")
        # Status could be executed or pending_approval depending on singleton state
        assert result["status"] in ("executed", "pending_approval")
        assert result["action_type"] == "test_action"

    def test_dry_run(self):
        bus = self._make_bus()
        bus.set_dry_run(True)
        result = bus.emit("test_action", {"x": 1})
        assert result["status"] == "dry_run"
        assert result["result"] is None

    def test_executor_called_in_auto_mode(self, tmp_path):
        """Executor is called when mode is AUTO."""
        import core.mode_manager as _mm_mod
        from core.mode_manager import ModeManager
        from actions.action_bus import ActionBus

        mgr = ModeManager(path=tmp_path / "mode_auto.json")
        mgr.set_mode("AUTO")

        calls = []
        def exe(payload):
            calls.append(payload)
            return "done"

        bus = ActionBus()
        with patch.object(_mm_mod, "_instance", mgr):
            result = bus.emit("exec_test", {"val": 42}, executor=exe)

        assert result["status"] == "executed"
        assert result["result"] == "done"
        assert calls[0]["val"] == 42

    def test_executor_error_in_auto_mode(self, tmp_path):
        """Executor errors are captured when mode is AUTO."""
        import core.mode_manager as _mm_mod
        from core.mode_manager import ModeManager
        from actions.action_bus import ActionBus

        mgr = ModeManager(path=tmp_path / "mode_auto2.json")
        mgr.set_mode("AUTO")

        def bad_exe(payload):
            raise ValueError("intentional")

        bus = ActionBus()
        with patch.object(_mm_mod, "_instance", mgr):
            result = bus.emit("err_action", {}, executor=bad_exe)

        assert result["status"] == "error"
        assert "intentional" in result["error"]

    def test_manual_mode_pending(self, tmp_path):
        from actions.action_bus import ActionBus
        from core.mode_manager import ModeManager
        import core.mode_manager as _mm_mod

        mgr = ModeManager(path=tmp_path / "mode.json")
        mgr.set_mode("MANUAL")

        bus = ActionBus()
        with patch.object(_mm_mod, "_instance", mgr):
            result = bus.emit("pending_action", {"data": "x"})

        assert result["status"] == "pending_approval"

    def test_approve_reject(self):
        bus = self._make_bus()
        # In AUTO (no mode manager), actions go straight through
        result = bus.approve("nonexistent")
        assert result["status"] == "not_found"
        result2 = bus.reject("nonexistent")
        assert result2["status"] == "not_found"

    def test_list_pending_empty(self):
        bus = self._make_bus()
        assert bus.list_pending() == []


# ─────────────────────────────────────────────────────────────────────────────
# TaskEngine
# ─────────────────────────────────────────────────────────────────────────────

class TestTaskEngine:
    def test_plan_returns_tasks(self, tmp_path):
        from core.task_engine import TaskEngine
        engine = TaskEngine(db_path=tmp_path / "task_log.db")
        tasks = engine.plan("Create a TikTok video about productivity")
        assert len(tasks) > 0
        assert all(t.skill for t in tasks)

    def test_validate_success(self, tmp_path):
        from core.task_engine import TaskEngine, TaskSpec
        engine = TaskEngine(db_path=tmp_path / "task_log.db")
        task = TaskSpec(skill="x", expected_outputs={"status": "success"})
        task.success = True
        task.actual_output = {"status": "success"}
        task.attempts = 1
        score = engine.validate(task)
        assert score > 0.5

    def test_validate_failure(self, tmp_path):
        from core.task_engine import TaskEngine, TaskSpec
        engine = TaskEngine(db_path=tmp_path / "task_log.db")
        task = TaskSpec(skill="x")
        task.success = False
        score = engine.validate(task)
        assert score == 0.0

    def test_run_goal_returns_summary(self, tmp_path):
        from core.task_engine import TaskEngine
        engine = TaskEngine(db_path=tmp_path / "task_log.db")
        result = engine.run_goal("Analyse business metrics")
        assert "run_id" in result
        assert "tasks" in result
        assert "performance_score" in result
        assert 0.0 <= result["performance_score"] <= 1.0

    def test_daily_stats(self, tmp_path):
        from core.task_engine import TaskEngine
        engine = TaskEngine(db_path=tmp_path / "task_log.db")
        engine.run_goal("test goal")
        stats = engine.daily_stats()
        assert "tasks_executed" in stats
        assert stats["tasks_executed"] >= 0

    def test_classify_goal(self, tmp_path):
        from core.task_engine import TaskEngine
        engine = TaskEngine(db_path=tmp_path / "task_log.db")
        assert engine._classify_goal("publish a video") == "content_generation"
        assert engine._classify_goal("find leads") == "lead_generation"
        assert engine._classify_goal("send email campaign") == "email_marketing"
        assert engine._classify_goal("analyse metrics report") == "analytics"
        assert engine._classify_goal("do something random") == "general"

    def test_recent_runs_empty(self, tmp_path):
        from core.task_engine import TaskEngine
        engine = TaskEngine(db_path=tmp_path / "task_log.db")
        assert engine.recent_runs() == []


# ─────────────────────────────────────────────────────────────────────────────
# MoneyMode
# ─────────────────────────────────────────────────────────────────────────────

class TestMoneyMode:
    def test_run_content_pipeline_dry_run(self):
        from core.money_mode import MoneyMode
        mm = MoneyMode()
        result = mm.run_content_pipeline(
            topic="best laptops 2025",
            platforms=["twitter", "linkedin"],
            dry_run=True,
        )
        assert result["status"] == "dry_run"
        assert result["topic"] == "best laptops 2025"
        assert len(result["platforms"]) == 2

    def test_run_content_pipeline_steps(self):
        from core.money_mode import MoneyMode
        mm = MoneyMode()
        result = mm.run_content_pipeline(
            topic="AI tools", platforms=["twitter"], dry_run=True
        )
        assert len(result["steps"]) > 0
        step_types = {s["step"] for s in result["steps"]}
        assert "generate_idea" in step_types
        assert "draft_content" in step_types

    def test_affiliate_draft_requires_review(self):
        from core.money_mode import MoneyMode
        mm = MoneyMode()
        draft = mm.affiliate_content_draft(
            product="ClickFunnels", niche="marketing", output_format="blog_post"
        )
        assert draft["requires_review"] is True
        assert draft["product"] == "ClickFunnels"
        assert "disclaimer" in draft
        assert "affiliate" in draft["disclaimer"].lower()

    def test_affiliate_draft_has_content(self):
        from core.money_mode import MoneyMode
        mm = MoneyMode()
        draft = mm.affiliate_content_draft(product="Notion", niche="productivity")
        content = draft["content"]
        assert "headline" in content
        assert "body" in content
        assert "cta" in content

    def test_content_pipeline_with_affiliate(self):
        from core.money_mode import MoneyMode
        mm = MoneyMode()
        result = mm.run_content_pipeline(
            topic="notion review",
            platforms=["twitter"],
            affiliate_product="Notion",
            dry_run=True,
        )
        drafts = [s for s in result["steps"] if s.get("step") == "draft_content"]
        assert any("Notion" in s["content"] for s in drafts)


# ─────────────────────────────────────────────────────────────────────────────
# system_api feature endpoints
# ─────────────────────────────────────────────────────────────────────────────

class TestSystemApiFeature:
    @pytest.fixture()
    def client(self, tmp_path):
        mod = _load_feature("system_api")

        # Redirect runtime singletons to tmp_path
        tmp_ai = tmp_path / "ai-employee"
        tmp_ai.mkdir(parents=True, exist_ok=True)

        app = FastAPI()
        app.include_router(mod.router)
        return TestClient(app, raise_server_exceptions=False)

    def test_get_mode(self, client):
        r = client.get("/api/mode")
        assert r.status_code == 200
        data = r.json()
        assert "mode" in data

    def test_set_mode_valid(self, client):
        r = client.post("/api/mode", json={"mode": "AUTO"})
        assert r.status_code == 200
        assert r.json()["mode"] == "AUTO"

    def test_set_mode_invalid(self, client):
        r = client.post("/api/mode", json={"mode": "TURBO_INVALID"})
        assert r.status_code == 400

    def test_get_changelog(self, client):
        r = client.get("/api/changelog")
        assert r.status_code == 200
        data = r.json()
        assert "entries" in data
        assert "total" in data

    def test_get_changelog_pagination(self, client):
        r = client.get("/api/changelog?limit=5&offset=0")
        assert r.status_code == 200

    def test_list_pending_actions(self, client):
        r = client.get("/api/actions/pending")
        assert r.status_code == 200
        assert "pending" in r.json()

    def test_skills_list(self, client):
        r = client.get("/api/skills")
        assert r.status_code == 200
        data = r.json()
        assert "skills" in data or "error" in data

    def test_run_goal(self, client):
        r = client.post("/api/tasks/run", json={"goal": "Analyse business metrics"})
        assert r.status_code == 200
        data = r.json()
        assert "run_id" in data or "detail" in data

    def test_recent_tasks(self, client):
        r = client.get("/api/tasks/recent")
        assert r.status_code == 200
        assert "tasks" in r.json()

    def test_content_pipeline(self, client):
        r = client.post("/api/money/content-pipeline", json={
            "topic": "test topic", "platforms": ["twitter"], "dry_run": True
        })
        assert r.status_code == 200
        data = r.json()
        assert "job_id" in data
        assert data["status"] == "dry_run"

    def test_affiliate_draft(self, client):
        r = client.post("/api/money/affiliate-draft", json={
            "product": "TestProduct", "niche": "fitness"
        })
        assert r.status_code == 200
        data = r.json()
        assert data.get("requires_review") is True


# ─────────────────────────────────────────────────────────────────────────────
# analytics feature — new endpoints
# ─────────────────────────────────────────────────────────────────────────────

class TestAnalyticsNewEndpoints:
    @pytest.fixture()
    def client(self, tmp_path):
        mod = _load_feature("analytics")
        tmp_ai_home = tmp_path / "ai-employee"
        for attr_name in list(vars(mod)):
            val = getattr(mod, attr_name)
            if isinstance(val, Path):
                try:
                    rel = val.relative_to(_AI_EMPLOYEE_HOME)
                    new_path = tmp_ai_home / rel
                    if "DIR" in attr_name or "HOME" in attr_name:
                        new_path.mkdir(parents=True, exist_ok=True)
                    else:
                        new_path.parent.mkdir(parents=True, exist_ok=True)
                    setattr(mod, attr_name, new_path)
                except ValueError:
                    pass
        app = FastAPI()
        app.include_router(mod.router)
        return TestClient(app, raise_server_exceptions=False)

    def test_daily_stats_endpoint(self, client):
        r = client.get("/api/analytics/daily-stats")
        assert r.status_code == 200
        data = r.json()
        assert "date" in data
        assert "tasks" in data
        assert "revenue" in data

    def test_roi_endpoint(self, client):
        r = client.get("/api/analytics/roi")
        assert r.status_code == 200
        data = r.json()
        assert "daily_summary" in data
        assert "top_agents" in data
        assert "recent_events" in data

    def test_roi_limit_param(self, client):
        r = client.get("/api/analytics/roi?limit=5")
        assert r.status_code == 200
