"""Zero-trust security layer for the AI Employee runtime.

Every agent is untrusted by default.  Explicit permissions must be granted
before any sensitive operation can proceed.  All permission checks are logged
to the audit engine.

Permission constants
--------------------
MEMORY_WRITE       — write to any memory store
TOOL_EXECUTION     — execute external tools / shell commands
FORGE_ACCESS       — submit or approve Forge change requests
ECONOMY_ACTIONS    — trigger economy / revenue-related operations

Usage
-----
    from core.security_layer import get_security_layer, FORGE_ACCESS

    sl = get_security_layer()
    sl.grant(agent_id="analyst-1", permissions={FORGE_ACCESS})
    sl.require(agent_id="analyst-1", permission=FORGE_ACCESS, action="forge_submit")
"""
from __future__ import annotations

import re
import threading
from typing import Any

# ── permission constants ──────────────────────────────────────────────────────

MEMORY_WRITE: str = "memory_write"
TOOL_EXECUTION: str = "tool_execution"
FORGE_ACCESS: str = "forge_access"
ECONOMY_ACTIONS: str = "economy_actions"

ALL_PERMISSIONS: frozenset[str] = frozenset(
    {MEMORY_WRITE, TOOL_EXECUTION, FORGE_ACCESS, ECONOMY_ACTIONS}
)

# ── input sanitisation patterns ───────────────────────────────────────────────

# Deny strings that look like shell injection or prompt injection
_SHELL_INJECTION = re.compile(
    r"(;|\||&&|\$\(|`|>\s*/|<\s*/proc|eval\s+\$)",
    re.IGNORECASE,
)
# Deny suspiciously long single values that might be prompt-stuffing
_MAX_VALUE_LEN = 8192


class PermissionDeniedError(PermissionError):
    """Raised when an agent attempts an action without the required permission."""


class SecurityLayer:
    """Manages per-agent permissions and validates inputs before execution."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        # agent_id -> granted permissions
        self._grants: dict[str, set[str]] = {}

    # ── permission management ─────────────────────────────────────────────────

    def grant(self, agent_id: str, permissions: set[str]) -> None:
        """Grant a set of permissions to an agent."""
        unknown = permissions - ALL_PERMISSIONS
        if unknown:
            raise ValueError(f"Unknown permissions: {unknown}")
        with self._lock:
            self._grants.setdefault(agent_id, set()).update(permissions)

    def revoke(self, agent_id: str, permissions: set[str] | None = None) -> None:
        """Revoke permissions from an agent.  Pass None to revoke all."""
        with self._lock:
            if permissions is None:
                self._grants.pop(agent_id, None)
            else:
                current = self._grants.get(agent_id, set())
                current.difference_update(permissions)
                if not current:
                    self._grants.pop(agent_id, None)

    def has_permission(self, agent_id: str, permission: str) -> bool:
        with self._lock:
            return permission in self._grants.get(agent_id, set())

    def require(self, agent_id: str, permission: str, *, action: str = "") -> None:
        """Raise ``PermissionDeniedError`` if the agent lacks the permission.

        Always records the check in the audit log.
        """
        allowed = self.has_permission(agent_id, permission)
        self._audit(
            actor=agent_id,
            action=action or f"permission_check:{permission}",
            output={"granted": allowed},
            risk_score=0.0 if allowed else 0.75,
        )
        if not allowed:
            raise PermissionDeniedError(
                f"Agent '{agent_id}' does not have permission '{permission}' "
                f"required for action '{action}'"
            )

    def permissions_for(self, agent_id: str) -> frozenset[str]:
        with self._lock:
            return frozenset(self._grants.get(agent_id, set()))

    # ── input validation ──────────────────────────────────────────────────────

    def validate_input(self, payload: Any, *, required_keys: list[str] | None = None) -> None:
        """Validate that a payload is a safe dict with expected keys."""
        if not isinstance(payload, dict):
            raise ValueError("payload must be a JSON object (dict)")
        for key, value in payload.items():
            if isinstance(value, str):
                if len(value) > _MAX_VALUE_LEN:
                    raise ValueError(f"payload field '{key}' exceeds maximum length ({_MAX_VALUE_LEN})")
                if _SHELL_INJECTION.search(value):
                    raise ValueError(f"payload field '{key}' contains disallowed characters")
        if required_keys:
            missing = [k for k in required_keys if k not in payload]
            if missing:
                raise ValueError(f"payload missing required fields: {missing}")

    def validate_forge_operation(self, agent_id: str, operation: dict[str, Any]) -> None:
        """Full validation for Forge operations: permission + input safety.

        Raises ``PermissionDeniedError`` or ``ValueError`` on failure.
        """
        self.require(agent_id, FORGE_ACCESS, action="forge_submit")
        self.validate_input(operation, required_keys=["goal"])

    # ── forge sandbox check ───────────────────────────────────────────────────

    def sandbox_check(self, code_snippet: str) -> dict[str, Any]:
        """Run a lightweight static safety check on a code snippet.

        Returns a dict with ``safe`` (bool) and ``violations`` (list[str]).
        This is NOT a full sandbox execution — it is a fast pre-screen that
        must be followed by an actual isolated execution step in the Forge
        pipeline.
        """
        violations: list[str] = []
        dangerous = [
            (r"\beval\s*\(", "eval()"),
            (r"\bexec\s*\(", "exec()"),
            (r"__import__\s*\(", "__import__()"),
            (r"\bos\.system\s*\(", "os.system()"),
            (r"\bsubprocess\b", "subprocess"),
            (r"\bopen\s*\(.*['\"]w['\"]", "open() for write"),
            (r"\bshutil\.rmtree\b", "shutil.rmtree()"),
        ]
        import re as _re
        for pattern, label in dangerous:
            if _re.search(pattern, code_snippet):
                violations.append(label)
        return {"safe": len(violations) == 0, "violations": violations}

    # ── helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _audit(*, actor: str, action: str, output: dict[str, Any], risk_score: float) -> None:
        try:
            from core.audit_engine import get_audit_engine
            get_audit_engine().record(
                actor=actor,
                action=action,
                output_data=output,
                risk_score=risk_score,
            )
        except Exception:
            pass  # audit must never block execution


# ── singleton ─────────────────────────────────────────────────────────────────

_instance: SecurityLayer | None = None
_instance_lock = threading.Lock()


def get_security_layer() -> SecurityLayer:
    global _instance
    with _instance_lock:
        if _instance is None:
            _instance = SecurityLayer()
    return _instance
