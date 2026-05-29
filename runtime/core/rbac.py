"""Role-Based Access Control — policy engine for FastAPI routes.

Permission string format: '<resource>:<action>' or '<resource>:*' (wildcard).

Wildcard resolution order:
  1. Role has '*'              → grants everything.
  2. Exact string match        → grants.
  3. Role has '<res>:*'        → grants any '<res>:<action>'.
  4. Permission is '<res>:*'   → granted if role has any '<res>:<x>'.

Usage in server.py::

    from core.rbac import require_permission

    @app.post("/api/ascend/mode")
    def ascend_set_mode(payload: dict,
                        _auth: None = Depends(require_auth),
                        _rbac=require_permission("admin:*", require_auth)):
        ...

Alternatively use the pre-wired factory after registering require_auth::

    from core.rbac import make_permission_dep
    require_admin = make_permission_dep("admin:*", require_auth)
"""

from __future__ import annotations

from typing import Any, Callable

from fastapi import Depends, HTTPException, Request, status

# ── Role → permission grants ──────────────────────────────────────────────────

ROLE_PERMISSIONS: dict[str, set[str]] = {
    "admin": {"*"},
    "operator": {
        "tasks:*",
        "agents:*",
        "research:read",
        "vault:read",
        "settings:write",
    },
    "analyst": {
        "tasks:read",
        "research:*",
        "telemetry:read",
        "vault:read",
    },
    "viewer": {
        "tasks:read",
        "agents:read",
        "telemetry:read",
    },
    "support": {
        "tasks:read",
        "agents:read",
        "vault:read",
    },
}

# ── Core permission check ─────────────────────────────────────────────────────


def has_permission(role: str, permission: str) -> bool:
    """Return True if *role* is granted *permission*.

    Args:
        role: one of admin | operator | analyst | viewer | support
        permission: e.g. "tasks:read", "vault:write", "admin:*"

    Returns:
        bool — True if the role's grant set covers the requested permission.
    """
    grants: set[str] = ROLE_PERMISSIONS.get(role, set())

    if "*" in grants:          # super-wildcard (admin)
        return True
    if permission in grants:   # exact match
        return True

    resource = permission.split(":", 1)[0]

    if f"{resource}:*" in grants:   # resource-level wildcard in grants
        return True

    # Requested permission is itself a wildcard — allow if role has *any* grant
    # on that resource (e.g. operator requesting "tasks:*" when they have "tasks:*")
    if permission.endswith(":*"):
        return any(g == "*" or g.startswith(f"{resource}:") for g in grants)

    return False


# ── FastAPI dependency factory ────────────────────────────────────────────────


def require_permission(permission: str, auth_dep: Callable | None = None) -> Any:
    """Build a FastAPI ``Depends`` that enforces *permission*.

    Must be called with the *auth_dep* callable (e.g. ``require_auth`` from
    server.py) so it can chain authentication before the permission check.

    Args:
        permission: permission string, e.g. "admin:*", "research:*"
        auth_dep: the ``require_auth`` async function from server.py.
                  If None, authentication is skipped (not recommended for
                  production; only useful when REQUIRE_AUTH=0).

    Returns:
        A ``Depends(...)`` instance suitable as a FastAPI route parameter default.

    Example::

        @app.post("/api/settings")
        def save_settings(body: _SettingsUpdateRequest,
                          _rbac=require_permission("settings:write", require_auth)):
            ...
    """
    if auth_dep is None:
        # Fallback: no auth dep wired — just check role from request state.
        async def _check_no_auth(request: Request) -> None:
            role: str = getattr(request.state, "role", "viewer")
            if not has_permission(role, permission):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Role '{role}' lacks permission '{permission}'",
                )

        return Depends(_check_no_auth)

    # Normal path: chain off auth_dep so authn always runs first.
    async def _check(
        request: Request,
        token_data: Any = Depends(auth_dep),
    ) -> Any:
        # token_data is None when REQUIRE_AUTH=0 (pass-through mode).
        role: str = "viewer"
        if isinstance(token_data, dict):
            role = token_data.get("role", "viewer")

        if not has_permission(role, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{role}' lacks permission '{permission}'",
            )
        return token_data

    return Depends(_check)
