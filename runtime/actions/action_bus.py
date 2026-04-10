"""ActionBus — unified action emission with audit trail and approval gating.

Every side-effecting agent action should flow through the ActionBus so that:
  - All actions are recorded in the ChangeLog.
  - In MANUAL mode, actions wait for human approval before executing.
  - Dry-run mode returns what *would* happen without any side effects.

Usage::

    from actions.action_bus import get_action_bus

    bus = get_action_bus()
    result = bus.emit(
        action_type="post_content",
        payload={"platform": "twitter", "text": "Hello world"},
        actor="social_media_manager",
        reason="Scheduled post from content calendar",
    )
"""
from __future__ import annotations

import queue
import threading
import time
import uuid
from typing import Any, Callable


class ActionBus:
    """Central hub for agent action emission.

    Integration points:
      - ``get_mode_manager()`` — determines if approval is required.
      - ``get_changelog()``    — writes every emitted action.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._dry_run = False
        # Pending approvals: action_id -> (event, payload_ref)
        self._pending: dict[str, dict] = {}
        self._pending_lock = threading.Lock()

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    def set_dry_run(self, enabled: bool) -> None:
        """Enable/disable dry-run mode (no side effects when True)."""
        with self._lock:
            self._dry_run = enabled

    @property
    def dry_run(self) -> bool:
        with self._lock:
            return self._dry_run

    # ------------------------------------------------------------------
    # Core emission
    # ------------------------------------------------------------------

    def emit(
        self,
        action_type: str,
        payload: dict | None = None,
        *,
        actor: str = "system",
        reason: str = "",
        executor: Callable[[dict], Any] | None = None,
    ) -> dict:
        """Emit an action.

        Parameters
        ----------
        action_type:
            A short label describing the action (e.g. ``"post_content"``).
        payload:
            Arbitrary data the action carries.
        actor:
            Name of the agent/module emitting the action.
        reason:
            Human-readable explanation for why this action was triggered.
        executor:
            Optional callable that actually performs the action.  If *None*,
            the bus records the action but does not execute it.

        Returns a result dict with ``status``, ``action_id``, and any
        ``result`` produced by *executor*.
        """
        payload = payload or {}
        action_id = str(uuid.uuid4())[:8]

        # Resolve mode without hard import failure
        requires_approval = False
        try:
            from core.mode_manager import get_mode_manager
            requires_approval = get_mode_manager().is_manual()
        except Exception:
            pass

        # Log to change log
        try:
            from core.change_log import get_changelog
            get_changelog().record(
                actor=actor,
                action_type=action_type,
                reason=reason,
                before=None,
                after=payload,
                outcome="pending" if requires_approval else "queued",
            )
        except Exception:
            pass

        if self.dry_run:
            return {
                "action_id": action_id,
                "status": "dry_run",
                "action_type": action_type,
                "payload": payload,
                "result": None,
            }

        if requires_approval:
            event = threading.Event()
            record: dict = {
                "action_id": action_id,
                "action_type": action_type,
                "payload": payload,
                "actor": actor,
                "reason": reason,
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "status": "pending",
                "_event": event,
                "_approved": False,
                "_executor": executor,
            }
            with self._pending_lock:
                self._pending[action_id] = record
            return {
                "action_id": action_id,
                "status": "pending_approval",
                "action_type": action_type,
                "payload": payload,
                "result": None,
            }

        # Execute immediately
        result = None
        if executor:
            try:
                result = executor(payload)
            except Exception as exc:
                return {
                    "action_id": action_id,
                    "status": "error",
                    "action_type": action_type,
                    "error": str(exc),
                    "result": None,
                }

        return {
            "action_id": action_id,
            "status": "executed",
            "action_type": action_type,
            "payload": payload,
            "result": result,
        }

    # ------------------------------------------------------------------
    # Approval workflow
    # ------------------------------------------------------------------

    def list_pending(self) -> list[dict]:
        """Return all actions awaiting approval (executor removed from output)."""
        with self._pending_lock:
            return [
                {k: v for k, v in rec.items() if not k.startswith("_")}
                for rec in self._pending.values()
            ]

    def approve(self, action_id: str) -> dict:
        """Approve a pending action and execute it."""
        with self._pending_lock:
            record = self._pending.pop(action_id, None)
        if record is None:
            return {"status": "not_found", "action_id": action_id}

        executor = record.get("_executor")
        result = None
        if executor:
            try:
                result = executor(record["payload"])
            except Exception as exc:
                return {"status": "error", "action_id": action_id, "error": str(exc)}

        try:
            from core.change_log import get_changelog
            get_changelog().record(
                actor="approval_workflow",
                action_type=record["action_type"],
                reason="Approved by user",
                before={"status": "pending"},
                after=record["payload"],
                outcome="approved",
            )
        except Exception:
            pass

        return {"status": "approved", "action_id": action_id, "result": result}

    def reject(self, action_id: str) -> dict:
        """Reject a pending action."""
        with self._pending_lock:
            record = self._pending.pop(action_id, None)
        if record is None:
            return {"status": "not_found", "action_id": action_id}

        try:
            from core.change_log import get_changelog
            get_changelog().record(
                actor="approval_workflow",
                action_type=record["action_type"],
                reason="Rejected by user",
                before={"status": "pending"},
                after=None,
                outcome="rejected",
            )
        except Exception:
            pass

        return {"status": "rejected", "action_id": action_id}


# ── Singleton ─────────────────────────────────────────────────────────────────

_instance: ActionBus | None = None
_instance_lock = threading.Lock()


def get_action_bus() -> ActionBus:
    """Return the process-wide ActionBus singleton."""
    global _instance
    with _instance_lock:
        if _instance is None:
            _instance = ActionBus()
    return _instance
