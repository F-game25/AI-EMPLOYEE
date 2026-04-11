"""Application-layer task validator."""
from __future__ import annotations

from core.contracts import TaskNode, ValidationResult


class Validator:
    """Validates task outputs with binary and scored results."""

    def validate(self, task: TaskNode) -> ValidationResult:
        if task.status != "success":
            return ValidationResult(
                task_id=task.task_id,
                passed=False,
                score=0.0,
                details={"reason": task.error or "task execution failed"},
            )
        score = self._score_output(task)
        return ValidationResult(
            task_id=task.task_id,
            passed=score >= 0.5,
            score=score,
            details={"attempts": task.attempts},
        )

    def _score_output(self, task: TaskNode) -> float:
        score = 0.5
        if task.expected_output:
            matched = 0
            for key in task.expected_output:
                if key in task.output:
                    matched += 1
            score += 0.3 * (matched / max(len(task.expected_output), 1))
        score -= 0.1 * max(0, task.attempts - 1)
        return round(max(0.0, min(score, 1.0)), 3)
