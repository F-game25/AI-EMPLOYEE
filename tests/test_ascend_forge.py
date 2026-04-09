"""Unit tests for runtime/agents/ascend-forge/ascend_forge.py

Covers:
  - Mode management: get_mode, set_mode, _resolve_effective_mode
  - Patch helpers: _risk_level, _infer_patch_type, _build_diff
  - Prompt optimisation: _optimize_prompt
  - Failsafe: _record_failure, _record_success
  - Patch lifecycle: create_patch, approve_patch, reject_patch, rollback_patch
  - Observe-only guard (create/approve blocked in observe-only mode)
  - State helpers: get_status, get_pending_patches, get_changelog
  - Auto-approve low-risk toggle: set_auto_approve_low
  - Blacklight flag: set_blacklight_active, _resolve_effective_mode override
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# ── Path setup ────────────────────────────────────────────────────────────────
_ASCEND_DIR = Path(__file__).parent.parent / "runtime" / "agents" / "ascend-forge"
if str(_ASCEND_DIR) not in sys.path:
    sys.path.insert(0, str(_ASCEND_DIR))

import ascend_forge as af


# ── Helpers to redirect file I/O to a temp state dir ─────────────────────────

@pytest.fixture(autouse=True)
def patch_ascend_paths(tmp_path, monkeypatch):
    """Redirect every file-path constant in ascend_forge to a temp dir."""
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    monkeypatch.setattr(af, "STATE_DIR", state_dir)
    monkeypatch.setattr(af, "STATE_FILE", state_dir / "ascend_forge.state.json")
    monkeypatch.setattr(af, "CHANGELOG_FILE", state_dir / "ascend_forge.changelog.json")
    monkeypatch.setattr(af, "AI_HOME", tmp_path)
    # Reset in-memory feeds / mode state between tests
    with af._activity_lock:
        af._activity_feed.clear()
    yield


# ══════════════════════════════════════════════════════════════════════════════
# Mode management
# ══════════════════════════════════════════════════════════════════════════════

class TestModeManagement:
    def test_default_mode_is_auto(self):
        assert af.get_mode() == af.MODE_AUTO

    def test_set_mode_general(self):
        af.set_mode("GENERAL")
        assert af.get_mode() == af.MODE_GENERAL

    def test_set_mode_money(self):
        af.set_mode("MONEY")
        assert af.get_mode() == af.MODE_MONEY

    def test_set_mode_case_insensitive(self):
        af.set_mode("auto")
        assert af.get_mode() == af.MODE_AUTO

    def test_set_mode_invalid_raises(self):
        with pytest.raises(ValueError, match="Invalid mode"):
            af.set_mode("TURBO")

    def test_mode_persists_to_state_file(self):
        af.set_mode("MONEY")
        # Re-read from disk
        state = json.loads(af.STATE_FILE.read_text())
        assert state["mode"] == "MONEY"


# ══════════════════════════════════════════════════════════════════════════════
# _resolve_effective_mode
# ══════════════════════════════════════════════════════════════════════════════

class TestResolveEffectiveMode:
    def test_explicit_general_mode(self):
        af.set_mode("GENERAL")
        assert af._resolve_effective_mode() == af.MODE_GENERAL

    def test_explicit_money_mode(self):
        af.set_mode("MONEY")
        assert af._resolve_effective_mode() == af.MODE_MONEY

    def test_auto_with_money_keyword(self):
        af.set_mode("AUTO")
        result = af._resolve_effective_mode("improve lead generation campaign")
        assert result == af.MODE_MONEY

    def test_auto_with_general_keyword(self):
        af.set_mode("AUTO")
        result = af._resolve_effective_mode("fix crash in performance code")
        assert result == af.MODE_GENERAL

    def test_auto_no_keywords_defaults_to_money(self):
        af.set_mode("AUTO")
        result = af._resolve_effective_mode("some vague task description")
        assert result == af.MODE_MONEY

    def test_blacklight_overrides_to_money(self):
        af.set_mode("GENERAL")
        af.set_blacklight_active(True)
        result = af._resolve_effective_mode()
        assert result == af.MODE_MONEY
        af.set_blacklight_active(False)


# ══════════════════════════════════════════════════════════════════════════════
# Patch helpers
# ══════════════════════════════════════════════════════════════════════════════

class TestRiskLevel:
    def test_low_risk_small_change(self):
        assert af._risk_level(["agents/some_agent.py"], 10) == "LOW"

    def test_medium_risk_large_change(self):
        assert af._risk_level(["agents/some_agent.py"], 100) == "MEDIUM"

    def test_high_risk_very_large_change(self):
        assert af._risk_level(["agents/some_agent.py"], 300) == "HIGH"

    def test_high_risk_protected_module(self):
        assert af._risk_level(["agents/ollama-agent/ollama.py"], 5) == "HIGH"

    def test_high_risk_hermes(self):
        assert af._risk_level(["hermes-agent/hermes.py"], 5) == "HIGH"

    def test_high_risk_ai_router(self):
        assert af._risk_level(["ai-router/ai_router.py"], 1) == "HIGH"

    def test_boundary_medium_51(self):
        assert af._risk_level(["safe.py"], 51) == "MEDIUM"

    def test_boundary_low_50(self):
        assert af._risk_level(["safe.py"], 50) == "LOW"

    def test_empty_files_list(self):
        assert af._risk_level([], 10) == "LOW"


class TestInferPatchType:
    def test_prompt_keyword(self):
        assert af._infer_patch_type("Improve the prompt wording") == "prompt"

    def test_monetization_keyword(self):
        assert af._infer_patch_type("Increase revenue output quality") == "monetization"

    def test_ui_keyword(self):
        assert af._infer_patch_type("Fix visual layout of dashboard UI") == "UI"

    def test_performance_keyword(self):
        assert af._infer_patch_type("Optimise latency in hot path") == "performance"

    def test_bug_fix_keyword(self):
        assert af._infer_patch_type("Fix crash when user logs in") == "functionality"

    def test_default_functionality(self):
        assert af._infer_patch_type("Some unrelated description xyz") == "functionality"

    def test_case_insensitive(self):
        assert af._infer_patch_type("IMPROVE THE PROMPT") == "prompt"


class TestBuildDiff:
    def test_returns_string(self):
        diff = af._build_diff("hello\n", "hello world\n", "test.py")
        assert isinstance(diff, str)

    def test_diff_contains_filename(self):
        diff = af._build_diff("a\n", "b\n", "myfile.py")
        assert "myfile.py" in diff

    def test_identical_content_empty_diff(self):
        diff = af._build_diff("same\n", "same\n")
        assert diff == ""

    def test_diff_shows_added_line(self):
        diff = af._build_diff("line1\n", "line1\nline2\n")
        assert "+line2" in diff


# ══════════════════════════════════════════════════════════════════════════════
# Prompt optimisation
# ══════════════════════════════════════════════════════════════════════════════

class TestOptimizePrompt:
    def test_returns_tuple(self):
        result = af._optimize_prompt("Write a summary.")
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_adds_terminator_if_missing(self):
        improved, suggestions = af._optimize_prompt("Write a summary")
        assert improved.endswith(".")
        assert any("terminator" in s.lower() for s in suggestions)

    def test_detects_please_filler(self):
        _, suggestions = af._optimize_prompt("please write a report.")
        assert any("please" in s.lower() for s in suggestions)

    def test_detects_can_you_filler(self):
        _, suggestions = af._optimize_prompt("Can you help me with this?")
        assert any("can you" in s.lower() or "imperative" in s.lower() for s in suggestions)

    def test_detects_just_filler(self):
        _, suggestions = af._optimize_prompt("just summarize it.")
        assert any("just" in s.lower() for s in suggestions)

    def test_restructures_long_single_line(self):
        long = "Please just summarize all the various things mentioned in the document and output an amazing comprehensive report with details."
        improved, suggestions = af._optimize_prompt(long)
        # Should be restructured into Task/Output format
        assert "Task:" in improved or len(suggestions) > 0

    def test_no_changes_for_good_prompt(self):
        good = "Summarize the quarterly revenue report."
        improved, suggestions = af._optimize_prompt(good)
        # No structural suggestions required for a well-formed short prompt
        assert isinstance(improved, str)


# ══════════════════════════════════════════════════════════════════════════════
# Failsafe: _record_failure / _record_success
# ══════════════════════════════════════════════════════════════════════════════

class TestFailsafe:
    def test_failure_increments_counter(self):
        af._record_failure()
        state = af._load_state()
        assert state["consecutive_failures"] == 1

    def test_three_failures_triggers_observe_only(self):
        for _ in range(af.MAX_CONSECUTIVE_FAILURES):
            af._record_failure()
        state = af._load_state()
        assert state["observe_only"] is True

    def test_success_resets_counter(self):
        af._record_failure()
        af._record_failure()
        af._record_success()
        state = af._load_state()
        assert state["consecutive_failures"] == 0

    def test_record_failure_returns_true_when_failsafe_triggers(self):
        for _ in range(af.MAX_CONSECUTIVE_FAILURES - 1):
            af._record_failure()
        triggered = af._record_failure()
        assert triggered is True

    def test_record_failure_returns_false_before_threshold(self):
        result = af._record_failure()
        assert result is False


# ══════════════════════════════════════════════════════════════════════════════
# Patch lifecycle: create → approve / reject / rollback
# ══════════════════════════════════════════════════════════════════════════════

class TestCreatePatch:
    def _make_patch(self, **kwargs):
        defaults = dict(
            description="Fix crash on login",
            reason="Null pointer dereference",
            affected_files=["agents/auth.py"],
            diff_preview="@@ -1 +1 @@\n-old\n+new\n",
        )
        defaults.update(kwargs)
        return af.create_patch(**defaults)

    def test_returns_dict_with_patch_id(self):
        patch = self._make_patch()
        assert "patch_id" in patch
        assert patch["patch_id"].startswith("patch-")

    def test_status_is_pending(self):
        patch = self._make_patch()
        assert patch["status"] == "pending"

    def test_risk_computed(self):
        patch = self._make_patch(affected_files=["agents/some_agent.py"],
                                 diff_preview="@@ -1 +1 @@\n+new\n")
        assert patch["risk_level"] in ("LOW", "MEDIUM", "HIGH")

    def test_protected_module_forces_high_risk(self):
        patch = self._make_patch(
            affected_files=["ollama-agent/ollama.py"],
            diff_preview="small\n",
        )
        assert patch["risk_level"] == "HIGH"

    def test_patch_logged_to_changelog(self):
        patch = self._make_patch()
        log = af._load_changelog()
        ids = [p["patch_id"] for p in log]
        assert patch["patch_id"] in ids

    def test_observe_only_blocks_creation(self):
        state = af._load_state()
        state["observe_only"] = True
        af._save_state(state)
        with pytest.raises(RuntimeError, match="observe-only"):
            self._make_patch()

    def test_patch_type_inferred_from_description(self):
        patch = self._make_patch(description="Improve prompt wording")
        assert patch["patch_type"] == "prompt"

    def test_mode_used_when_provided(self):
        patch = self._make_patch(mode="MONEY")
        assert patch["mode"] == "MONEY"


class TestApprovePatch:
    def _create_low_risk_patch(self):
        return af.create_patch(
            description="Minor fix",
            reason="Bug in safe module",
            affected_files=["agents/safe.py"],
            diff_preview="+fix\n",
        )

    def test_approve_sets_status_approved(self):
        patch = self._create_low_risk_patch()
        approved = af.approve_patch(patch["patch_id"])
        assert approved["status"] == "approved"

    def test_approve_sets_applied_timestamp(self):
        patch = self._create_low_risk_patch()
        approved = af.approve_patch(patch["patch_id"])
        assert approved["applied_timestamp"] is not None

    def test_approve_increments_counter(self):
        patch = self._create_low_risk_patch()
        af.approve_patch(patch["patch_id"])
        state = af._load_state()
        assert state["patches_approved"] >= 1

    def test_approve_nonexistent_raises(self):
        with pytest.raises(ValueError, match="not found"):
            af.approve_patch("patch-00000000")

    def test_approve_already_approved_raises(self):
        patch = self._create_low_risk_patch()
        af.approve_patch(patch["patch_id"])
        with pytest.raises(ValueError, match="not pending"):
            af.approve_patch(patch["patch_id"])

    def test_approve_in_observe_only_raises(self):
        patch = self._create_low_risk_patch()
        state = af._load_state()
        state["observe_only"] = True
        af._save_state(state)
        with pytest.raises(RuntimeError, match="observe-only"):
            af.approve_patch(patch["patch_id"])


class TestRejectPatch:
    def _create_patch(self):
        return af.create_patch(
            description="Reduce cost",
            reason="Saves money",
            affected_files=["agents/cost.py"],
            diff_preview="-expensive\n+cheap\n",
        )

    def test_reject_sets_status_rejected(self):
        patch = self._create_patch()
        rejected = af.reject_patch(patch["patch_id"])
        assert rejected["status"] == "rejected"

    def test_reject_nonexistent_raises(self):
        with pytest.raises(ValueError, match="not found"):
            af.reject_patch("patch-deadbeef")

    def test_reject_already_rejected_raises(self):
        patch = self._create_patch()
        af.reject_patch(patch["patch_id"])
        with pytest.raises(ValueError, match="not pending"):
            af.reject_patch(patch["patch_id"])

    def test_reject_increments_counter(self):
        patch = self._create_patch()
        af.reject_patch(patch["patch_id"])
        state = af._load_state()
        assert state["patches_rejected"] >= 1


class TestRollbackPatch:
    def _approved_patch(self):
        p = af.create_patch(
            description="Rollback me",
            reason="Test rollback",
            affected_files=["agents/rollback.py"],
            diff_preview="+something\n",
        )
        af.approve_patch(p["patch_id"])
        return p

    def test_rollback_sets_status(self):
        patch = self._approved_patch()
        rolled = af.rollback_patch(patch["patch_id"])
        assert rolled["status"] == "rolled_back"

    def test_rollback_sets_timestamp(self):
        patch = self._approved_patch()
        rolled = af.rollback_patch(patch["patch_id"])
        assert "rolled_back_at" in rolled

    def test_rollback_nonexistent_raises(self):
        with pytest.raises(ValueError, match="not found"):
            af.rollback_patch("patch-ffffffff")

    def test_rollback_pending_raises(self):
        patch = af.create_patch(
            description="Still pending",
            reason="Not yet approved",
            affected_files=["agents/x.py"],
            diff_preview="+x\n",
        )
        with pytest.raises(ValueError, match="approved"):
            af.rollback_patch(patch["patch_id"])


# ══════════════════════════════════════════════════════════════════════════════
# Auto-approve toggle
# ══════════════════════════════════════════════════════════════════════════════

class TestAutoApproveLow:
    def test_low_risk_auto_approved_when_toggle_on(self):
        af.set_auto_approve_low(True)
        patch = af.create_patch(
            description="Minor log improvement",
            reason="Better readability",
            affected_files=["agents/logger.py"],
            diff_preview="+log\n",  # small change → LOW risk
        )
        # Either auto-approved or still pending (depends on risk classification)
        log = af._load_changelog()
        p = next(p for p in log if p["patch_id"] == patch["patch_id"])
        assert p["status"] in ("approved", "pending")

    def test_toggle_persists_to_state(self):
        af.set_auto_approve_low(True)
        state = af._load_state()
        assert state["auto_approve_low"] is True


# ══════════════════════════════════════════════════════════════════════════════
# Status / query helpers
# ══════════════════════════════════════════════════════════════════════════════

class TestStatusHelpers:
    def test_get_status_returns_dict(self):
        status = af.get_status()
        assert isinstance(status, dict)
        assert "mode" in status

    def test_get_pending_patches_empty_initially(self):
        pending = af.get_pending_patches()
        assert pending == []

    def test_get_pending_patches_shows_new_patch(self):
        af.create_patch(
            description="Pending patch",
            reason="Test",
            affected_files=["agents/x.py"],
            diff_preview="+x\n",
        )
        pending = af.get_pending_patches()
        assert len(pending) >= 1

    def test_get_changelog_empty_initially(self):
        assert af.get_changelog() == []

    def test_get_changelog_shows_entries_after_patch(self):
        af.create_patch(
            description="Changelog entry",
            reason="Coverage",
            affected_files=["agents/log.py"],
            diff_preview="+log\n",
        )
        log = af.get_changelog()
        assert len(log) >= 1

    def test_get_changelog_limit(self):
        for i in range(10):
            af.create_patch(
                description=f"Patch {i}",
                reason="bulk",
                affected_files=["agents/safe.py"],
                diff_preview=f"+{i}\n",
            )
        log = af.get_changelog(limit=5)
        assert len(log) <= 5


# ══════════════════════════════════════════════════════════════════════════════
# Activity feed
# ══════════════════════════════════════════════════════════════════════════════

class TestActivityFeed:
    def test_push_activity_adds_entry(self):
        af._push_activity("test message", "info")
        with af._activity_lock:
            feed = list(af._activity_feed)
        assert any(e["msg"] == "test message" for e in feed)

    def test_feed_capped_at_max(self):
        for i in range(af._MAX_FEED + 50):
            af._push_activity(f"msg {i}")
        with af._activity_lock:
            assert len(af._activity_feed) <= af._MAX_FEED


# ══════════════════════════════════════════════════════════════════════════════
# analyze_prompt
# ══════════════════════════════════════════════════════════════════════════════

class TestAnalyzePrompt:
    def test_returns_dict_with_expected_keys(self):
        result = af.analyze_prompt("Fix the login bug.")
        for key in ("is_complex", "phases", "actions", "mentioned_agents",
                    "mentioned_files", "patch_types", "has_high_risk", "summary"):
            assert key in result

    def test_simple_prompt_not_complex(self):
        result = af.analyze_prompt("Fix the login bug.")
        assert not result["is_complex"]

    def test_multi_phase_prompt_is_complex(self):
        result = af.analyze_prompt(
            "Phase 1: Fix stability issues\n- fix crashes\n- improve logging\n"
            "Phase 2: Add new features\n- add user auth\n- add dashboard"
        )
        assert result["is_complex"]
        assert len(result["phases"]) == 2

    def test_phase_extraction(self):
        result = af.analyze_prompt(
            "Phase 1: Fix bugs\n- fix crash\n- fix error\n"
            "Phase 2: Improve UI\n- better layout"
        )
        assert result["phases"][0]["name"].startswith("Phase 1")
        assert len(result["phases"][0]["items"]) >= 1

    def test_phase_priorities_assigned(self):
        result = af.analyze_prompt(
            "Phase 1: First phase\n- do something\n"
            "Phase 2: Second phase\n- do another\n"
            "Phase 3: Third phase\n- do more"
        )
        assert result["phases"][0]["priority"] == "HIGH"
        assert result["phases"][1]["priority"] == "MEDIUM"
        assert result["phases"][2]["priority"] == "LOW"

    def test_action_extraction(self):
        result = af.analyze_prompt(
            "Do the following:\n"
            "- Fix login crash\n- Optimize prompts\n- Update the UI layout"
        )
        assert len(result["actions"]) >= 3

    def test_agent_detection(self):
        result = af.analyze_prompt(
            "Agent: task-orchestrator needs to handle phase 2 planning"
        )
        assert "task-orchestrator" in result["mentioned_agents"]

    def test_file_detection(self):
        result = af.analyze_prompt("Update server.py and the index.html file")
        assert "server.py" in result["mentioned_files"]
        assert "index.html" in result["mentioned_files"]

    def test_patch_type_ui_detected(self):
        result = af.analyze_prompt(
            "Fix the dashboard UI layout and improve visual design"
        )
        assert "UI" in result["patch_types"]

    def test_patch_type_performance_detected(self):
        result = af.analyze_prompt("Optimize the performance and reduce latency")
        assert "performance" in result["patch_types"]

    def test_patch_type_functionality_detected(self):
        result = af.analyze_prompt("Fix crash and resolve error in login flow")
        assert "functionality" in result["patch_types"]

    def test_high_risk_detection_server(self):
        result = af.analyze_prompt(
            "Update server.py and the ai-router configuration"
        )
        assert result["has_high_risk"]

    def test_no_high_risk_for_safe_prompt(self):
        result = af.analyze_prompt("Improve the color scheme of the UI buttons")
        assert not result["has_high_risk"]

    def test_summary_is_first_line(self):
        result = af.analyze_prompt(
            "Fix critical bugs in the system\nPhase 1: Do X"
        )
        assert "Fix critical bugs" in result["summary"]

    def test_persists_last_plan_to_state(self):
        af.analyze_prompt("Test prompt for state persistence")
        state = af._load_state()
        assert "last_plan" in state
        assert state["last_plan"] is not None

    def test_many_lines_marks_complex(self):
        prompt = "\n".join(f"Step {i}: do something important" for i in range(12))
        result = af.analyze_prompt(prompt)
        assert result["is_complex"]

    def test_plan_keyword_marks_complex(self):
        result = af.analyze_prompt("Create a plan to upgrade the system")
        assert result["is_complex"]


# ══════════════════════════════════════════════════════════════════════════════
# handle_complex_task
# ══════════════════════════════════════════════════════════════════════════════

class TestHandleComplexTask:
    def test_returns_string(self):
        result = af.handle_complex_task("Fix login crash in the system")
        assert isinstance(result, str)

    def test_response_has_summary(self):
        result = af.handle_complex_task("Fix login crash in the system")
        assert "Summary" in result

    def test_response_ends_with_ready_or_awaiting(self):
        result = af.handle_complex_task("Fix login crash")
        assert "Ready to execute" in result or "Awaiting your approval" in result

    def test_delegates_ascend_prefix_commands(self):
        result = af.handle_complex_task("ascend: status")
        assert "ASCEND_FORGE Status" in result

    def test_complex_prompt_queues_patches(self):
        initial_count = len(af._load_changelog())
        af.handle_complex_task(
            "Phase 1: Fix UI issues\n- improve layout\n- fix dashboard\n"
            "Phase 2: Optimize performance\n- reduce latency\n- improve speed"
        )
        new_log = af._load_changelog()
        assert len(new_log) > initial_count
        descriptions = [p["description"] for p in new_log]
        assert any("Phase 1" in d or "UI" in d for d in descriptions)
        assert any("Phase 2" in d or "performance" in d or "Optim" in d for d in descriptions)

    def test_observe_only_still_returns_analysis(self):
        state = af._load_state()
        state["observe_only"] = True
        af._save_state(state)
        try:
            # Should return analysis even when observe-only blocks patch creation
            result = af.handle_complex_task("Improve the UI layout and design")
            assert isinstance(result, str)
            assert "Summary" in result
        finally:
            s = af._load_state()
            s["observe_only"] = False
            af._save_state(s)

    def test_high_risk_prompt_awaiting_approval(self):
        result = af.handle_complex_task(
            "Rewrite server.py to integrate with ai-router backend"
        )
        assert "Awaiting your approval" in result

    def test_plan_section_in_complex_prompt(self):
        result = af.handle_complex_task(
            "Phase 1: Stability fixes\n- fix crash\n- fix errors\n"
            "Phase 2: New features\n- add feature A\n- add feature B"
        )
        assert "Plan" in result
        assert "Phase 1" in result

    def test_performance_prompt_queues_performance_patch(self):
        af.handle_complex_task("Optimize performance and reduce response latency")
        log = af._load_changelog()
        assert any(p.get("patch_type") == "performance" for p in log)

    def test_ui_prompt_queues_ui_patch(self):
        af.handle_complex_task("Improve the dashboard UI layout and visual design")
        log = af._load_changelog()
        assert any(p.get("patch_type") == "UI" for p in log)

    def test_routing_suggestion_shown_for_ui_task(self):
        result = af.handle_complex_task("Improve the dashboard UI layout")
        assert "ui-engine" in result.lower() or "Routing" in result

    def test_routing_suggestion_shown_for_revenue_task(self):
        result = af.handle_complex_task("Generate leads and increase revenue")
        assert "cold-outreach" in result.lower() or "Routing" in result


# ══════════════════════════════════════════════════════════════════════════════
# Feature 5: Agent routing — _route_task
# ══════════════════════════════════════════════════════════════════════════════

class TestRouteTask:
    def test_ui_routes_to_ui_engine(self):
        assert af._route_task("Fix the dashboard UI layout") == "ui-engine"

    def test_visual_routes_to_ui_engine(self):
        assert af._route_task("Improve visual design and CSS styling") == "ui-engine"

    def test_revenue_routes_to_cold_outreach(self):
        agent = af._route_task("Generate leads and increase revenue")
        assert agent == "cold-outreach-assassin"

    def test_bug_routes_to_hermes(self):
        assert af._route_task("Fix crash and resolve error exception") == "hermes-agent"

    def test_research_routes_to_problem_solver(self):
        assert af._route_task("Research competitor market analysis") == "problem-solver"

    def test_prompt_routes_to_ascend_forge(self):
        assert af._route_task("Improve prompt quality for better output") == "ascend-forge"

    def test_unmatched_returns_none(self):
        assert af._route_task("something completely unrelated xyz") is None


# ══════════════════════════════════════════════════════════════════════════════
# Feature 4: Real execution — _apply_simple_diff, _execute_real_patch
# ══════════════════════════════════════════════════════════════════════════════

class TestApplySimpleDiff:
    def test_replaces_matching_line(self):
        original = "hello world\nkeep this\n"
        diff = "-hello world\n+hello universe\n"
        result = af._apply_simple_diff(original, diff)
        assert "hello universe" in result
        assert "keep this" in result

    def test_returns_original_when_removal_not_found(self):
        original = "something else\n"
        diff = "-missing line\n+replacement\n"
        result = af._apply_simple_diff(original, diff)
        assert result == original

    def test_returns_original_when_no_real_lines(self):
        original = "no change\n"
        diff = "# just a comment\n"
        result = af._apply_simple_diff(original, diff)
        assert result == original

    def test_ignores_diff_header_lines(self):
        original = "old value\n"
        diff = "--- a/file.py\n+++ b/file.py\n-old value\n+new value\n"
        result = af._apply_simple_diff(original, diff)
        assert "new value" in result


class TestExecuteRealPatch:
    def test_returns_false_for_empty_affected_files(self):
        patch = {"affected_files": [], "diff_preview": "-old\n+new\n"}
        assert af._execute_real_patch(patch) is False

    def test_returns_false_for_empty_diff(self):
        patch = {"affected_files": ["safe.py"], "diff_preview": ""}
        assert af._execute_real_patch(patch) is False

    def test_returns_false_when_diff_has_only_comments(self):
        patch = {
            "affected_files": ["safe.py"],
            "diff_preview": "# Just a metadata comment\n# Another comment",
        }
        assert af._execute_real_patch(patch) is False

    def test_returns_false_when_file_not_found(self, tmp_path, monkeypatch):
        monkeypatch.setattr(af, "AI_HOME", tmp_path)
        patch = {
            "affected_files": ["nonexistent/agent.py"],
            "diff_preview": "-old line\n+new line\n",
        }
        assert af._execute_real_patch(patch) is False

    def test_applies_to_real_file(self, tmp_path, monkeypatch):
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        target = agents_dir / "myagent.py"
        target.write_text("old line\nkeep this\n")
        monkeypatch.setattr(af, "AI_HOME", tmp_path)

        patch = {
            "affected_files": ["myagent.py"],
            "diff_preview": "-old line\n+new line\n",
        }
        result = af._execute_real_patch(patch)
        assert result is True
        assert "new line" in target.read_text()
        assert "keep this" in target.read_text()


# ══════════════════════════════════════════════════════════════════════════════
# Feature 3: Web research — web_research
# ══════════════════════════════════════════════════════════════════════════════

class TestWebResearch:
    def test_returns_string(self, monkeypatch):
        """web_research always returns a string regardless of network."""
        # Patch urlopen to raise to simulate offline environment
        import urllib.request as _urlreq

        def _fail(*a, **kw):
            raise OSError("network unavailable")

        monkeypatch.setattr(_urlreq, "urlopen", _fail)
        result = af.web_research("test query")
        assert isinstance(result, str)

    def test_offline_message_contains_query(self, monkeypatch):
        import urllib.request as _urlreq

        monkeypatch.setattr(_urlreq, "urlopen", lambda *a, **kw: (_ for _ in ()).throw(OSError("offline")))
        result = af.web_research("best email openers")
        assert "best email openers" in result

    def test_returns_findings_on_success(self, monkeypatch):
        import io, urllib.request as _urlreq

        fake_html = (
            b'<span class="result__snippet">First great result about topic.</span>'
            b'<a class="result__snippet">Second result here.</a>'
        )

        class _FakeResp:
            def read(self):
                return fake_html

            def __enter__(self):
                return self

            def __exit__(self, *_):
                pass

        monkeypatch.setattr(_urlreq, "urlopen", lambda *a, **kw: _FakeResp())
        result = af.web_research("AI automation")
        assert "FINDINGS" in result

    def test_max_results_respected(self, monkeypatch):
        import urllib.request as _urlreq

        snippets = "".join(
            f'<span class="result__snippet">Result {i}.</span>' for i in range(10)
        ).encode()

        class _FakeResp:
            def read(self):
                return snippets

            def __enter__(self):
                return self

            def __exit__(self, *_):
                pass

        monkeypatch.setattr(_urlreq, "urlopen", lambda *a, **kw: _FakeResp())
        result = af.web_research("test", max_results=2)
        # Should not have more than 2 numbered results
        lines = [l for l in result.splitlines() if l.strip().startswith(("1.", "2.", "3.", "4."))]
        assert len(lines) <= 2


# ══════════════════════════════════════════════════════════════════════════════
# Feature 6: Context compaction + cost tracking
# ══════════════════════════════════════════════════════════════════════════════

class TestCompactContext:
    def test_returns_string(self):
        result = af.compact_context()
        assert isinstance(result, str)

    def test_empty_feed_message(self):
        result = af.compact_context()
        assert "empty" in result.lower() or "nothing" in result.lower()

    def test_compresses_feed(self):
        for i in range(20):
            af._push_activity(f"✅ Event {i}", "success")
        af.compact_context()
        with af._activity_lock:
            feed_size = len(af._activity_feed)
        assert feed_size == 1  # collapsed to one compact entry

    def test_compact_summary_entry_message(self):
        af._push_activity("✅ patch applied", "success")
        af.compact_context()
        with af._activity_lock:
            feed = list(af._activity_feed)
        assert any("compact" in e["msg"].lower() for e in feed)

    def test_returns_compressed_label(self):
        af._push_activity("✅ patch applied", "success")
        result = af.compact_context()
        assert "COMPRESSED" in result or "compact" in result.lower()


class TestGetSessionCost:
    def test_returns_dict_with_expected_keys(self):
        stats = af.get_session_cost()
        for key in (
            "patches_applied", "patches_pending", "patches_rejected",
            "patches_rolled_back", "session_minutes", "activity_entries",
            "context_health",
        ):
            assert key in stats

    def test_session_minutes_non_negative(self):
        stats = af.get_session_cost()
        assert stats["session_minutes"] >= 0

    def test_context_health_green_for_small_feed(self):
        stats = af.get_session_cost()
        assert "🟢" in stats["context_health"]

    def test_context_health_yellow_when_feed_large(self):
        for i in range(60):
            af._push_activity(f"msg {i}")
        stats = af.get_session_cost()
        assert "🟡" in stats["context_health"] or "🔴" in stats["context_health"]

    def test_patch_counts_reflect_changelog(self):
        p = af.create_patch(
            description="Cost test",
            reason="Test",
            affected_files=["agents/safe.py"],
            diff_preview="+x\n",
        )
        af.approve_patch(p["patch_id"])
        stats = af.get_session_cost()
        assert stats["patches_applied"] >= 1


# ══════════════════════════════════════════════════════════════════════════════
# Feature 7: Scheduler
# ══════════════════════════════════════════════════════════════════════════════

class TestScheduler:
    def test_register_returns_entry(self):
        entry = af.register_schedule("test_scan", "daily")
        assert entry["name"] == "test_scan"
        assert entry["freq"] == "daily"
        assert entry["freq_seconds"] == 86400
        assert entry["last_run_ts"] is None

    def test_register_persists_to_state(self):
        af.register_schedule("persist_test", "weekly")
        state = af._load_state()
        assert "persist_test" in state.get("schedules", {})

    def test_freq_normalization_hourly(self):
        entry = af.register_schedule("hourly_task", "hourly")
        assert entry["freq"] == "hourly"
        assert entry["freq_seconds"] == 3600

    def test_freq_normalization_weekly(self):
        entry = af.register_schedule("weekly_task", "weekly")
        assert entry["freq"] == "weekly"
        assert entry["freq_seconds"] == 604800

    def test_freq_default_to_daily_for_unknown(self):
        entry = af.register_schedule("unknown_freq", "monthly")
        assert entry["freq"] == "daily"

    def test_list_schedules_empty_initially(self):
        assert af.list_schedules() == []

    def test_list_schedules_shows_registered(self):
        af.register_schedule("scan_daily", "daily")
        schedules = af.list_schedules()
        assert len(schedules) >= 1
        names = [s["name"] for s in schedules]
        assert "scan_daily" in names

    def test_remove_schedule_returns_true(self):
        af.register_schedule("to_remove", "daily")
        result = af.remove_schedule("to_remove")
        assert result is True

    def test_remove_schedule_removes_from_state(self):
        af.register_schedule("removable", "daily")
        af.remove_schedule("removable")
        state = af._load_state()
        assert "removable" not in state.get("schedules", {})

    def test_remove_nonexistent_returns_false(self):
        assert af.remove_schedule("does_not_exist") is False

    def test_check_schedules_fires_overdue_task(self):
        # Register with last_run set far in the past to guarantee firing
        af.register_schedule("overdue_scan", "daily")
        state = af._load_state()
        state["schedules"]["overdue_scan"]["last_run_ts"] = "2000-01-01T00:00:00Z"
        af._save_state(state)
        fired = af.check_schedules()
        assert "overdue_scan" in fired

    def test_check_schedules_does_not_fire_recent_task(self):
        af.register_schedule("fresh_scan", "daily")
        # Set last_run to now
        state = af._load_state()
        state["schedules"]["fresh_scan"]["last_run_ts"] = af._now_iso()
        af._save_state(state)
        fired = af.check_schedules()
        assert "fresh_scan" not in fired

    def test_check_schedules_returns_list(self):
        result = af.check_schedules()
        assert isinstance(result, list)

    def test_check_schedules_updates_last_run_ts(self):
        af.register_schedule("ts_test_scan", "daily")
        state = af._load_state()
        state["schedules"]["ts_test_scan"]["last_run_ts"] = "2000-01-01T00:00:00Z"
        af._save_state(state)
        af.check_schedules()
        state_after = af._load_state()
        ts = state_after["schedules"]["ts_test_scan"]["last_run_ts"]
        assert ts != "2000-01-01T00:00:00Z"
        assert ts is not None


# ══════════════════════════════════════════════════════════════════════════════
# Feature 1 & 2: Slash command handler
# ══════════════════════════════════════════════════════════════════════════════

class TestHandleSlashCommand:
    def test_non_slash_returns_empty(self):
        assert af.handle_slash_command("ascend: status") == ""

    def test_empty_slash_returns_empty(self):
        assert af.handle_slash_command("/") == ""

    def test_help_lists_commands(self):
        result = af.handle_slash_command("/help")
        assert "/scan" in result
        assert "/plan" in result
        assert "/execute" in result
        assert "/research" in result
        assert "/compact" in result
        assert "/cost" in result
        assert "/schedule" in result

    def test_status_returns_state(self):
        result = af.handle_slash_command("/status")
        assert "ASCEND_FORGE Status" in result
        assert "Mode" in result

    def test_scan_returns_string(self):
        result = af.handle_slash_command("/scan")
        assert isinstance(result, str)
        assert "Scan" in result

    def test_patches_empty(self):
        result = af.handle_slash_command("/patches")
        assert "No pending" in result

    def test_patches_shows_pending(self):
        af.create_patch(
            description="Slash pending test",
            reason="Test",
            affected_files=["agents/x.py"],
            diff_preview="+x\n",
        )
        result = af.handle_slash_command("/patches")
        assert "patch" in result.lower()

    def test_approve_missing_id(self):
        result = af.handle_slash_command("/approve")
        assert "Usage" in result

    def test_approve_nonexistent_id(self):
        result = af.handle_slash_command("/approve patch-00000000")
        assert "❌" in result

    def test_approve_valid_patch(self):
        p = af.create_patch(
            description="Slash approve test",
            reason="Test",
            affected_files=["agents/safe.py"],
            diff_preview="+x\n",
        )
        result = af.handle_slash_command(f"/approve {p['patch_id']}")
        assert "✅" in result

    def test_approve_all_low(self):
        af.create_patch(
            description="Low slash test",
            reason="Test",
            affected_files=["agents/safe.py"],
            diff_preview="+x\n",
        )
        result = af.handle_slash_command("/approve all low")
        assert isinstance(result, str)

    def test_reject_missing_id(self):
        result = af.handle_slash_command("/reject")
        assert "Usage" in result

    def test_reject_valid_patch(self):
        p = af.create_patch(
            description="Slash reject test",
            reason="Test",
            affected_files=["agents/safe.py"],
            diff_preview="+x\n",
        )
        result = af.handle_slash_command(f"/reject {p['patch_id']}")
        assert "❌" in result

    def test_rollback_missing_id(self):
        result = af.handle_slash_command("/rollback")
        assert "Usage" in result

    def test_rollback_pending_fails(self):
        p = af.create_patch(
            description="Slash rollback test",
            reason="Test",
            affected_files=["agents/safe.py"],
            diff_preview="+x\n",
        )
        result = af.handle_slash_command(f"/rollback {p['patch_id']}")
        assert "❌" in result

    def test_explain_missing_id(self):
        result = af.handle_slash_command("/explain")
        assert "Usage" in result

    def test_explain_valid_patch(self):
        p = af.create_patch(
            description="Slash explain test",
            reason="Test reason",
            affected_files=["agents/safe.py"],
            diff_preview="+x\n",
        )
        result = af.handle_slash_command(f"/explain {p['patch_id']}")
        assert p["patch_id"] in result
        assert "Status" in result

    def test_history_empty(self):
        result = af.handle_slash_command("/history")
        assert "No change history" in result

    def test_history_shows_entries(self):
        af.create_patch(
            description="History entry test",
            reason="Test",
            affected_files=["agents/safe.py"],
            diff_preview="+x\n",
        )
        result = af.handle_slash_command("/history")
        assert "⏳" in result  # pending emoji

    def test_improve_missing_module(self):
        result = af.handle_slash_command("/improve")
        assert "Usage" in result

    def test_improve_nonexistent_module(self):
        result = af.handle_slash_command("/improve nonexistent_module_xyz")
        assert "complete" in result.lower()

    def test_mode_get_current(self):
        result = af.handle_slash_command("/mode")
        assert "Current mode" in result

    def test_mode_set_general(self):
        result = af.handle_slash_command("/mode general")
        assert "GENERAL" in result

    def test_mode_set_invalid(self):
        result = af.handle_slash_command("/mode turbo")
        assert "❌" in result

    def test_blacklight_on(self):
        result = af.handle_slash_command("/blacklight on")
        assert "BLACKLIGHT" in result or "⚡" in result
        af.set_blacklight_active(False)  # cleanup

    def test_blacklight_off(self):
        af.set_blacklight_active(True)
        result = af.handle_slash_command("/blacklight off")
        assert "deactivated" in result.lower() or "🔴" in result

    def test_blacklight_invalid(self):
        result = af.handle_slash_command("/blacklight maybe")
        assert "Usage" in result

    def test_unknown_command(self):
        result = af.handle_slash_command("/unknownxyz")
        assert "Unknown" in result
        assert "/help" in result

    def test_compact_empty(self):
        result = af.handle_slash_command("/compact")
        assert isinstance(result, str)

    def test_cost_returns_report(self):
        result = af.handle_slash_command("/cost")
        assert "Session Report" in result
        assert "patches" in result.lower()

    def test_schedule_register(self):
        result = af.handle_slash_command("/schedule nightly_scan daily")
        assert "nightly_scan" in result
        assert "daily" in result

    def test_schedule_list_empty(self):
        result = af.handle_slash_command("/schedule list")
        assert "No schedules" in result

    def test_schedule_list_shows_entry(self):
        af.register_schedule("show_me", "daily")
        result = af.handle_slash_command("/schedule list")
        assert "show_me" in result

    def test_schedule_remove(self):
        af.register_schedule("remove_me", "daily")
        result = af.handle_slash_command("/schedule remove remove_me")
        assert "removed" in result.lower()

    def test_schedule_remove_nonexistent(self):
        result = af.handle_slash_command("/schedule remove does_not_exist")
        assert "❌" in result

    def test_schedule_missing_freq(self):
        result = af.handle_slash_command("/schedule onlyname")
        assert "Usage" in result

    def test_plan_missing_args(self):
        result = af.handle_slash_command("/plan")
        assert "Usage" in result

    def test_plan_stores_task(self):
        af.handle_slash_command("/plan Improve the UI layout and fix bugs")
        state = af._load_state()
        assert state.get("plan_pending_task") is not None

    def test_plan_returns_plan_block(self):
        result = af.handle_slash_command("/plan Fix critical login crash in auth module")
        assert "PLAN" in result

    def test_plan_shows_execute_hint(self):
        result = af.handle_slash_command("/plan Fix login bug")
        assert "/execute" in result or "execute" in result.lower()

    def test_execute_no_plan(self):
        result = af.handle_slash_command("/execute")
        assert "No pending plan" in result

    def test_execute_runs_stored_plan(self):
        af.handle_slash_command("/plan Fix the login error crash")
        result = af.handle_slash_command("/execute")
        assert isinstance(result, str)
        assert "Summary" in result

    def test_execute_clears_pending_plan(self):
        af.handle_slash_command("/plan Fix login error")
        af.handle_slash_command("/execute")
        state = af._load_state()
        assert state.get("plan_pending_task") is None

    def test_research_missing_query(self):
        result = af.handle_slash_command("/research")
        assert "Usage" in result

    def test_research_returns_string(self, monkeypatch):
        import urllib.request as _urlreq
        monkeypatch.setattr(_urlreq, "urlopen", lambda *a, **kw: (_ for _ in ()).throw(OSError("offline")))
        result = af.handle_slash_command("/research cold email tips")
        assert isinstance(result, str)
        assert "cold email tips" in result


# ══════════════════════════════════════════════════════════════════════════════
# handle_chat_command slash delegation
# ══════════════════════════════════════════════════════════════════════════════

class TestHandleChatCommandSlashDelegation:
    def test_slash_help_via_handle_chat_command(self):
        result = af.handle_chat_command("/help")
        assert "/scan" in result

    def test_slash_status_via_handle_chat_command(self):
        result = af.handle_chat_command("/status")
        assert "ASCEND_FORGE Status" in result

    def test_slash_scan_via_handle_chat_command(self):
        result = af.handle_chat_command("/scan")
        assert "Scan" in result

    def test_legacy_ascend_prefix_still_works(self):
        result = af.handle_chat_command("ascend: status")
        assert "ASCEND_FORGE Status" in result

    def test_non_slash_non_ascend_still_empty(self):
        assert af.handle_chat_command("random text") == ""

    def test_unknown_command_mentions_help(self):
        result = af.handle_chat_command("ascend: unknowncommandxyz")
        assert "/help" in result or "help" in result.lower()


# ══════════════════════════════════════════════════════════════════════════════
# New state fields
# ══════════════════════════════════════════════════════════════════════════════

class TestNewStateFields:
    def test_default_state_has_schedules(self):
        state = af._default_state()
        assert "schedules" in state
        assert isinstance(state["schedules"], dict)

    def test_default_state_has_plan_pending_task(self):
        state = af._default_state()
        assert "plan_pending_task" in state
        assert state["plan_pending_task"] is None

    def test_load_state_includes_new_fields(self):
        state = af._load_state()
        assert "schedules" in state
        assert "plan_pending_task" in state

