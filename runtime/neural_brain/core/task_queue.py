"""Neural Brain Task Queue — priority queue with concurrency, cancellation, tracking.

Neural Brain is the ONLY caller. Agents, Forge, and Memory never enqueue directly.

Features:
- Priority levels: CRITICAL=0, HIGH=1, NORMAL=2, LOW=3
- Configurable concurrency limit (default 8)
- Per-task timeout + cancellation
- Retry with exponential backoff (max 3 attempts)
- Full lifecycle tracking in-memory + event bus
- system:error emitted on unrecoverable failure
"""
from __future__ import annotations

import heapq
import logging
import threading
import time
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Callable

logger = logging.getLogger(__name__)


class Priority(IntEnum):
    CRITICAL = 0
    HIGH = 1
    NORMAL = 2
    LOW = 3


class TaskStatus:
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    RETRYING = "retrying"


@dataclass
class Task:
    fn: Callable
    args: tuple = field(default_factory=tuple)
    kwargs: dict = field(default_factory=dict)
    priority: Priority = Priority.NORMAL
    timeout_s: float = 60.0
    max_retries: int = 3
    task_id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    trace_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    source: str = "neural_brain"
    label: str = ""
    created_at: float = field(default_factory=time.time)
    status: str = field(default=TaskStatus.PENDING)
    attempts: int = 0
    result: Any = None
    error: str = ""
    started_at: float = 0.0
    finished_at: float = 0.0

    def __lt__(self, other: "Task") -> bool:
        return (self.priority, self.created_at) < (other.priority, other.created_at)

    def as_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "label": self.label,
            "source": self.source,
            "priority": int(self.priority),
            "status": self.status,
            "attempts": self.attempts,
            "error": self.error,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }


class TaskQueue:
    """Thread-safe priority task queue with executor pool."""

    def __init__(self, max_workers: int = 8, max_queue_size: int = 500) -> None:
        self._lock = threading.RLock()
        self._heap: list[Task] = []
        self._tasks: dict[str, Task] = {}
        self._cancelled: set[str] = set()
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="nb_task")
        self._futures: dict[str, Future] = {}
        self._running_count = 0
        self._max_workers = max_workers
        self._max_queue_size = max_queue_size
        self._dispatcher_thread = threading.Thread(
            target=self._dispatch_loop, daemon=True, name="nb_task_dispatcher"
        )
        self._dispatcher_thread.start()

    # ── Enqueue ──────────────────────────────────────────────────────────

    def enqueue(
        self,
        fn: Callable,
        *,
        args: tuple = (),
        kwargs: dict | None = None,
        priority: Priority = Priority.NORMAL,
        timeout_s: float = 60.0,
        max_retries: int = 3,
        label: str = "",
        source: str = "neural_brain",
        trace_id: str | None = None,
    ) -> str:
        """Add a task to the queue. Returns task_id."""
        with self._lock:
            if len(self._heap) >= self._max_queue_size:
                raise RuntimeError(f"TaskQueue full ({self._max_queue_size} tasks)")
            task = Task(
                fn=fn,
                args=args,
                kwargs=kwargs or {},
                priority=priority,
                timeout_s=timeout_s,
                max_retries=max_retries,
                label=label,
                source=source,
                trace_id=trace_id or str(uuid.uuid4()),
            )
            heapq.heappush(self._heap, task)
            self._tasks[task.task_id] = task

        self._emit("system:task_queued", task)
        return task.task_id

    # ── Cancel ───────────────────────────────────────────────────────────

    def cancel(self, task_id: str) -> bool:
        with self._lock:
            self._cancelled.add(task_id)
            task = self._tasks.get(task_id)
            if task and task.status == TaskStatus.PENDING:
                task.status = TaskStatus.CANCELLED
                return True
            future = self._futures.get(task_id)
            if future:
                future.cancel()
        return False

    def cancel_all(self) -> int:
        with self._lock:
            cancelled = 0
            for task in list(self._heap):
                if task.status == TaskStatus.PENDING:
                    task.status = TaskStatus.CANCELLED
                    self._cancelled.add(task.task_id)
                    cancelled += 1
            for task_id, future in list(self._futures.items()):
                future.cancel()
                cancelled += 1
        return cancelled

    # ── Status ───────────────────────────────────────────────────────────

    def get_task(self, task_id: str) -> dict | None:
        task = self._tasks.get(task_id)
        return task.as_dict() if task else None

    def list_tasks(self, status: str | None = None) -> list[dict]:
        with self._lock:
            tasks = list(self._tasks.values())
        if status:
            tasks = [t for t in tasks if t.status == status]
        return [t.as_dict() for t in sorted(tasks, key=lambda t: t.created_at, reverse=True)[:100]]

    def stats(self) -> dict:
        with self._lock:
            return {
                "queued": len(self._heap),
                "running": self._running_count,
                "total_tracked": len(self._tasks),
                "max_workers": self._max_workers,
            }

    # ── Dispatch loop ─────────────────────────────────────────────────────

    def _dispatch_loop(self) -> None:
        while True:
            time.sleep(0.05)  # 50ms polling cycle
            with self._lock:
                if not self._heap or self._running_count >= self._max_workers:
                    continue
                task = heapq.heappop(self._heap)
                if task.task_id in self._cancelled or task.status == TaskStatus.CANCELLED:
                    continue
                task.status = TaskStatus.RUNNING
                task.started_at = time.time()
                self._running_count += 1

            future = self._executor.submit(self._run_task, task)
            with self._lock:
                self._futures[task.task_id] = future

    def _run_task(self, task: Task) -> None:
        import concurrent.futures
        task.attempts += 1
        backoff = 0.5
        last_error = ""

        for attempt in range(1, task.max_retries + 1):
            if task.task_id in self._cancelled:
                task.status = TaskStatus.CANCELLED
                break
            try:
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
                    f = ex.submit(task.fn, *task.args, **task.kwargs)
                    task.result = f.result(timeout=task.timeout_s)
                task.status = TaskStatus.COMPLETED
                task.finished_at = time.time()
                self._emit("system:task_completed", task)
                break
            except Exception as e:
                last_error = str(e)
                if attempt < task.max_retries:
                    task.status = TaskStatus.RETRYING
                    self._emit("system:task_retrying", task, extra={"attempt": attempt, "error": last_error})
                    time.sleep(backoff * (2 ** (attempt - 1)))
                else:
                    task.status = TaskStatus.FAILED
                    task.error = last_error
                    task.finished_at = time.time()
                    self._emit("system:error", task, extra={"error": last_error})
                    logger.error("Task %s failed after %d attempts: %s", task.task_id, attempt, last_error)

        with self._lock:
            self._running_count = max(0, self._running_count - 1)
            self._futures.pop(task.task_id, None)

    # ── Event helpers ─────────────────────────────────────────────────────

    def _emit(self, event_type: str, task: Task, extra: dict | None = None) -> None:
        try:
            from neural_brain.utils.event_bus import publish
            publish(event_type, source="system", payload={**task.as_dict(), **(extra or {})}, trace_id=task.trace_id)
        except Exception:
            pass


# ── Singleton ─────────────────────────────────────────────────────────────────

_queue_instance: TaskQueue | None = None
_queue_lock = threading.Lock()


def get_task_queue(max_workers: int = 8) -> TaskQueue:
    global _queue_instance
    if _queue_instance is None:
        with _queue_lock:
            if _queue_instance is None:
                _queue_instance = TaskQueue(max_workers=max_workers)
    return _queue_instance
