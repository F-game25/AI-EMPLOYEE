"""Central orchestrator coordinating planner, executor, validator."""
from __future__ import annotations

import time
import uuid
import threading
from typing import Callable

from analytics.structured_logger import StructuredLogger, get_structured_logger
from core.contracts import TaskGraph, TaskNode
from core.executor import Executor
from core.planner import Planner
from core.validator import Validator
from security.policy import SecurityPolicy, get_security_policy
from skills.catalog import SkillCatalog, get_skill_catalog


class AgentController:
    """Application-layer orchestrator with deterministic data flow."""

    def __init__(
        self,
        *,
        planner: Planner | None = None,
        executor: Executor | None = None,
        validator: Validator | None = None,
        logger: StructuredLogger | None = None,
        skills: SkillCatalog | None = None,
        policy: SecurityPolicy | None = None,
    ) -> None:
        self._logger = logger or get_structured_logger()
        self._planner = planner or Planner(logger=self._logger)
        catalog = skills or get_skill_catalog()
        guard = policy or get_security_policy()
        self._executor = executor or Executor(
            skills=catalog,
            policy=guard,
            logger=self._logger,
            action_emitter=self._emit_action,
        )
        self._validator = validator or Validator(logger=self._logger)

    @property
    def planner(self) -> Planner:
        return self._planner

    @property
    def executor(self) -> Executor:
        return self._executor

    @property
    def validator(self) -> Validator:
        return self._validator

    def build_task_graph(self, *, goal: str, run_id: str) -> TaskGraph:
        best = self._best_strategies(goal)
        return self._planner.plan(goal=goal, run_id=run_id, best_strategies=best)

    def run_goal(
        self,
        goal: str,
        *,
        persist_task: Callable[[str, TaskNode], None] | None = None,
    ) -> dict:
        run_id = str(uuid.uuid4())[:8]
        start = time.perf_counter()
        graph = self.build_task_graph(goal=goal, run_id=run_id)
        tasks = self._executor.execute_graph(graph)
        for task in tasks:
            verdict = self._validator.validate(task)
            task.passed = verdict.passed
            task.score = verdict.score
            if persist_task:
                persist_task(run_id, task)
            self._feedback_loop(goal=goal, task=task)
        summary = self._build_summary(run_id=run_id, goal=goal, graph=graph)
        self._logger.log_event(
            component="controller",
            action="run_goal",
            result="success",
            latency_ms=(time.perf_counter() - start) * 1000,
            meta={"run_id": run_id, "tasks": len(tasks)},
        )
        return summary

    def _build_summary(self, *, run_id: str, goal: str, graph: TaskGraph) -> dict:
        rows = [self._task_summary(task) for task in graph.tasks]
        score = round(sum(task.score for task in graph.tasks) / max(len(graph.tasks), 1), 3)
        success = round(sum(1 for task in graph.tasks if task.status == "success") / max(len(graph.tasks), 1), 3)
        return {
            "run_id": run_id,
            "goal": goal,
            "task_graph": graph.to_contract(),
            "tasks": rows,
            "performance_score": score,
            "success_rate": success,
        }

    def _task_summary(self, task: TaskNode) -> dict:
        return {
            "task_id": task.task_id,
            "skill": task.skill,
            "status": task.status,
            "success": task.status == "success",
            "attempts": task.attempts,
            "score": round(task.score, 3),
            "error": task.error,
            "output": task.output,
        }

    def _best_strategies(self, goal: str) -> list[dict]:
        try:
            from memory.strategy_store import get_strategy_store

            goal_type = self._planner.classify_goal(goal)
            return get_strategy_store().get_best_strategy(goal_type)
        except Exception as exc:
            self._logger.log_event(
                component="controller",
                action="best_strategies",
                result="fallback",
                latency_ms=0.0,
                meta={"reason": str(exc)},
            )
            return []

    def _feedback_loop(self, *, goal: str, task: TaskNode) -> None:
        try:
            from memory.strategy_store import get_strategy_store

            goal_type = self._planner.classify_goal(goal)
            get_strategy_store().record(
                goal_type=goal_type,
                agent=task.skill,
                config=task.input,
                outcome_score=task.score,
                outcome_status="success" if task.status == "success" else "failed",
                context={
                    "task_id": task.task_id,
                    "attempts": task.attempts,
                    "started_at": task.started_at,
                    "finished_at": task.finished_at,
                },
                outcome={
                    "status": task.status,
                    "output": task.output,
                    "error": task.error,
                },
                notes=task.error or "ok",
            )
        except Exception as exc:
            self._logger.log_event(
                component="controller",
                action="feedback_loop",
                result="error",
                latency_ms=0.0,
                meta={"reason": str(exc)},
            )

    def _emit_action(self, action: str, payload: dict) -> dict:
        from actions.action_bus import get_action_bus

        action_type = f"skill:{payload.get('skill', 'unknown')}"
        bus_payload = {"task_input": payload.get("input", {}), "action": action}
        return get_action_bus().emit(
            action_type=action_type,
            payload=bus_payload,
            actor="agent_controller",
            reason="executor dispatch",
        )


_instance: AgentController | None = None
_instance_lock = threading.Lock()


def get_agent_controller() -> AgentController:
    global _instance
    with _instance_lock:
        if _instance is None:
            _instance = AgentController()
    return _instance
