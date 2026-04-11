"""Execution permission and contract validation policy."""
from __future__ import annotations

import threading
from typing import Any


class SecurityPolicy:
    """Applies strict checks before infrastructure actions run."""

    def validate_payload(self, payload: Any) -> None:
        if not isinstance(payload, dict):
            raise ValueError("payload must be a JSON object")

    def ensure_action_allowed(
        self,
        *,
        action: str,
        allowed_actions: list[str],
        skill_name: str,
    ) -> None:
        if action not in allowed_actions:
            raise PermissionError(
                f"action '{action}' is not allowed for skill '{skill_name}'"
            )

    def validate_task_input(self, data: Any, required_keys: list[str]) -> None:
        self.validate_payload(data)
        missing = [key for key in required_keys if key not in data]
        if missing:
            raise ValueError(f"missing required input fields: {missing}")


_instance: SecurityPolicy | None = None
_instance_lock = threading.Lock()


def get_security_policy() -> SecurityPolicy:
    global _instance
    with _instance_lock:
        if _instance is None:
            _instance = SecurityPolicy()
    return _instance
