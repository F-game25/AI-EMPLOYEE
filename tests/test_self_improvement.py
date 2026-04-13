"""Comprehensive tests for the self-improvement closed-loop system.

Covers:
  - State machine transitions (valid + invalid)
  - Diff policy enforcement (binary, protected, size, rewrite ratio)
  - Risk scoring and classification
  - Queue lifecycle (enqueue, peek, update, depth, summary)
  - Full pipeline integration (plan-only and with patches)
  - Approval policies (manual, semi_auto, auto)
  - Failure paths (test fail, policy reject, deploy fail, rollback)
  - Learning feedback to strategy_store and brain_registry
  - Telemetry counters and dashboard payload
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

# Ensure runtime modules are importable
_RUNTIME_DIR = Path(__file__).parent.parent / "runtime"
for _p in [
    str(_RUNTIME_DIR),
    str(_RUNTIME_DIR / "core"),
    str(_RUNTIME_DIR / "actions"),
    str(_RUNTIME_DIR / "memory"),
    str(_RUNTIME_DIR / "brain"),
    str(_RUNTIME_DIR / "agents"),
]:
    if _p not in sys.path:
        sys.path.insert(0, _p)


# ═════════════════════════════════════════════════════════════════════════════
# State Machine
# ═════════════════════════════════════════════════════════════════════════════

class TestStateMachine:
    """Test the improvement task state machine transitions."""

    def test_valid_transitions(self):
        from core.self_improvement.contracts import ImprovementTask

        task = ImprovementTask(description="test")
        assert task.status == "queued"

        task.transition("analyzing")
        assert task.status == "analyzing"

        task.transition("planned")
        assert task.status == "planned"

        task.transition("building")
        assert task.status == "building"

        task.transition("testing")
        assert task.status == "testing"

        task.transition("awaiting_approval")
        assert task.status == "awaiting_approval"

        task.transition("approved")
        assert task.status == "approved"

        task.transition("deploying")
        assert task.status == "deploying"

        task.transition("deployed")
        assert task.status == "deployed"
        assert task.is_terminal

    def test_reject_path(self):
        from core.self_improvement.contracts import ImprovementTask

        task = ImprovementTask(description="test")
        task.transition("analyzing")
        task.transition("planned")
        task.transition("building")
        task.transition("testing")
        task.transition("awaiting_approval")
        task.transition("rejected")
        assert task.status == "rejected"
        assert task.is_terminal

    def test_rollback_path(self):
        from core.self_improvement.contracts import ImprovementTask

        task = ImprovementTask(description="test")
        task.transition("analyzing")
        task.transition("planned")
        task.transition("building")
        task.transition("testing")
        task.transition("awaiting_approval")
        task.transition("approved")
        task.transition("deploying")
        task.transition("rolled_back")
        assert task.status == "rolled_back"
        assert task.is_terminal

    def test_fail_from_any_active_state(self):
        from core.self_improvement.contracts import ImprovementTask

        for state in ("queued", "analyzing", "planned", "building", "testing", "approved", "deploying"):
            task = ImprovementTask(description="test")
            task.status = state
            task.transition("failed")
            assert task.status == "failed"
            assert task.is_terminal

    def test_illegal_transition_raises(self):
        from core.self_improvement.contracts import ImprovementTask

        task = ImprovementTask(description="test")
        with pytest.raises(ValueError, match="Illegal state transition"):
            task.transition("deployed")  # can't jump from queued to deployed

    def test_terminal_states_cannot_transition(self):
        from core.self_improvement.contracts import ImprovementTask

        for terminal in ("deployed", "rolled_back", "rejected", "failed"):
            task = ImprovementTask(description="test")
            task.status = terminal
            with pytest.raises(ValueError, match="Illegal state transition"):
                task.transition("queued")

    def test_task_to_dict_roundtrip(self):
        from core.self_improvement.contracts import ImprovementTask, ImprovementPlan

        task = ImprovementTask(
            description="improve login",
            target_area="core",
            risk_class="high",
        )
        task.plan = ImprovementPlan(task_id=task.task_id, what="test")
        d = task.to_dict()
        assert d["task_id"] == task.task_id
        assert d["description"] == "improve login"
        assert d["risk_class"] == "high"
        assert d["plan"]["what"] == "test"
        assert d["plan"]["plan_hash"]  # auto-generated


# ═════════════════════════════════════════════════════════════════════════════
# Diff Policy
# ═════════════════════════════════════════════════════════════════════════════

class TestDiffPolicy:
    """Test the diff governance rules."""

    def test_allow_clean_patch(self):
        from core.self_improvement.contracts import PatchArtifact
        from core.self_improvement.diff_policy import DiffPolicy

        patch = PatchArtifact(
            files_changed=["runtime/core/planner.py"],
            lines_added=10,
            lines_removed=5,
            risk_level="low",
        )
        result = DiffPolicy().validate(patch)
        assert result.allowed
        assert len(result.violations) == 0

    def test_reject_binary_file(self):
        from core.self_improvement.contracts import PatchArtifact
        from core.self_improvement.diff_policy import DiffPolicy

        patch = PatchArtifact(
            files_changed=["runtime/models/brain.pth"],
            lines_added=1,
            risk_level="low",
        )
        result = DiffPolicy().validate(patch)
        assert not result.allowed
        violations = [v for v in result.violations if v.rule == "no_binary_files"]
        assert len(violations) >= 1

    def test_reject_protected_path(self):
        from core.self_improvement.contracts import PatchArtifact
        from core.self_improvement.diff_policy import DiffPolicy

        patch = PatchArtifact(
            files_changed=["runtime/brain/brain.py"],
            lines_added=5,
            risk_level="low",
        )
        result = DiffPolicy().validate(patch)
        assert not result.allowed
        violations = [v for v in result.violations if v.rule == "protected_path"]
        assert len(violations) >= 1

    def test_reject_outside_whitelist(self):
        from core.self_improvement.contracts import PatchArtifact
        from core.self_improvement.diff_policy import DiffPolicy

        patch = PatchArtifact(
            files_changed=["random/unknown/file.py"],
            lines_added=5,
            risk_level="low",
        )
        result = DiffPolicy().validate(patch)
        assert not result.allowed
        violations = [v for v in result.violations if v.rule == "outside_whitelist"]
        assert len(violations) >= 1

    def test_reject_patch_too_large(self):
        from core.self_improvement.contracts import PatchArtifact
        from core.self_improvement.diff_policy import DiffPolicy

        patch = PatchArtifact(
            files_changed=["runtime/core/executor.py"],
            lines_added=300,
            lines_removed=100,
            risk_level="medium",  # max 100 lines for medium
        )
        result = DiffPolicy().validate(patch)
        assert not result.allowed
        violations = [v for v in result.violations if v.rule == "patch_too_large"]
        assert len(violations) >= 1

    def test_reject_too_many_files(self):
        from core.self_improvement.contracts import PatchArtifact
        from core.self_improvement.diff_policy import DiffPolicy

        patch = PatchArtifact(
            files_changed=[f"runtime/core/file{i}.py" for i in range(8)],
            lines_added=10,
            risk_level="medium",  # max 5 files for medium
        )
        result = DiffPolicy().validate(patch)
        assert not result.allowed

    def test_reject_critical_risk(self):
        from core.self_improvement.contracts import PatchArtifact
        from core.self_improvement.diff_policy import DiffPolicy

        patch = PatchArtifact(
            files_changed=["runtime/core/something.py"],
            lines_added=1,
            risk_level="critical",
        )
        result = DiffPolicy().validate(patch)
        assert not result.allowed
        violations = [v for v in result.violations if v.rule == "critical_risk"]
        assert len(violations) >= 1

    def test_reject_secret_file(self):
        from core.self_improvement.contracts import PatchArtifact
        from core.self_improvement.diff_policy import DiffPolicy

        patch = PatchArtifact(
            files_changed=["runtime/config/.env"],
            lines_added=1,
            risk_level="low",
        )
        result = DiffPolicy().validate(patch)
        assert not result.allowed

    def test_reject_full_rewrite(self):
        from core.self_improvement.contracts import PatchArtifact
        from core.self_improvement.diff_policy import DiffPolicy

        # Build a diff where 90% of lines are replaced (exceeds 60% threshold)
        diff = (
            "--- a/runtime/core/test.py\n"
            "+++ b/runtime/core/test.py\n"
            "@@ -1,10 +1,10 @@\n"
        )
        diff += "".join(f"-old line {i}\n" for i in range(9))
        diff += "".join(f"+new line {i}\n" for i in range(9))

        patch = PatchArtifact(
            files_changed=["runtime/core/test.py"],
            diff=diff,
            lines_added=9,
            lines_removed=9,
            risk_level="low",
        )
        result = DiffPolicy().validate(patch)
        assert not result.allowed
        violations = [v for v in result.violations if v.rule == "full_rewrite"]
        assert len(violations) >= 1


# ═════════════════════════════════════════════════════════════════════════════
# Queue
# ═════════════════════════════════════════════════════════════════════════════

class TestImprovementQueue:
    """Test the persistent FIFO task queue."""

    def test_enqueue_and_peek(self, tmp_path):
        from core.self_improvement.queue import ImprovementQueue

        q = ImprovementQueue(path=tmp_path / "queue.json")
        task = q.enqueue(description="optimize imports")
        assert task.task_id.startswith("imp-")
        assert task.status == "queued"

        peeked = q.peek()
        assert peeked is not None
        assert peeked.task_id == task.task_id

    def test_get_by_id(self, tmp_path):
        from core.self_improvement.queue import ImprovementQueue

        q = ImprovementQueue(path=tmp_path / "queue.json")
        task = q.enqueue(description="fix bug")
        found = q.get(task.task_id)
        assert found is not None
        assert found.description == "fix bug"

    def test_get_nonexistent_returns_none(self, tmp_path):
        from core.self_improvement.queue import ImprovementQueue

        q = ImprovementQueue(path=tmp_path / "queue.json")
        assert q.get("nonexistent-id") is None

    def test_update_persists(self, tmp_path):
        from core.self_improvement.queue import ImprovementQueue

        q = ImprovementQueue(path=tmp_path / "queue.json")
        task = q.enqueue(description="update")
        task.transition("analyzing")
        q.update(task)

        refreshed = q.get(task.task_id)
        assert refreshed is not None
        assert refreshed.status == "analyzing"

    def test_list_all_with_filter(self, tmp_path):
        from core.self_improvement.queue import ImprovementQueue

        q = ImprovementQueue(path=tmp_path / "queue.json")
        q.enqueue(description="task 1")
        task2 = q.enqueue(description="task 2")
        task2.transition("analyzing")
        q.update(task2)

        all_tasks = q.list_all()
        assert len(all_tasks) == 2

        queued = q.list_all(status="queued")
        assert len(queued) == 1

    def test_active_count(self, tmp_path):
        from core.self_improvement.queue import ImprovementQueue

        q = ImprovementQueue(path=tmp_path / "queue.json")
        q.enqueue(description="active 1")
        task2 = q.enqueue(description="done")
        task2.status = "deployed"
        q.update(task2)

        assert q.active_count() == 1

    def test_depth(self, tmp_path):
        from core.self_improvement.queue import ImprovementQueue

        q = ImprovementQueue(path=tmp_path / "queue.json")
        assert q.depth() == 0
        q.enqueue(description="one")
        q.enqueue(description="two")
        assert q.depth() == 2

    def test_summary(self, tmp_path):
        from core.self_improvement.queue import ImprovementQueue

        q = ImprovementQueue(path=tmp_path / "queue.json")
        q.enqueue(description="a")
        q.enqueue(description="b")
        summary = q.summary()
        assert summary["total"] == 2
        assert summary["active"] == 2
        assert "queued" in summary["by_status"]

    def test_can_run_for_area(self, tmp_path):
        from core.self_improvement.queue import ImprovementQueue

        q = ImprovementQueue(path=tmp_path / "queue.json")
        assert q.can_run_for_area("core") is True

        task = q.enqueue(description="fix core", target_area="core")
        task.transition("analyzing")
        q.update(task)
        assert q.can_run_for_area("core") is False
        assert q.can_run_for_area("agents") is True


# ═════════════════════════════════════════════════════════════════════════════
# Planner AI
# ═════════════════════════════════════════════════════════════════════════════

class TestPlannerAI:
    """Test the read-only planner."""

    def test_produces_plan(self):
        from core.self_improvement.contracts import ImprovementTask
        from core.self_improvement.planner_ai import PlannerAI

        task = ImprovementTask(
            description="optimize response time",
            target_area="core",
        )
        planner = PlannerAI()
        plan = planner.analyze_and_plan(task)

        assert plan.task_id == task.task_id
        assert plan.what == task.description
        assert len(plan.where) > 0
        assert plan.risk_level in ("low", "medium", "high", "critical")
        assert len(plan.acceptance_criteria) >= 3
        assert plan.plan_hash  # auto-computed

    def test_risk_classification(self):
        from core.self_improvement.planner_ai import PlannerAI

        planner = PlannerAI()
        assert planner._classify_risk("fix a test", "tests") == "low"
        assert planner._classify_risk("update API endpoint", "backend") == "high"
        assert planner._classify_risk("change brain model", "brain") == "critical"
        assert planner._classify_risk("optimize agent performance", "agents") == "medium"

    def test_brain_strategy_is_set(self):
        from core.self_improvement.contracts import ImprovementTask
        from core.self_improvement.planner_ai import PlannerAI

        task = ImprovementTask(description="general improvement", target_area="general")
        planner = PlannerAI()
        planner.analyze_and_plan(task)
        assert "source" in task.brain_strategy


# ═════════════════════════════════════════════════════════════════════════════
# Builder AI
# ═════════════════════════════════════════════════════════════════════════════

class TestBuilderAI:
    """Test the diff-only builder."""

    def test_build_empty_patch(self):
        from core.self_improvement.contracts import ImprovementTask, ImprovementPlan
        from core.self_improvement.builder_ai import BuilderAI

        task = ImprovementTask(description="plan-only")
        plan = ImprovementPlan(task_id=task.task_id, what="test")
        builder = BuilderAI()
        patch = builder.build_patch(task, plan)

        assert patch.task_id == task.task_id
        assert patch.plan_id == plan.plan_id
        assert patch.diff == ""
        assert patch.lines_added == 0

    def test_build_from_explicit_changes(self):
        from core.self_improvement.contracts import ImprovementTask, ImprovementPlan
        from core.self_improvement.builder_ai import BuilderAI

        task = ImprovementTask(description="fix import")
        plan = ImprovementPlan(task_id=task.task_id, what="test")
        builder = BuilderAI()

        changes = {
            "runtime/core/test.py": (
                "import os\nprint('hello')\n",
                "import os\nimport sys\nprint('hello')\n",
            ),
        }
        patch = builder.build_patch_from_changes(task, plan, changes)

        assert len(patch.files_changed) == 1
        assert "runtime/core/test.py" in patch.files_changed
        assert patch.lines_added >= 1
        assert "import sys" in patch.diff

    def test_empty_changes_produce_empty_patch(self):
        from core.self_improvement.contracts import ImprovementTask, ImprovementPlan
        from core.self_improvement.builder_ai import BuilderAI

        task = ImprovementTask(description="no change")
        plan = ImprovementPlan(task_id=task.task_id, what="test")
        builder = BuilderAI()

        changes = {
            "runtime/core/test.py": ("same content\n", "same content\n"),
        }
        patch = builder.build_patch_from_changes(task, plan, changes)
        assert patch.diff == ""
        assert len(patch.files_changed) == 0


# ═════════════════════════════════════════════════════════════════════════════
# Tester Gate — Security checks (no subprocess in CI)
# ═════════════════════════════════════════════════════════════════════════════

class TestTesterGateSecurity:
    """Test the static security analysis gate."""

    def test_clean_diff_passes_security(self):
        from core.self_improvement.contracts import PatchArtifact
        from core.self_improvement.tester_gate import TesterGate

        patch = PatchArtifact(
            diff="+import os\n+x = 1\n",
            lines_added=2,
        )
        tester = TesterGate()
        ok, details = tester.run_security_only(patch)
        assert ok is True
        assert len(details["issues"]) == 0

    def test_hardcoded_secret_fails_security(self):
        from core.self_improvement.contracts import PatchArtifact
        from core.self_improvement.tester_gate import TesterGate

        patch = PatchArtifact(
            diff='+password = "hunter2"\n',
            lines_added=1,
        )
        tester = TesterGate()
        ok, details = tester.run_security_only(patch)
        assert ok is False
        assert len(details["issues"]) >= 1

    def test_eval_fails_security(self):
        from core.self_improvement.contracts import PatchArtifact
        from core.self_improvement.tester_gate import TesterGate

        patch = PatchArtifact(
            diff="+result = eval(user_input)\n",
            lines_added=1,
        )
        tester = TesterGate()
        ok, details = tester.run_security_only(patch)
        assert ok is False

    def test_empty_diff_passes(self):
        from core.self_improvement.contracts import PatchArtifact
        from core.self_improvement.tester_gate import TesterGate

        patch = PatchArtifact(diff="", lines_added=0)
        tester = TesterGate()
        ok, details = tester.run_security_only(patch)
        assert ok is True


# ═════════════════════════════════════════════════════════════════════════════
# Controller — Full Pipeline Integration
# ═════════════════════════════════════════════════════════════════════════════

class _PassAllTester:
    """Stub tester gate that always passes all gates."""

    def run_all_gates(self, patch):
        from core.self_improvement.contracts import TestResult
        return TestResult(
            passed=True,
            lint_ok=True,
            tests_ok=True,
            security_ok=True,
            details={"stub": True},
            duration_ms=0.1,
        )


class _FailTestsTester:
    """Stub tester gate where the test suite fails."""

    def run_all_gates(self, patch):
        from core.self_improvement.contracts import TestResult
        return TestResult(
            passed=False,
            lint_ok=True,
            tests_ok=False,
            security_ok=True,
            details={"stub": True, "reason": "tests_failed"},
            duration_ms=0.1,
        )


class TestController:
    """Test the full pipeline controller."""

    def test_plan_only_pipeline_succeeds(self, tmp_path):
        """Plan-only mode: empty diff → auto-approve → deploy (no-op)."""
        os.environ["AI_HOME"] = str(tmp_path)
        from core.self_improvement.contracts import ImprovementTask
        from core.self_improvement.controller import ImprovementController

        task = ImprovementTask(
            description="improve docs",
            target_area="tests",
            risk_class="low",
            approval_policy="auto",
        )
        controller = ImprovementController(tester=_PassAllTester())
        result = controller.run_pipeline(task)

        assert result.status == "deployed"
        assert result.plan is not None
        assert result.patch is not None
        assert result.is_terminal

    def test_manual_high_risk_gets_rejected(self, tmp_path):
        os.environ["AI_HOME"] = str(tmp_path)
        from core.self_improvement.contracts import ImprovementTask
        from core.self_improvement.controller import ImprovementController

        task = ImprovementTask(
            description="change server config",
            target_area="backend",
            risk_class="high",
            approval_policy="manual",
        )
        controller = ImprovementController(tester=_PassAllTester())
        result = controller.run_pipeline(task)

        assert result.status == "rejected"
        assert result.is_terminal

    def test_semi_auto_low_risk_approved(self, tmp_path):
        os.environ["AI_HOME"] = str(tmp_path)
        from core.self_improvement.contracts import ImprovementTask
        from core.self_improvement.controller import ImprovementController

        task = ImprovementTask(
            description="fix test formatting",
            target_area="tests",
            risk_class="low",
            approval_policy="semi_auto",
        )
        controller = ImprovementController(tester=_PassAllTester())
        result = controller.run_pipeline(task)

        assert result.status == "deployed"

    def test_manual_approve_then_deploy(self, tmp_path):
        os.environ["AI_HOME"] = str(tmp_path)
        from core.self_improvement.contracts import ImprovementTask
        from core.self_improvement.controller import ImprovementController

        task = ImprovementTask(description="manual task", risk_class="low")
        task.status = "awaiting_approval"
        controller = ImprovementController()

        approved = controller.approve_task(task)
        assert approved.status == "approved"

        deployed = controller.deploy_approved(approved)
        assert deployed.status == "deployed"

    def test_manual_reject(self, tmp_path):
        os.environ["AI_HOME"] = str(tmp_path)
        from core.self_improvement.contracts import ImprovementTask
        from core.self_improvement.controller import ImprovementController

        task = ImprovementTask(description="rejected task", risk_class="high")
        task.status = "awaiting_approval"
        controller = ImprovementController()

        rejected = controller.reject_task(task, reason="too risky")
        assert rejected.status == "rejected"
        assert rejected.error == "too risky"

    def test_rollback(self, tmp_path):
        os.environ["AI_HOME"] = str(tmp_path)
        from core.self_improvement.contracts import ImprovementTask
        from core.self_improvement.controller import ImprovementController

        task = ImprovementTask(description="rollback test")
        task.status = "deploying"
        controller = ImprovementController()

        rolled = controller.rollback_task(task)
        assert rolled.status == "rolled_back"
        assert rolled.is_terminal

    def test_approve_wrong_state_raises(self, tmp_path):
        os.environ["AI_HOME"] = str(tmp_path)
        from core.self_improvement.contracts import ImprovementTask
        from core.self_improvement.controller import ImprovementController

        task = ImprovementTask(description="bad state")
        task.status = "queued"
        controller = ImprovementController()

        with pytest.raises(ValueError, match="not awaiting approval"):
            controller.approve_task(task)


# ═════════════════════════════════════════════════════════════════════════════
# Learning Module
# ═════════════════════════════════════════════════════════════════════════════

class TestLearning:
    """Test the feedback learning module."""

    def test_record_outcome_returns_summary(self, tmp_path):
        os.environ["AI_HOME"] = str(tmp_path)
        from core.self_improvement.contracts import ImprovementTask
        from core.self_improvement.learning import LearningModule

        task = ImprovementTask(
            description="test learning",
            target_area="core",
            risk_class="low",
        )
        learning = LearningModule()
        result = learning.record_outcome(task, "deployed")

        assert result["task_id"] == task.task_id
        assert result["outcome"] == "deployed"
        assert result["score"] == 1.0
        assert result["is_success"] is True
        assert "strategy_stored" in result
        assert "brain_learned" in result

    def test_record_failure(self, tmp_path):
        os.environ["AI_HOME"] = str(tmp_path)
        from core.self_improvement.contracts import ImprovementTask
        from core.self_improvement.learning import LearningModule

        task = ImprovementTask(description="failed", target_area="core")
        learning = LearningModule()
        result = learning.record_outcome(task, "test_failed")

        assert result["score"] == 0.1
        assert result["is_success"] is False

    def test_get_insights_empty(self, tmp_path):
        os.environ["AI_HOME"] = str(tmp_path)
        from core.self_improvement.learning import LearningModule

        learning = LearningModule()
        insights = learning.get_insights()

        assert insights["total_outcomes"] == 0
        assert insights["success_rate"] == 0.0
        assert insights["learning_active"] is True

    def test_get_insights_with_data(self, tmp_path):
        os.environ["AI_HOME"] = str(tmp_path)
        from core.self_improvement.contracts import ImprovementTask
        from core.self_improvement.learning import LearningModule

        learning = LearningModule()
        for i in range(5):
            task = ImprovementTask(description=f"task {i}", target_area="core")
            outcome = "deployed" if i % 2 == 0 else "test_failed"
            learning.record_outcome(task, outcome)

        insights = learning.get_insights()
        assert insights["total_outcomes"] == 5
        assert insights["successes"] == 3
        assert insights["failures"] == 2
        assert 0.0 < insights["success_rate"] < 1.0

    def test_strategy_store_integration(self, tmp_path):
        """Verify learning writes to the strategy store."""
        os.environ["AI_HOME"] = str(tmp_path)
        from memory.strategy_store import StrategyStore
        from core.self_improvement.contracts import ImprovementTask
        from core.self_improvement.learning import LearningModule

        store = StrategyStore(path=tmp_path / "strategies.json")
        learning = LearningModule()
        learning._strategy_store = store

        task = ImprovementTask(description="store test", target_area="agents")
        learning.record_outcome(task, "deployed")

        strategies = store.all_strategies()
        assert len(strategies) >= 1
        assert strategies[-1]["goal_type"] == "self_improvement:agents"
        assert strategies[-1]["agent"] == "self_improvement_loop"


# ═════════════════════════════════════════════════════════════════════════════
# Telemetry
# ═════════════════════════════════════════════════════════════════════════════

class TestTelemetry:
    """Test the telemetry module."""

    def test_record_event(self):
        from core.self_improvement.telemetry import ImprovementTelemetry

        t = ImprovementTelemetry()
        event = t.record_event("test_event", task_id="t1")
        assert event["event"] == "test_event"
        assert event["task_id"] == "t1"

    def test_counters(self):
        from core.self_improvement.telemetry import ImprovementTelemetry

        t = ImprovementTelemetry()
        t.record_event("analyzing")
        t.record_event("analyzing")
        t.record_event("deployed")

        counters = t.get_counters()
        assert counters["analyzing"] == 2
        assert counters["deployed"] == 1

    def test_recent_events(self):
        from core.self_improvement.telemetry import ImprovementTelemetry

        t = ImprovementTelemetry()
        for i in range(25):
            t.record_event(f"event_{i}")

        recent = t.get_recent_events(limit=10)
        assert len(recent) == 10
        assert recent[0]["event"] == "event_24"  # most recent first

    def test_dashboard_payload(self):
        from core.self_improvement.telemetry import ImprovementTelemetry

        t = ImprovementTelemetry()
        t.record_event("analyzing")
        t.record_event("deployed")
        t.record_event("test_failed")

        payload = t.dashboard_payload()
        si = payload["self_improvement"]
        assert si["active"] is True
        assert si["total_tasks_processed"] == 1
        assert si["deployed"] == 1
        assert si["test_failures"] == 1
        assert isinstance(si["pass_rate"], float)
        assert isinstance(si["top_failure_causes"], list)


# ═════════════════════════════════════════════════════════════════════════════
# Sandbox Repo
# ═════════════════════════════════════════════════════════════════════════════

class TestSandboxRepo:
    """Test sandbox lifecycle management."""

    def test_create_and_cleanup(self, tmp_path):
        from core.self_improvement.sandbox_repo import SandboxRepo

        repo = SandboxRepo(repo_root=tmp_path, sandbox_base=tmp_path / "sb")
        sandbox_path = repo.create_sandbox("task-123")
        assert sandbox_path.exists()
        assert (sandbox_path / ".sandbox_meta.json").exists()

        cleaned = repo.cleanup_sandbox("task-123")
        assert cleaned is True
        assert not sandbox_path.exists()

    def test_list_sandboxes(self, tmp_path):
        from core.self_improvement.sandbox_repo import SandboxRepo

        repo = SandboxRepo(repo_root=tmp_path, sandbox_base=tmp_path / "sb")
        repo.create_sandbox("task-a")
        repo.create_sandbox("task-b")

        listed = repo.list_sandboxes()
        assert len(listed) == 2

    def test_cleanup_nonexistent(self, tmp_path):
        from core.self_improvement.sandbox_repo import SandboxRepo

        repo = SandboxRepo(repo_root=tmp_path, sandbox_base=tmp_path / "sb")
        assert repo.cleanup_sandbox("nonexistent") is False


# ═════════════════════════════════════════════════════════════════════════════
# End-to-end Integration
# ═════════════════════════════════════════════════════════════════════════════

class TestEndToEnd:
    """Full integration tests covering the complete loop."""

    def test_test_gate_failure_rejects(self, tmp_path):
        """Pipeline with failing test gate → task fails."""
        os.environ["AI_HOME"] = str(tmp_path)
        from core.self_improvement.contracts import ImprovementTask
        from core.self_improvement.controller import ImprovementController

        task = ImprovementTask(
            description="test gate fail",
            target_area="tests",
            risk_class="low",
            approval_policy="auto",
        )
        controller = ImprovementController(tester=_FailTestsTester())
        result = controller.run_pipeline(task)

        assert result.status == "failed"
        assert "test gate" in result.error.lower()

    def test_queue_plan_build_test_deploy(self, tmp_path):
        """Complete end-to-end: queue → analyze → plan → build → test → approve → deploy."""
        os.environ["AI_HOME"] = str(tmp_path)
        from core.self_improvement.queue import ImprovementQueue
        from core.self_improvement.controller import ImprovementController

        queue = ImprovementQueue(path=tmp_path / "queue.json")
        task = queue.enqueue(
            description="add docstring to validator",
            target_area="tests",
            risk_class="low",
            approval_policy="auto",
        )
        assert task.status == "queued"

        controller = ImprovementController(tester=_PassAllTester())
        result = controller.run_pipeline(task)
        queue.update(result)

        assert result.status == "deployed"
        assert result.plan is not None
        assert result.patch is not None
        assert result.learning_outcome.get("outcome") == "deployed"

        # Verify it's persisted in the queue
        persisted = queue.get(task.task_id)
        assert persisted is not None
        assert persisted.status == "deployed"

    def test_pipeline_with_policy_violation(self, tmp_path):
        """Pipeline should fail when diff policy is violated."""
        os.environ["AI_HOME"] = str(tmp_path)
        from core.self_improvement.contracts import ImprovementTask, PatchArtifact
        from core.self_improvement.controller import ImprovementController
        from core.self_improvement.builder_ai import BuilderAI

        # Custom builder that produces a patch touching protected path
        class BadBuilder(BuilderAI):
            def build_patch(self, task, plan, **kw):
                return PatchArtifact(
                    task_id=task.task_id,
                    plan_id=plan.plan_id if plan else "",
                    files_changed=["runtime/brain/brain.py"],  # PROTECTED!
                    lines_added=5,
                    risk_level="low",
                )

        task = ImprovementTask(
            description="modify brain",
            target_area="brain",
            risk_class="low",
            approval_policy="auto",
        )
        controller = ImprovementController(builder=BadBuilder())
        result = controller.run_pipeline(task)

        assert result.status == "failed"
        assert "policy violation" in result.error.lower() or "protected" in result.error.lower()

    def test_learning_updates_strategy_store(self, tmp_path):
        """Verify that completed tasks update the strategy store."""
        os.environ["AI_HOME"] = str(tmp_path)
        from memory.strategy_store import StrategyStore
        from core.self_improvement.contracts import ImprovementTask
        from core.self_improvement.controller import ImprovementController
        from core.self_improvement.learning import LearningModule

        store = StrategyStore(path=tmp_path / "strategies.json")
        learning = LearningModule()
        learning._strategy_store = store

        task = ImprovementTask(
            description="optimize tests",
            target_area="tests",
            risk_class="low",
            approval_policy="auto",
        )
        controller = ImprovementController(learning=learning, tester=_PassAllTester())
        controller.run_pipeline(task)

        strategies = store.all_strategies()
        assert len(strategies) >= 1
        last = strategies[-1]
        assert last["goal_type"] == "self_improvement:tests"

    def test_telemetry_tracks_full_pipeline(self, tmp_path):
        """Verify telemetry captures all pipeline phases."""
        os.environ["AI_HOME"] = str(tmp_path)
        from core.self_improvement.contracts import ImprovementTask
        from core.self_improvement.controller import ImprovementController
        from core.self_improvement.telemetry import ImprovementTelemetry

        telemetry = ImprovementTelemetry()
        # Inject fresh telemetry (not singleton for isolation)
        import core.self_improvement.telemetry as tel_mod
        old = tel_mod._instance
        tel_mod._instance = telemetry

        try:
            task = ImprovementTask(
                description="telemetry test",
                target_area="tests",
                risk_class="low",
                approval_policy="auto",
            )
            controller = ImprovementController(tester=_PassAllTester())
            controller._telemetry = telemetry
            controller.run_pipeline(task)

            counters = telemetry.get_counters()
            assert counters.get("analyzing", 0) >= 1
            assert counters.get("planned", 0) >= 1
            assert counters.get("building", 0) >= 1

            payload = telemetry.dashboard_payload()
            assert payload["self_improvement"]["active"] is True
        finally:
            tel_mod._instance = old
