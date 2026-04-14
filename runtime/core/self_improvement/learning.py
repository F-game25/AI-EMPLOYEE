"""Learning Module — feeds improvement outcomes to memory and neural brain.

Connects the self-improvement loop to:
  1. **Strategy Store** — records which improvement approaches succeed/fail.
  2. **Brain Registry** — trains the neural network on improvement outcomes.
  3. **Intelligence Core** — updates user/system profiles with learned data.

This closes the feedback loop: future planning decisions are influenced
by historical accept/reject/deploy/rollback statistics.
"""
from __future__ import annotations

import logging
import time
import threading
from typing import Any

from core.brain_weights import update_weight
from core.self_improvement.contracts import ImprovementTask

_log = logging.getLogger(__name__)


class LearningModule:
    """Records improvement outcomes and feeds them to brain + memory."""

    def __init__(self) -> None:
        self._brain_registry = None
        self._strategy_store = None
        self._intelligence = None
        self._lock = threading.Lock()
        self._outcome_history: list[dict[str, Any]] = []
        self._max_history = 500

    # ── Lazy dependency loading ───────────────────────────────────────────────

    def _get_brain(self):
        if self._brain_registry is None:
            try:
                from core.brain_registry import brain
                self._brain_registry = brain
            except Exception:
                pass
        return self._brain_registry

    def _get_strategy_store(self):
        if self._strategy_store is None:
            try:
                from memory.strategy_store import get_strategy_store
                self._strategy_store = get_strategy_store()
            except Exception:
                pass
        return self._strategy_store

    def _get_intelligence(self):
        if self._intelligence is None:
            try:
                from brain.intelligence import get_intelligence
                self._intelligence = get_intelligence()
            except Exception:
                pass
        return self._intelligence

    # ── Core API ──────────────────────────────────────────────────────────────

    @staticmethod
    def _score_to_reward(score: float) -> float:
        """Map a score in [0, 1] to a reward signal in [-1, 1]."""
        return (score * 2) - 1.0

    @staticmethod
    def calculate_reward(result: Any) -> float:
        if hasattr(result, "success") and getattr(result, "success"):
            return 1.0
        if hasattr(result, "partial") and getattr(result, "partial"):
            return 0.0
        if isinstance(result, dict):
            if result.get("success"):
                return 1.0
            if result.get("partial"):
                return 0.0
            if result.get("outcome") in ("deployed", "approved"):
                return 1.0
            if result.get("outcome") in ("rolled_back",):
                return 0.0
        return -1.0

    def learn(self, agent: str, result: Any) -> dict[str, Any]:
        reward = self.calculate_reward(result)
        before, after = update_weight(agent, reward)
        return {
            "agent": agent,
            "reward": reward,
            "weight_before": round(before, 4),
            "weight_after": round(after, 4),
        }

    @staticmethod
    def _brain_selected_agent(task: ImprovementTask) -> str | None:
        brain_strategy = task.brain_strategy if isinstance(task.brain_strategy, dict) else {}
        selected = brain_strategy.get("selected_agent")
        return selected if isinstance(selected, str) else None

    def record_outcome(
        self,
        task: ImprovementTask,
        outcome: str,
    ) -> dict[str, Any]:
        """Record the outcome of an improvement task.

        Feeds back to:
          - strategy_store (memory persistence)
          - brain_registry (neural network learning)
          - intelligence (user/system profile update)

        Parameters
        ----------
        task:
            The completed improvement task.
        outcome:
            One of: "deployed", "rolled_back", "rejected",
            "test_failed", "policy_rejected", "error".

        Returns a summary of what was learned.
        """
        # Score mapping: higher = better outcome
        score_map = {
            "deployed": 1.0,
            "approved": 0.8,
            "rolled_back": 0.2,
            "rejected": 0.1,
            "test_failed": 0.1,
            "policy_rejected": 0.05,
            "error": 0.0,
        }
        score = score_map.get(outcome, 0.0)
        reward = self._score_to_reward(score)
        is_success = outcome in ("deployed", "approved")

        record = {
            "task_id": task.task_id,
            "agent": "self_improvement_loop",
            "description": task.description,
            "target_area": task.target_area,
            "risk_class": task.risk_class,
            "outcome": outcome,
            "decision_reason": self._decision_reason(task, outcome),
            "neural_input": task.brain_strategy or {},
            "score": score,
            "is_success": is_success,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "brain_strategy": task.brain_strategy,
        }

        # ── 1. Store in strategy memory ───────────────────────────────────
        strategy_result = self._record_to_strategy_store(task, outcome, score)
        record["strategy_stored"] = strategy_result is not None

        # ── 2. Feed to neural brain ───────────────────────────────────────
        brain_result = self._feed_brain(task, outcome, score)
        record["brain_learned"] = brain_result.get("learned", False)
        record["brain_reward"] = brain_result.get("reward", 0.0)
        record["reward_signal"] = reward
        selected_agent = self._brain_selected_agent(task)
        reinforcement = self.learn(selected_agent or "task_orchestrator", {"outcome": outcome})
        record["reinforcement"] = reinforcement

        # ── 3. Update intelligence profile ────────────────────────────────
        intel_result = self._update_intelligence(task, outcome, score)
        record["intel_updated"] = intel_result

        # ── Store in local history ────────────────────────────────────────
        with self._lock:
            self._outcome_history.append(record)
            if len(self._outcome_history) > self._max_history:
                self._outcome_history = self._outcome_history[-self._max_history:]

        task.learning_outcome = record
        return record

    def get_insights(self) -> dict[str, Any]:
        """Return learning insights for the dashboard/API."""
        with self._lock:
            history = list(self._outcome_history)

        total = len(history)
        if total == 0:
            return {
                "total_outcomes": 0,
                "success_rate": 0.0,
                "top_failure_causes": [],
                "learning_active": True,
                "brain_connected": self._get_brain() is not None,
                "memory_connected": self._get_strategy_store() is not None,
            }

        successes = sum(1 for h in history if h.get("is_success"))
        failures = [h for h in history if not h.get("is_success")]
        failure_causes: dict[str, int] = {}
        for f in failures:
            cause = f.get("outcome", "unknown")
            failure_causes[cause] = failure_causes.get(cause, 0) + 1

        top_failures = sorted(failure_causes.items(), key=lambda x: -x[1])[:5]

        return {
            "total_outcomes": total,
            "success_rate": round(successes / total, 3),
            "successes": successes,
            "failures": total - successes,
            "top_failure_causes": [
                {"cause": c, "count": n} for c, n in top_failures
            ],
            "recent_outcomes": history[-10:],
            "learning_active": True,
            "brain_connected": self._get_brain() is not None,
            "memory_connected": self._get_strategy_store() is not None,
        }

    # ── Internal: Strategy Store ──────────────────────────────────────────────

    @staticmethod
    def _decision_reason(task: ImprovementTask, outcome: str) -> str:
        """Build a human-readable explanation for why the outcome happened."""
        if outcome == "deployed":
            return "All gates passed; patch deployed successfully."
        if outcome == "approved":
            return "Patch approved by policy."
        if outcome == "rejected":
            return task.error or "Approval policy rejected this risk level."
        if outcome == "rolled_back":
            return task.error or "Post-deploy verification failed; rolled back."
        if outcome == "test_failed":
            return task.error or "One or more test gates failed."
        if outcome == "policy_rejected":
            return task.error or "Diff policy violation detected."
        return task.error or f"Outcome: {outcome}"

    def _record_to_strategy_store(
        self,
        task: ImprovementTask,
        outcome: str,
        score: float,
    ) -> dict | None:
        store = self._get_strategy_store()
        if store is None:
            return None
        try:
            return store.record(
                goal_type=f"self_improvement:{task.target_area}",
                agent="self_improvement_loop",
                config={
                    "target_area": task.target_area,
                    "risk_class": task.risk_class,
                    "approval_policy": task.approval_policy,
                },
                outcome_score=score,
                outcome_status="success" if score >= 0.6 else "failed",
                context={
                    "task_id": task.task_id,
                    "plan_id": task.plan.plan_id if task.plan else "",
                    "patch_id": task.patch.patch_id if task.patch else "",
                },
                outcome={
                    "status": outcome,
                    "error": task.error,
                },
                notes=f"Self-improvement outcome: {outcome}",
            )
        except Exception as exc:
            _log.debug("Strategy store write failed: %s", exc)
            return None

    # ── Internal: Neural Brain ────────────────────────────────────────────────

    def _feed_brain(
        self,
        task: ImprovementTask,
        outcome: str,
        score: float,
    ) -> dict[str, Any]:
        brain = self._get_brain()
        if brain is None:
            return {"learned": False, "reward": 0.0}

        reward = self._score_to_reward(score)

        try:
            # Delayed import: TaskNode lives in core.contracts which may not be
            # available at module-load time in all deployment configurations.
            from core.contracts import TaskNode
            synthetic_task = TaskNode(
                task_id=task.task_id,
                skill="self_improvement_loop",
                input={"goal": task.description, "target_area": task.target_area},
                status="success" if score >= 0.6 else "failed",
                output={"outcome": outcome, "score": score},
                error=task.error,
            )
            result = brain.learn_from_task(
                goal=f"self_improve:{task.description}",
                task=synthetic_task,
            )
            return result
        except Exception as exc:
            _log.debug("Brain feedback failed: %s", exc)
            return {"learned": False, "reward": reward}

    # ── Internal: Intelligence ────────────────────────────────────────────────

    def _update_intelligence(
        self,
        task: ImprovementTask,
        outcome: str,
        score: float,
    ) -> bool:
        intel = self._get_intelligence()
        if intel is None:
            return False
        try:
            reward = (score * 2) - 1.0
            intel.on_exchange(
                user_id="system:self_improvement",
                user_msg=f"Improve: {task.description}",
                agent_response=f"Outcome: {outcome} (score={score:.2f})",
                agent_id="self_improvement_loop",
                mode="power",
                reward=reward,
            )
            return True
        except Exception as exc:
            _log.debug("Intelligence update failed: %s", exc)
            return False
