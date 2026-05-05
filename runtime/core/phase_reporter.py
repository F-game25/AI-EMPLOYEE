"""Phase Reporter — HTTP callback utility for real-time pipeline tracking.

PhaseReporter sends phase transition updates to the Node backend
(/api/execution/phase-update) with retry logic and graceful degradation.

Usage:
    from core.phase_reporter import PhaseReporter

    reporter = PhaseReporter(
        backend_url="http://localhost:8787",
        task_id="task-123",
        tenant_id="default"
    )
    reporter.report_phase(
        phase_num=1,
        phase_name="retrieve_relevant_nodes",
        status="done",
        duration_ms=1250,
        output={"nodes": [...]}
    )
"""

import asyncio
import json
import logging
import time
import urllib.error
import urllib.request
from typing import Any, Optional

logger = logging.getLogger("phase_reporter")

# Phase name constants (must match backend enum exactly)
PHASE_NAMES = [
    "retrieve_relevant_nodes",
    "build_context",
    "classify_decision",
    "call_llm",
    "validate_tasks",
    "execute_tasks",
    "format_response",
    "update_graph",
    "monitor_and_improve",
    "validate_pipeline_integrity",
]


class PhaseReporter:
    """Report pipeline phase transitions to backend via HTTP POST."""

    def __init__(
        self,
        backend_url: str,
        task_id: str,
        tenant_id: str = "default",
    ) -> None:
        """Initialize phase reporter.

        Args:
            backend_url: Base URL of Node backend (e.g., "http://localhost:8787")
            task_id: Unique task identifier
            tenant_id: Tenant identifier (for multi-tenancy)
        """
        self.backend_url = backend_url.rstrip("/")
        self.task_id = task_id
        self.tenant_id = tenant_id
        self.endpoint = f"{self.backend_url}/api/execution/phase-update"
        self._backend_unavailable = False
        self._warned_unavailable = False

    def report_phase(
        self,
        phase_num: int,
        phase_name: str,
        status: str,
        duration_ms: float = 0,
        input: Optional[Any] = None,
        output: Optional[Any] = None,
        error: Optional[str] = None,
    ) -> bool:
        """Report a phase transition to the backend.

        Args:
            phase_num: Phase number (1-10)
            phase_name: Phase name (must match PHASE_NAMES)
            status: One of "running", "done", "failed"
            duration_ms: Execution time in milliseconds
            input: Input data (optional)
            output: Output data (optional)
            error: Error message if status="failed" (optional)

        Returns:
            True if report was sent successfully, False otherwise
        """
        if not self._validate_phase(phase_num, phase_name):
            return False

        if self._backend_unavailable:
            return False

        payload = {
            "taskId": self.task_id,
            "tenantId": self.tenant_id,
            "phase": phase_num,
            "phaseName": phase_name,
            "status": status,
            "duration_ms": duration_ms,
            "timestamp": time.time(),
        }

        if input is not None:
            payload["input"] = input
        if output is not None:
            payload["output"] = output
        if error is not None:
            payload["error"] = error

        return self._send_with_retry(payload)

    def _validate_phase(self, phase_num: int, phase_name: str) -> bool:
        """Validate phase number and name."""
        if not (1 <= phase_num <= 10):
            logger.warning(
                "Invalid phase_num=%d (must be 1-10); taskId=%s",
                phase_num,
                self.task_id,
            )
            return False

        expected_name = PHASE_NAMES[phase_num - 1]
        if phase_name != expected_name:
            logger.warning(
                "Phase name mismatch at phase=%d; got %r, expected %r; taskId=%s",
                phase_num,
                phase_name,
                expected_name,
                self.task_id,
            )
            return False

        return True

    def _send_with_retry(
        self,
        payload: dict[str, Any],
        max_attempts: int = 3,
        backoff_s: float = 1.0,
    ) -> bool:
        """Send HTTP POST with exponential backoff retry.

        Args:
            payload: JSON payload to POST
            max_attempts: Max number of attempts
            backoff_s: Initial backoff in seconds

        Returns:
            True if successful, False on failure
        """
        last_error = ""

        for attempt in range(1, max_attempts + 1):
            try:
                data = json.dumps(payload).encode("utf-8")
                req = urllib.request.Request(
                    self.endpoint,
                    data=data,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                req.add_header("User-Agent", "PhaseReporter/1.0")

                with urllib.request.urlopen(req, timeout=5) as resp:
                    if resp.status in (200, 201):
                        self._backend_unavailable = False
                        self._warned_unavailable = False
                        return True
                    else:
                        last_error = f"HTTP {resp.status}"

            except urllib.error.HTTPError as e:
                last_error = f"HTTP {e.code}: {e.reason}"
                if e.code >= 500:
                    # Server error — retry
                    pass
                else:
                    # Client error (4xx) — don't retry
                    return False

            except urllib.error.URLError as e:
                last_error = f"Connection error: {e.reason}"
                # Connection error — retry

            except Exception as e:  # noqa: BLE001
                last_error = f"Unexpected error: {e}"

            if attempt < max_attempts:
                time.sleep(backoff_s)
                backoff_s *= 2

        # All retries exhausted
        self._backend_unavailable = True
        if not self._warned_unavailable:
            logger.warning(
                "Phase reporter backend unavailable (endpoint=%s); "
                "falling back to local-only tracking; taskId=%s; last_error=%s",
                self.endpoint,
                self.task_id,
                last_error,
            )
            self._warned_unavailable = True

        return False
