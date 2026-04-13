"""Autonomy Daemon — always-on background intelligence loop.

Runs an async loop that continuously:
  1. Checks the improvement queue.
  2. Pulls the next eligible task.
  3. Sends it through the ImprovementController pipeline.
  4. Emits telemetry + WebSocket-friendly events.

The loop behaviour depends on the global ``SystemMode``:
  OFF  — idle, no processing, only monitoring.
  ON   — process high-priority (low-risk) tasks only.
  AUTO — process all queued tasks continuously.

Thread-safe start/stop with graceful shutdown.

Usage::

    from core.autonomy_daemon import get_daemon

    daemon = get_daemon()
    daemon.start()           # launches the background loop
    daemon.stop()            # graceful shutdown
    print(daemon.status())   # live status dict
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any

from core.system_mode import get_system_mode
from core.self_improvement.queue import get_queue
from core.self_improvement.controller import get_controller
from core.self_improvement.telemetry import get_telemetry
from core.self_improvement.contracts import TERMINAL_STATES

_log = logging.getLogger(__name__)

_CYCLE_SLEEP_S = 2.0        # seconds between queue polls
_MAX_CONSECUTIVE_ERRORS = 5  # back off after repeated failures
_BACKOFF_SLEEP_S = 10.0      # extended sleep after error burst


class AutonomyDaemon:
    """Background loop that continuously processes the improvement queue."""

    def __init__(self) -> None:
        self._system_mode = get_system_mode()
        self._queue = get_queue()
        self._controller = get_controller()
        self._telemetry = get_telemetry()

        self._thread: threading.Thread | None = None
        self._running = False
        self._lock = threading.Lock()

        # Live counters
        self._cycles = 0
        self._tasks_processed = 0
        self._tasks_succeeded = 0
        self._tasks_failed = 0
        self._consecutive_errors = 0
        self._last_cycle_at: str | None = None
        self._last_task_id: str | None = None
        self._current_task_id: str | None = None
        self._started_at: str | None = None

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def start(self) -> None:
        """Start the daemon loop in a background thread."""
        with self._lock:
            if self._running:
                return
            self._running = True
            self._started_at = _now()
            self._thread = threading.Thread(
                target=self._loop, name="autonomy-daemon", daemon=True
            )
            self._thread.start()
            _log.info("Autonomy daemon started")
            self._telemetry.record_event(
                "daemon_started", mode=self._system_mode.current_mode
            )

    def stop(self) -> None:
        """Gracefully stop the daemon loop."""
        with self._lock:
            if not self._running:
                return
            self._running = False
        if self._thread:
            self._thread.join(timeout=_CYCLE_SLEEP_S + 2)
            self._thread = None
        _log.info("Autonomy daemon stopped")
        self._telemetry.record_event("daemon_stopped")

    @property
    def running(self) -> bool:
        with self._lock:
            return self._running

    # ── Main loop ─────────────────────────────────────────────────────────────

    def _loop(self) -> None:
        while self._running:
            try:
                self._cycles += 1
                self._last_cycle_at = _now()

                mode = self._system_mode.current_mode

                if mode == "OFF":
                    # Idle — sleep and continue
                    time.sleep(_CYCLE_SLEEP_S)
                    continue

                # Check for queued tasks
                task = self._queue.peek()
                if task is None:
                    # Nothing in queue
                    time.sleep(_CYCLE_SLEEP_S)
                    continue

                # Mode gating
                if mode == "ON" and task.risk_class not in ("low",):
                    # ON mode: only low-risk tasks
                    time.sleep(_CYCLE_SLEEP_S)
                    continue

                # AUTO mode: process everything
                # ON mode: process low-risk only (already filtered above)

                # Check area lock
                if not self._queue.can_run_for_area(task.target_area):
                    time.sleep(_CYCLE_SLEEP_S)
                    continue

                # ── Execute pipeline ──────────────────────────────────────
                self._current_task_id = task.task_id
                self._telemetry.record_event(
                    "daemon_processing",
                    task_id=task.task_id,
                    mode=mode,
                )

                result = self._controller.run_pipeline(task)
                self._queue.update(result)

                self._tasks_processed += 1
                self._last_task_id = task.task_id
                self._current_task_id = None

                if result.status in ("deployed", "approved"):
                    self._tasks_succeeded += 1
                    self._consecutive_errors = 0
                else:
                    self._tasks_failed += 1

                self._telemetry.record_event(
                    "daemon_task_done",
                    task_id=task.task_id,
                    status=result.status,
                    mode=mode,
                )

            except Exception as exc:
                self._consecutive_errors += 1
                self._current_task_id = None
                _log.warning(
                    "Autonomy daemon cycle error (%d/%d): %s",
                    self._consecutive_errors,
                    _MAX_CONSECUTIVE_ERRORS,
                    exc,
                )
                self._telemetry.record_event(
                    "daemon_error", error=str(exc)
                )

                if self._consecutive_errors >= _MAX_CONSECUTIVE_ERRORS:
                    _log.error(
                        "Autonomy daemon backing off after %d consecutive errors",
                        self._consecutive_errors,
                    )
                    time.sleep(_BACKOFF_SLEEP_S)
                    self._consecutive_errors = 0

            # Normal cycle sleep
            time.sleep(_CYCLE_SLEEP_S)

    # ── Status ────────────────────────────────────────────────────────────────

    def status(self) -> dict[str, Any]:
        """Return a live snapshot for the UI / API."""
        mode_status = self._system_mode.status()
        queue_summary = self._queue.summary()
        return {
            "daemon": {
                "running": self._running,
                "started_at": self._started_at,
                "cycles": self._cycles,
                "tasks_processed": self._tasks_processed,
                "tasks_succeeded": self._tasks_succeeded,
                "tasks_failed": self._tasks_failed,
                "consecutive_errors": self._consecutive_errors,
                "last_cycle_at": self._last_cycle_at,
                "last_task_id": self._last_task_id,
                "current_task_id": self._current_task_id,
                "cycle_interval_s": _CYCLE_SLEEP_S,
            },
            "mode": mode_status,
            "queue": queue_summary,
        }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# ── Singleton ─────────────────────────────────────────────────────────────────

_instance: AutonomyDaemon | None = None
_instance_lock = threading.Lock()


def get_daemon() -> AutonomyDaemon:
    """Return the process-wide AutonomyDaemon singleton."""
    global _instance
    with _instance_lock:
        if _instance is None:
            _instance = AutonomyDaemon()
    return _instance
