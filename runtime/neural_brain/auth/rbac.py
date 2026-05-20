"""Role-Based Access Control — ADMIN > DEV > USER hierarchy."""
from __future__ import annotations

from enum import IntEnum


class Role(IntEnum):
    USER = 0
    DEV = 1
    ADMIN = 2


ROLE_NAMES: dict[str, Role] = {
    "user": Role.USER,
    "dev": Role.DEV,
    "admin": Role.ADMIN,
}


def parse_role(name: str) -> Role:
    return ROLE_NAMES.get((name or "").lower(), Role.USER)


def require_role(user_role: str, minimum: Role) -> bool:
    return parse_role(user_role) >= minimum


# Permission definitions — each permission maps to minimum required role
PERMISSIONS: dict[str, Role] = {
    # User-level
    "think": Role.USER,
    "recall": Role.USER,
    "remember": Role.USER,
    "forget": Role.USER,
    "chat": Role.USER,
    # Dev-level
    "forge:submit": Role.DEV,
    "forge:approve": Role.DEV,
    "forge:reject": Role.DEV,
    "models:route": Role.DEV,
    "debug:inspect": Role.DEV,
    "agents:view": Role.DEV,
    # Admin-level
    "admin:users": Role.ADMIN,
    "admin:roles": Role.ADMIN,
    "admin:block": Role.ADMIN,
    "admin:override": Role.ADMIN,
    "admin:telemetry": Role.ADMIN,
    "security:status": Role.ADMIN,
    "security:lockdown": Role.ADMIN,
    "key:rotate": Role.ADMIN,
    "agents:restart": Role.ADMIN,
    "memory:clear": Role.ADMIN,
}


def has_permission(user_role: str, permission: str) -> bool:
    required = PERMISSIONS.get(permission, Role.ADMIN)
    return parse_role(user_role) >= required


def check_permission(user_role: str, permission: str) -> None:
    """Raises PermissionError if insufficient role."""
    if not has_permission(user_role, permission):
        required = PERMISSIONS.get(permission, Role.ADMIN)
        raise PermissionError(
            f"Role '{user_role}' cannot '{permission}' — requires '{required.name}'"
        )
