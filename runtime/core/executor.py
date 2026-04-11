"""Application-layer executor resolving task graph dependencies."""
from __future__ import annotations

import time
from typing import Callable

from analytics.structured_logger import StructuredLogger
from core.contracts import TaskGraph, TaskNode
from security.policy import SecurityPolicy
from skills.catalog import SkillCatalog


class Executor:
    """Executes graph tasks deterministically through domain skills."""

    def __init__(
        self,
        *,
        skills: SkillCatalog,
        policy: SecurityPolicy,
        logger: StructuredLogger,
        action_emitter: Callable[[str, dict], dict],
    ) -> None:
        self._skills = skills
        self._policy = policy
        self._logger = logger
        self._action_emitter = action_emitter

    def execute_graph(self, graph: TaskGraph) -> list[TaskNode]:
        graph.validate_no_cycles()
        completed: dict[str, TaskNode] = {}
        while len(completed) < len(graph.tasks):
            progress = self._execute_ready_tasks(graph=graph, completed=completed)
            if not progress:
                self._fail_blocked_tasks(graph=graph, completed=completed)
        return graph.tasks

    def execute_task(self, task: TaskNode) -> TaskNode:
        start = time.perf_counter()
        task.started_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        result = self._try_execute(task)
        task.finished_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        latency_ms = (time.perf_counter() - start) * 1000
        self._logger.log_event(
            component="executor",
            action=f"task:{task.skill}",
            result=task.status,
            latency_ms=latency_ms,
            meta={"task_id": task.task_id, "attempts": task.attempts},
        )
        return result

    def _execute_ready_tasks(
        self,
        *,
        graph: TaskGraph,
        completed: dict[str, TaskNode],
    ) -> bool:
        progress = False
        for task in graph.tasks:
            if task.task_id in completed or task.status != "pending":
                continue
            if not self._dependencies_satisfied(task=task, completed=completed):
                continue
            completed[task.task_id] = self.execute_task(task)
            progress = True
        return progress

    def _dependencies_satisfied(self, *, task: TaskNode, completed: dict[str, TaskNode]) -> bool:
        return all(
            dep in completed and completed[dep].status == "success"
            for dep in task.dependencies
        )

    def _fail_blocked_tasks(self, *, graph: TaskGraph, completed: dict[str, TaskNode]) -> None:
        for task in graph.tasks:
            if task.task_id in completed:
                continue
            task.status = "failed"
            task.error = "blocked_dependency"
            completed[task.task_id] = task

    def _try_execute(self, task: TaskNode) -> TaskNode:
        retries = 3
        for attempt in range(1, retries + 1):
            task.attempts = attempt
            try:
                self._execute_once(task)
                task.status = "success"
                task.error = ""
                return task
            except Exception as exc:
                task.status = "failed"
                task.error = str(exc)
                if attempt < retries:
                    time.sleep(min(2 ** (attempt - 1), 4))
        return task

    def _execute_once(self, task: TaskNode) -> None:
        skill = self._skills.get(task.skill)
        if skill is None:
            skill = self._skills.get("problem-solver")
            task.skill = "problem-solver"
        if skill is None:
            raise RuntimeError("no fallback skill available")
        required_keys = list(skill.input_schema.get("required", []))
        self._policy.validate_task_input(task.input, required_keys)
        self._policy.ensure_action_allowed(
            action="skill_dispatch",
            allowed_actions=skill.allowed_actions,
            skill_name=skill.name,
        )
        task.allowed_actions = list(skill.allowed_actions)
        output = skill.execute(task.input, self._run_action)
        required_output_keys = list(skill.output_schema.get("required", []))
        self._policy.validate_output(output, required_output_keys)
        task.output = output

    def _run_action(self, action: str, payload: dict) -> dict:
        self._policy.validate_payload(payload)
        return self._action_emitter(action, payload)
