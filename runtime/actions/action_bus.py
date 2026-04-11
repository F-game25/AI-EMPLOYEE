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

import logging
import threading
import time
import uuid
from typing import Any, Callable

_log = logging.getLogger(__name__)


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
        self._secure_engine = None

    def _get_or_create_secure_engine(self):
        if self._secure_engine is None:
            from actions.execution_engine import SecureExecutionEngine
            self._secure_engine = SecureExecutionEngine()
        return self._secure_engine

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
        idempotency_key: str | None = None,
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
        idempotency_key:
            Optional replay-safe key used by secure registered actions to
            deduplicate retries and return cached outcomes. Provide this when
            callers might retry the same external action request.

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
        else:
            try:
                engine = self._get_or_create_secure_engine()
                if engine.has_action(action_type):
                    secure_result = engine.execute(
                        action_name=action_type,
                        payload=payload,
                        skill=actor,
                        idempotency_key=idempotency_key,
                    )
                    if secure_result.get("status") == "executed":
                        result = secure_result.get("result")
                    elif secure_result.get("status") == "error":
                        return {
                            "action_id": action_id,
                            "status": "error",
                            "action_type": action_type,
                            "error": secure_result.get(
                                "failure", {}
                            ).get("reason", f"Execution failed for action {action_type}"),
                            "failure": secure_result.get("failure", {}),
                            "result": None,
                        }
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
            except Exception:
                _log.exception("Executor failed for approved action %s", action_id)
                return {"status": "error", "action_id": action_id, "error": "Execution failed"}
        else:
            try:
                engine = self._get_or_create_secure_engine()
                if engine.has_action(record["action_type"]):
                    secure_result = engine.execute(
                        action_name=record["action_type"],
                        payload=record["payload"],
                        skill=record.get("actor", "system"),
                    )
                    if secure_result.get("status") == "executed":
                        result = secure_result.get("result")
                    else:
                        return {
                            "status": "error",
                            "action_id": action_id,
                            "error": secure_result.get("failure", {}).get(
                                "reason",
                                f"Execution failed for action {record['action_type']}",
                            ),
                            "failure": secure_result.get("failure", {}),
                        }
            except Exception:
                _log.exception("Secure execution failed for approved action %s", action_id)
                return {"status": "error", "action_id": action_id, "error": "Execution failed"}

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

    # ------------------------------------------------------------------
    # Secure action management
    # ------------------------------------------------------------------

    def register_action(self, name: str, action: Any) -> None:
        """Register a standardized external action in the secure engine."""
        self._get_or_create_secure_engine().register_action(name, action)

    def metrics(self) -> dict:
        """Return execution metrics for registered actions."""
        try:
            return self._get_or_create_secure_engine().metrics()
        except Exception:
            return {}


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
