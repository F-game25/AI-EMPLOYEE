"""RBAC middleware for FastAPI route protection."""
from fastapi import HTTPException, Depends
from core.auth import get_current_user
from core.tenancy import get_current_tenant
from core.rbac import get_rbac_manager, RolePermission, Role


async def require_permission(permission: str):
    """Dependency: require user to have a specific permission."""
    async def check_permission(
        user: dict = Depends(get_current_user),
        tenant: dict = Depends(get_current_tenant),
    ):
        rbac = get_rbac_manager()
        if not rbac.has_permission(user.get("user_id"), tenant.tenant_id, permission):
            raise HTTPException(
                status_code=403,
                detail=f"Permission denied: {permission} required",
            )
        return user
    return check_permission


async def require_role(required_role: Role):
    """Dependency: require user to have a specific role or higher."""
    async def check_role(
        user: dict = Depends(get_current_user),
        tenant: dict = Depends(get_current_tenant),
    ):
        rbac = get_rbac_manager()
        user_role = rbac.get_user_role(user.get("user_id"), tenant.tenant_id)

        role_hierarchy = {Role.VIEWER: 0, Role.MEMBER: 1, Role.ADMIN: 2}
        if role_hierarchy[user_role] < role_hierarchy[required_role]:
            raise HTTPException(
                status_code=403,
                detail=f"Role {required_role.value} required",
            )
        return user
    return check_role


async def require_execute_agents():
    """Dependency: require permission to execute agents."""
    return await require_permission("execute_agents")


async def require_manage_users():
    """Dependency: require permission to manage users."""
    return await require_permission("manage_users")


async def require_manage_billing():
    """Dependency: require permission to manage billing."""
    return await require_permission("manage_billing")


async def require_delete_data():
    """Dependency: require permission to delete data."""
    return await require_permission("delete_data")


async def require_view_audit_logs():
    """Dependency: require permission to view audit logs."""
    return await require_permission("view_audit_logs")
