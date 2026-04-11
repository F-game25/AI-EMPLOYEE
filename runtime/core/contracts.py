"""Structured data contracts for deterministic task orchestration."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


TaskStatus = Literal["pending", "running", "success", "failed"]


@dataclass
class TaskNode:
    """Deterministic task graph node."""

    task_id: str
    skill: str
    input: dict[str, Any]
    expected_output: dict[str, Any] = field(default_factory=dict)
    dependencies: list[str] = field(default_factory=list)
    allowed_actions: list[str] = field(default_factory=lambda: ["skill_dispatch"])
    status: TaskStatus = "pending"
    output: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    attempts: int = 0
    score: float = 0.0
    passed: bool = False
    started_at: str = ""
    finished_at: str = ""

    def to_contract(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "skill": self.skill,
            "input": self.input,
            "status": self.status,
            "output": self.output,
            "dependencies": self.dependencies,
            "attempts": self.attempts,
            "error": self.error,
            "score": self.score,
            "passed": self.passed,
        }


@dataclass
class TaskGraph:
    """Task graph emitted by the planner."""

    run_id: str
    goal: str
    tasks: list[TaskNode]

    def to_contract(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "goal": self.goal,
            "tasks": [task.to_contract() for task in self.tasks],
        }


@dataclass
class ValidationResult:
    """Binary + scored validation contract."""

    task_id: str
    passed: bool
    score: float
    details: dict[str, Any] = field(default_factory=dict)

    def to_contract(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "passed": self.passed,
            "score": self.score,
            "details": self.details,
        }
