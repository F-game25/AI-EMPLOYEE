"""Application-layer task validator."""
from __future__ import annotations

import time
from typing import TYPE_CHECKING

from core.contracts import TaskNode, ValidationResult

if TYPE_CHECKING:
    from analytics.structured_logger import StructuredLogger


class Validator:
    """Validates task outputs with binary and scored results."""

    def __init__(self, logger: StructuredLogger | None = None) -> None:
        self._logger = logger

    def validate(self, task: TaskNode) -> ValidationResult:
        start = time.perf_counter()
        result = self._evaluate(task)
        latency_ms = (time.perf_counter() - start) * 1000
        if self._logger is not None:
            self._logger.log_event(
                component="validator",
                action="validate",
                result="passed" if result.passed else "failed",
                latency_ms=latency_ms,
                meta={"task_id": task.task_id, "score": result.score},
            )
        return result

    def _evaluate(self, task: TaskNode) -> ValidationResult:
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
