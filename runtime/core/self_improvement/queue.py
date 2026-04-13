"""Persistent FIFO task queue for the self-improvement loop.

Stores tasks as JSON in ``~/.ai-employee/state/improvement_queue.json``.
Thread-safe with file-level locking for single-process safety.
"""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any

from core.self_improvement.contracts import (
    TERMINAL_STATES,
    ImprovementPlan,
    ImprovementTask,
    PatchArtifact,
    RiskLevel,
    TestResult,
)

_AI_HOME = Path(os.environ.get("AI_HOME", str(Path.home() / ".ai-employee")))
_QUEUE_FILE = _AI_HOME / "state" / "improvement_queue.json"
_MAX_PARALLEL = 3
_MAX_QUEUE_DEPTH = 50


class ImprovementQueue:
    """File-backed FIFO for improvement tasks with per-area locking."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or _QUEUE_FILE
        self._lock = threading.Lock()
        self._area_locks: dict[str, threading.Lock] = {}
        self._path.parent.mkdir(parents=True, exist_ok=True)

    # ── Persistence ───────────────────────────────────────────────────────────

    def _read(self) -> list[dict]:
        try:
            return json.loads(self._path.read_text(encoding="utf-8"))
        except Exception:
            return []

    def _write(self, data: list[dict]) -> None:
        self._path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    # ── Public API ────────────────────────────────────────────────────────────

    def enqueue(
        self,
        *,
        description: str,
        target_area: str = "general",
        constraints: list[str] | None = None,
        risk_class: RiskLevel = "medium",
        owner: str = "system",
        approval_policy: str = "manual",
    ) -> ImprovementTask:
        """Add a new improvement task to the queue. Returns the task."""
        task = ImprovementTask(
            description=description,
            target_area=target_area,
            constraints=constraints or [],
            risk_class=risk_class,
            owner=owner,
            approval_policy=approval_policy,
        )
        with self._lock:
            data = self._read()
            if len(data) >= _MAX_QUEUE_DEPTH:
                raise RuntimeError(
                    f"Queue full ({_MAX_QUEUE_DEPTH} tasks). "
                    "Complete or remove existing tasks first."
                )
            data.append(task.to_dict())
            self._write(data)
        return task

    def peek(self) -> ImprovementTask | None:
        """Return the first non-terminal task without removing it."""
        with self._lock:
            data = self._read()
        for item in data:
            if item.get("status") not in TERMINAL_STATES:
                return self._dict_to_task(item)
        return None

    def get(self, task_id: str) -> ImprovementTask | None:
        """Return a specific task by ID."""
        with self._lock:
            data = self._read()
        for item in data:
            if item.get("task_id") == task_id:
                return self._dict_to_task(item)
        return None

    def update(self, task: ImprovementTask) -> None:
        """Persist updated task state back to the queue."""
        with self._lock:
            data = self._read()
            for i, item in enumerate(data):
                if item.get("task_id") == task.task_id:
                    data[i] = task.to_dict()
                    break
            else:
                data.append(task.to_dict())
            self._write(data)

    def list_all(self, *, status: str | None = None) -> list[dict]:
        """Return all tasks, optionally filtered by status."""
        with self._lock:
            data = self._read()
        if status:
            data = [d for d in data if d.get("status") == status]
        return data

    def active_count(self) -> int:
        """Return the number of non-terminal tasks."""
        with self._lock:
            data = self._read()
        return sum(1 for d in data if d.get("status") not in TERMINAL_STATES)

    def can_run_for_area(self, area: str) -> bool:
        """Check if a new task can run for the given target area.

        Prevents conflicting patches by limiting one active task per area.
        """
        with self._lock:
            data = self._read()
        active_in_area = sum(
            1 for d in data
            if d.get("target_area") == area
            and d.get("status") not in TERMINAL_STATES
            and d.get("status") != "queued"
        )
        return active_in_area == 0

    def depth(self) -> int:
        """Return total number of tasks in the queue."""
        with self._lock:
            return len(self._read())

    def summary(self) -> dict[str, Any]:
        """Return a compact summary for telemetry/dashboard."""
        with self._lock:
            data = self._read()
        by_status: dict[str, int] = {}
        for d in data:
            s = d.get("status", "unknown")
            by_status[s] = by_status.get(s, 0) + 1
        return {
            "total": len(data),
            "active": sum(1 for d in data if d.get("status") not in TERMINAL_STATES),
            "by_status": by_status,
        }

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _dict_to_task(d: dict) -> ImprovementTask:
        plan_data = d.get("plan")
        patch_data = d.get("patch")
        test_data = d.get("test_result")
        return ImprovementTask(
            task_id=d.get("task_id", ""),
            description=d.get("description", ""),
            target_area=d.get("target_area", ""),
            constraints=d.get("constraints", []),
            risk_class=d.get("risk_class", "medium"),
            owner=d.get("owner", "system"),
            status=d.get("status", "queued"),
            plan=ImprovementPlan(**plan_data) if plan_data else None,
            patch=PatchArtifact(**patch_data) if patch_data else None,
            test_result=TestResult(**test_data) if test_data else None,
            approval_policy=d.get("approval_policy", "manual"),
            retry_count=d.get("retry_count", 0),
            max_retries=d.get("max_retries", 2),
            error=d.get("error", ""),
            created_at=d.get("created_at", ""),
            updated_at=d.get("updated_at", ""),
            completed_at=d.get("completed_at", ""),
            brain_strategy=d.get("brain_strategy", {}),
            learning_outcome=d.get("learning_outcome", {}),
        )


# ── Singleton ─────────────────────────────────────────────────────────────────

_instance: ImprovementQueue | None = None
_instance_lock = threading.Lock()


def get_queue(path: Path | None = None) -> ImprovementQueue:
    """Return the process-wide ImprovementQueue singleton."""
    global _instance
    with _instance_lock:
        if _instance is None:
            _instance = ImprovementQueue(path)
    return _instance
