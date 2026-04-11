"""ActionBus — unified action emission with audit trail and approval gating.

Every side-effecting agent action should flow through the ActionBus so that:
  - All actions are recorded in the ChangeLog.
  - In MANUAL mode, actions wait for human approval before executing.
  - Dry-run mode returns what *would* happen without any side effects.

Dependencies are injected via constructor to avoid upward layer violations.
Default callables fall back to the core singletons when not provided.

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

# Type aliases for injected dependencies
_ModeChecker = Callable[[], bool]
_AuditFunc = Callable[[str, str, str, Any, Any, str], None]


class ActionBus:
    """Central hub for agent action emission.

    Dependencies are explicit and injectable:
      - ``mode_checker``  — returns True when manual approval is required.
      - ``audit_func``    — records each action to the audit trail.

    When not provided, defaults fall back to the core singletons via lazy
    import so that out-of-the-box usage remains unchanged.
    """

    def __init__(
        self,
        *,
        mode_checker: _ModeChecker | None = None,
        audit_func: _AuditFunc | None = None,
    ) -> None:
        self._lock = threading.Lock()
        self._dry_run = False
        self._mode_checker: _ModeChecker | None = mode_checker
        self._audit_func: _AuditFunc | None = audit_func
        # Pending approvals: action_id -> record dict
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
    # Injected-dependency helpers (no upward layer imports)
    # ------------------------------------------------------------------

    def _get_requires_approval(self) -> bool:
        """Resolve whether manual approval is needed."""
        if self._mode_checker is not None:
            try:
                return self._mode_checker()
            except Exception:
                return False
        # Default: lazy fallback to core singleton (preserves existing behaviour)
        try:
            from core.mode_manager import get_mode_manager
            return get_mode_manager().is_manual()
        except Exception:
            return False

    def _record_audit(
        self,
        actor: str,
        action_type: str,
        reason: str,
        before: Any,
        after: Any,
        outcome: str,
    ) -> None:
        """Write an audit record via the injected function or core fallback."""
        if self._audit_func is not None:
            try:
                self._audit_func(actor, action_type, reason, before, after, outcome)
            except Exception:
                pass
            return
        # Default: lazy fallback to core singleton (preserves existing behaviour)
        try:
            from core.change_log import get_changelog
            get_changelog().record(
                actor=actor,
                action_type=action_type,
                reason=reason,
                before=before,
                after=after,
                outcome=outcome,
            )
        except Exception:
            pass

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

        requires_approval = self._get_requires_approval()

        self._record_audit(
            actor,
            action_type,
            reason,
            None,
            payload,
            "pending" if requires_approval else "queued",
        )

        if self.dry_run:
            return {
                "action_id": action_id,
                "status": "dry_run",
                "action_type": action_type,
                "payload": payload,
                "result": None,
            }

        if requires_approval:
            record: dict = {
                "action_id": action_id,
                "action_type": action_type,
                "payload": payload,
                "actor": actor,
                "reason": reason,
                "idempotency_key": idempotency_key,
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "status": "pending",
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
        """Return all actions awaiting approval.

        Internal fields (prefixed with ``_``) such as ``_executor``,
        ``_approved``, and ``_event`` are stripped from the output — they
        are implementation details of the approval workflow and must never
        be exposed to callers.
        """
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
                        idempotency_key=record.get("idempotency_key"),
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

        self._record_audit(
            "approval_workflow",
            record["action_type"],
            "Approved by user",
            {"status": "pending"},
            record["payload"],
            "approved",
        )

        return {"status": "approved", "action_id": action_id, "result": result}

    def reject(self, action_id: str) -> dict:
        """Reject a pending action."""
        with self._pending_lock:
            record = self._pending.pop(action_id, None)
        if record is None:
            return {"status": "not_found", "action_id": action_id}

        self._record_audit(
            "approval_workflow",
            record["action_type"],
            "Rejected by user",
            {"status": "pending"},
            None,
            "rejected",
        )

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
