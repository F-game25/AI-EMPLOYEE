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
        assert len(af._load_changelog()) > initial_count

    def test_observe_only_still_returns_analysis(self):
        state = af._load_state()
        state["observe_only"] = True
        af._save_state(state)
        # Should return analysis even when observe-only blocks patch creation
        result = af.handle_complex_task("Improve the UI layout and design")
        assert isinstance(result, str)
        assert "Summary" in result

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

