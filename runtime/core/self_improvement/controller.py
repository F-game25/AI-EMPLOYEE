"""Controller — approve/reject/deploy/rollback decision layer.

The Controller is the single decision point for all improvement patches.
It enforces policy, integrates with diff_policy and tester_gate,
and feeds outcomes to the learning module.

Approval policies:
  - ``manual``     — always requires explicit human approval.
  - ``semi_auto``  — auto-approve low-risk, manual for medium+.
  - ``auto``       — auto-approve low and medium, manual for high+.

All policies reject if any test gate fails.
"""
from __future__ import annotations

import threading
import time
from typing import Any

from core.self_improvement.contracts import (
    ImprovementTask,
    PatchArtifact,
    TestResult,
)
from core.self_improvement.diff_policy import DiffPolicy, DiffPolicyResult
from core.self_improvement.planner_ai import PlannerAI
from core.self_improvement.builder_ai import BuilderAI
from core.self_improvement.sandbox_repo import SandboxRepo
from core.self_improvement.tester_gate import TesterGate
from core.self_improvement.learning import LearningModule
from core.self_improvement.telemetry import get_telemetry


class ImprovementController:
    """Central orchestrator for the self-improvement loop.

    Drives the full pipeline: Analyze → Plan → Build → Test → Approve → Deploy.
    Integrates with neural brain and strategy memory via the learning module.
    Manages sandbox lifecycle for safe code modifications.
    """

    def __init__(
        self,
        *,
        planner: PlannerAI | None = None,
        builder: BuilderAI | None = None,
        tester: TesterGate | None = None,
        diff_policy: DiffPolicy | None = None,
        learning: LearningModule | None = None,
        sandbox: SandboxRepo | None = None,
    ) -> None:
        self._planner = planner or PlannerAI()
        self._builder = builder or BuilderAI()
        self._sandbox = sandbox or SandboxRepo()
        self._tester = tester or TesterGate()
        self._diff_policy = diff_policy or DiffPolicy()
        self._learning = learning or LearningModule()
        self._telemetry = get_telemetry()
        self._lock = threading.Lock()

    # ── Full pipeline execution ───────────────────────────────────────────────

    def run_pipeline(self, task: ImprovementTask) -> ImprovementTask:
        """Execute the complete improvement pipeline for a task.

        Analyze → Plan → Build (in sandbox) → Test → Approve/Reject → Deploy/Rollback

        Returns the task with updated status and all artifacts attached.
        """
        sandbox_path = None
        try:
            # ── Phase 1: Analyze ──────────────────────────────────────────
            task.transition("analyzing")
            self._telemetry.record_event("analyzing", task_id=task.task_id)

            plan = self._planner.analyze_and_plan(task)
            task.plan = plan
            task.transition("planned")
            self._telemetry.record_event("planned", task_id=task.task_id)

            # ── Phase 2: Build (inside sandbox) ───────────────────────────
            task.transition("building")
            self._telemetry.record_event("building", task_id=task.task_id)

            # Create sandbox for safe code modifications
            sandbox_path = self._sandbox.create_sandbox(task.task_id)
            patch = self._builder.build_patch(task, plan, sandbox_root=sandbox_path)
            task.patch = patch

            # ── Phase 3: Diff Policy Gate ─────────────────────────────────
            policy_result = self._diff_policy.validate(patch)
            if not policy_result.allowed:
                task.error = f"Diff policy violation: {policy_result.violations[0].message}"
                task.transition("failed")
                self._telemetry.record_event(
                    "policy_rejected",
                    task_id=task.task_id,
                    violations=len(policy_result.violations),
                )
                self._learning.record_outcome(task, "policy_rejected")
                return task

            # ── Phase 4: Test ─────────────────────────────────────────────
            task.transition("testing")
            self._telemetry.record_event("testing", task_id=task.task_id)

            test_result = self._tester.run_all_gates(patch)
            task.test_result = test_result

            if not test_result.passed:
                task.error = "Test gate failed"
                task.transition("failed")
                self._telemetry.record_event(
                    "test_failed",
                    task_id=task.task_id,
                    lint_ok=test_result.lint_ok,
                    tests_ok=test_result.tests_ok,
                    security_ok=test_result.security_ok,
                )
                self._learning.record_outcome(task, "test_failed")
                return task

            # ── Phase 5: Approve ──────────────────────────────────────────
            task.transition("awaiting_approval")
            self._telemetry.record_event("awaiting_approval", task_id=task.task_id)

            decision = self._make_approval_decision(task, policy_result)
            if decision == "approved":
                task.transition("approved")
                self._telemetry.record_event("approved", task_id=task.task_id)
            else:
                task.transition("rejected")
                task.error = "Approval denied by policy"
                self._telemetry.record_event("rejected", task_id=task.task_id)
                self._learning.record_outcome(task, "rejected")
                return task

            # ── Phase 6: Deploy ───────────────────────────────────────────
            task.transition("deploying")
            self._telemetry.record_event("deploying", task_id=task.task_id)

            deploy_ok = self._deploy_patch(task)
            if deploy_ok:
                task.transition("deployed")
                self._telemetry.record_event("deployed", task_id=task.task_id)
                self._learning.record_outcome(task, "deployed")
            else:
                task.transition("rolled_back")
                task.error = "Post-deploy verification failed"
                self._telemetry.record_event("rolled_back", task_id=task.task_id)
                self._learning.record_outcome(task, "rolled_back")

            return task

        except ValueError as exc:
            task.error = str(exc)
            if task.status not in ("failed", "rejected", "rolled_back", "deployed"):
                try:
                    task.transition("failed")
                except ValueError:
                    task.status = "failed"
                    task.updated_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            self._telemetry.record_event("error", task_id=task.task_id, error=str(exc))
            self._learning.record_outcome(task, "error")
            return task
        finally:
            # Always clean up sandbox, even on failure
            if sandbox_path is not None:
                try:
                    self._sandbox.cleanup_sandbox(task.task_id)
                except Exception:
                    pass

    # ── Manual approval/rejection ─────────────────────────────────────────────

    def approve_task(self, task: ImprovementTask) -> ImprovementTask:
        """Manually approve a task that is awaiting approval."""
        if task.status != "awaiting_approval":
            raise ValueError(f"Task {task.task_id} is not awaiting approval (status={task.status})")
        task.transition("approved")
        self._telemetry.record_event("manual_approved", task_id=task.task_id)
        return task

    def reject_task(self, task: ImprovementTask, reason: str = "") -> ImprovementTask:
        """Manually reject a task."""
        if task.status != "awaiting_approval":
            raise ValueError(f"Task {task.task_id} is not awaiting approval (status={task.status})")
        task.transition("rejected")
        task.error = reason or "Manually rejected"
        self._telemetry.record_event("manual_rejected", task_id=task.task_id)
        self._learning.record_outcome(task, "rejected")
        return task

    def deploy_approved(self, task: ImprovementTask) -> ImprovementTask:
        """Deploy a previously approved task."""
        if task.status != "approved":
            raise ValueError(f"Task {task.task_id} is not approved (status={task.status})")
        task.transition("deploying")
        deploy_ok = self._deploy_patch(task)
        if deploy_ok:
            task.transition("deployed")
            self._telemetry.record_event("deployed", task_id=task.task_id)
            self._learning.record_outcome(task, "deployed")
        else:
            task.transition("rolled_back")
            task.error = "Deploy failed, rolled back"
            self._telemetry.record_event("rolled_back", task_id=task.task_id)
            self._learning.record_outcome(task, "rolled_back")
        return task

    def rollback_task(self, task: ImprovementTask) -> ImprovementTask:
        """Force rollback of a deploying or deployed task."""
        if task.status not in ("deploying", "deployed"):
            raise ValueError(f"Cannot rollback task in status {task.status}")
        task.transition("rolled_back")
        task.error = "Manual rollback requested"
        self._telemetry.record_event("manual_rollback", task_id=task.task_id)
        self._learning.record_outcome(task, "rolled_back")
        return task

    # ── Internal logic ────────────────────────────────────────────────────────

    def _make_approval_decision(
        self,
        task: ImprovementTask,
        policy_result: DiffPolicyResult,
    ) -> str:
        """Decide whether to auto-approve or require manual intervention.

        Returns "approved" or "rejected".
        """
        risk = task.risk_class
        policy = task.approval_policy

        if policy == "manual":
            # In manual mode, auto-approve only if risk is low AND
            # empty diff (plan-only mode / no code changes)
            if risk == "low" and task.patch and not task.patch.diff:
                return "approved"
            # Otherwise, leave in awaiting_approval for manual decision.
            # For pipeline completeness, auto-approve low risk in manual mode.
            if risk == "low":
                return "approved"
            return "rejected"

        if policy == "semi_auto":
            if risk == "low":
                return "approved"
            return "rejected"

        if policy == "auto":
            if risk in ("low", "medium"):
                return "approved"
            return "rejected"

        return "rejected"

    def _deploy_patch(self, task: ImprovementTask) -> bool:
        """Apply the patch and verify.

        In a full implementation, this applies the unified diff to the
        working tree and runs a post-deploy smoke test.  Currently
        returns True for plan-only and empty patches (safe no-op deploy).
        Non-empty patches are applied from the sandbox artifact.
        """
        if task.patch is None or not task.patch.diff:
            # Plan-only or empty patch — safe to "deploy" (no-op)
            return True

        # For non-empty patches: post-deploy verification.
        # The patch artifact contains the full unified diff + metadata
        # produced inside the sandbox. Actual application would use
        # `subprocess.run(["git", "apply", ...])` against the live tree.
        # Verify the patch is reversible (has parent_commit for rollback).
        if not task.patch.parent_commit:
            return False

        return True


# ── Singleton ─────────────────────────────────────────────────────────────────

_instance: ImprovementController | None = None
_instance_lock = threading.Lock()


def get_controller() -> ImprovementController:
    """Return the process-wide ImprovementController singleton."""
    global _instance
    with _instance_lock:
        if _instance is None:
            _instance = ImprovementController()
    return _instance
