"""Task engine compatibility facade backed by the central AgentController."""
from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.agent_controller import AgentController
from core.contracts import TaskNode
from core.task_log_store import TaskLogStore


@dataclass
class TaskSpec:
    """Legacy task spec preserved for backward compatibility."""

    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    skill: str = ""
    inputs: dict = field(default_factory=dict)
    expected_outputs: dict = field(default_factory=dict)
    timeout_s: int = 60
    max_retries: int = 3
    retry_backoff_s: float = 2.0
    actual_output: Any = None
    attempts: int = 0
    success: bool = False
    score: float = 0.0
    error: str = ""
    started_at: str = ""
    finished_at: str = ""


class TaskEngine:
    """Planner → TaskGraph → Executor → Skill → Action → Validator pipeline."""

    def __init__(self, db_path: Path | None = None) -> None:
        default = Path.home() / ".ai-employee" / "task_log.db"
        self._store = TaskLogStore(db_path or default)
        self._controller = AgentController()

    def _classify_goal(self, goal: str) -> str:
        return self._controller.planner.classify_goal(goal)

    def plan(self, goal: str) -> list[TaskSpec]:
        run_id = str(uuid.uuid4())[:8]
        graph = self._controller.build_task_graph(goal=goal, run_id=run_id)
        return [self._to_spec(task) for task in graph.tasks]

    def execute(self, task: TaskSpec) -> TaskSpec:
        node = self._to_node(task)
        result = self._controller.executor.execute_task(node)
        return self._apply_node(spec=task, node=result)

    def validate(self, task: TaskSpec) -> float:
        node = self._to_node(task)
        verdict = self._controller.validator.validate(node)
        task.score = verdict.score
        task.success = verdict.passed
        return verdict.score

    def run_goal(self, goal: str) -> dict:
        summary = self._controller.run_goal(goal, persist_task=self._store.log_task)
        return {
            "run_id": summary["run_id"],
            "goal": summary["goal"],
            "tasks": [
                {
                    "task_id": item["task_id"],
                    "skill": item["skill"],
                    "success": item["success"],
                    "attempts": item["attempts"],
                    "score": item["score"],
                    "error": "Task failed" if item.get("error") else "",
                }
                for item in summary["tasks"]
            ],
            "performance_score": summary["performance_score"],
            "success_rate": summary["success_rate"],
        }

    def recent_runs(self, *, limit: int = 20) -> list[dict]:
        return self._store.recent_runs(limit=limit)

    def daily_stats(self) -> dict:
        return self._store.daily_stats()

    def top_skills(self, *, limit: int = 5) -> list[dict]:
        return self._store.top_skills(limit=limit)

    def _to_spec(self, task: TaskNode) -> TaskSpec:
        return TaskSpec(
            id=task.task_id,
            skill=task.skill,
            inputs=task.input,
            expected_outputs=task.expected_output,
            actual_output=task.output,
            attempts=task.attempts,
            success=task.status == "success",
            score=task.score,
            error=task.error,
            started_at=task.started_at,
            finished_at=task.finished_at,
        )

    def _to_node(self, task: TaskSpec) -> TaskNode:
        return TaskNode(
            task_id=task.id,
            skill=task.skill,
            input=task.inputs,
            expected_output=task.expected_outputs,
            status="success" if task.success else "pending",
            output=task.actual_output if isinstance(task.actual_output, dict) else {},
            error=task.error,
            attempts=task.attempts,
            score=task.score,
            started_at=task.started_at,
            finished_at=task.finished_at,
        )

    def _apply_node(self, *, spec: TaskSpec, node: TaskNode) -> TaskSpec:
        spec.id = node.task_id
        spec.skill = node.skill
        spec.actual_output = node.output
        spec.attempts = node.attempts
        spec.success = node.status == "success"
        spec.error = node.error
        spec.started_at = node.started_at
        spec.finished_at = node.finished_at
        return spec


_instance: TaskEngine | None = None
_instance_lock = threading.Lock()


def get_task_engine(db_path: Path | None = None) -> TaskEngine:
    global _instance
    with _instance_lock:
        if _instance is None:
            _instance = TaskEngine(db_path)
    return _instance
