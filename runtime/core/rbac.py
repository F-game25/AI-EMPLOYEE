"""Role-based access control system."""
from enum import Enum
from typing import Optional, Set
from dataclasses import dataclass
from datetime import datetime

from core.tenancy import get_current_tenant
from core.database import get_database


class Role(str, Enum):
    """User roles in the system."""
    ADMIN = "admin"
    MEMBER = "member"
    VIEWER = "viewer"


@dataclass
class RolePermission:
    """Defines what actions a role can perform."""
    role: Role
    can_execute_agents: bool
    can_manage_users: bool
    can_manage_billing: bool
    can_delete_data: bool
    can_view_audit_logs: bool

    @staticmethod
    def get_permissions(role: Role) -> "RolePermission":
        """Get permission set for a role."""
        permissions = {
            Role.ADMIN: RolePermission(
                role=Role.ADMIN,
                can_execute_agents=True,
                can_manage_users=True,
                can_manage_billing=True,
                can_delete_data=True,
                can_view_audit_logs=True,
            ),
            Role.MEMBER: RolePermission(
                role=Role.MEMBER,
                can_execute_agents=True,
                can_manage_users=False,
                can_manage_billing=False,
                can_delete_data=False,
                can_view_audit_logs=False,
            ),
            Role.VIEWER: RolePermission(
                role=Role.VIEWER,
                can_execute_agents=False,
                can_manage_users=False,
                can_manage_billing=False,
                can_delete_data=False,
                can_view_audit_logs=False,
            ),
        }
        return permissions[role]

    def require(self, permission: str) -> bool:
        """Check if role has a specific permission."""
        perm_attr = f"can_{permission}"
        return getattr(self, perm_attr, False)


class RBACManager:
    """Manage user roles and permissions."""

    def __init__(self):
        self.db = get_database()

    def assign_role(self, user_id: str, role: Role, tenant_id: str) -> bool:
        """Assign a role to a user in a tenant."""
        try:
            self.db.execute(
                """
                INSERT INTO user_roles (user_id, tenant_id, role, assigned_at)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (user_id, tenant_id) DO UPDATE
                SET role = %s, assigned_at = %s
                """,
                (user_id, tenant_id, role.value, datetime.utcnow(), role.value, datetime.utcnow()),
                tenant_id=tenant_id,
            )
            return True
        except Exception as e:
            print(f"Failed to assign role: {e}")
            return False

    def get_user_role(self, user_id: str, tenant_id: str) -> Optional[Role]:
        """Get user's role in a tenant."""
        try:
            result = self.db.execute(
                "SELECT role FROM user_roles WHERE user_id = %s AND tenant_id = %s",
                (user_id, tenant_id),
                tenant_id=tenant_id,
            )
            if result:
                return Role(result[0].get("role"))
            return Role.VIEWER  # default to viewer
        except Exception:
            return Role.VIEWER

    def has_permission(self, user_id: str, tenant_id: str, permission: str) -> bool:
        """Check if user has a specific permission."""
        role = self.get_user_role(user_id, tenant_id)
        perms = RolePermission.get_permissions(role)
        return perms.require(permission)

    def list_user_roles(self, tenant_id: str) -> list[dict]:
        """List all user roles in a tenant."""
        try:
            return self.db.execute(
                "SELECT user_id, role, assigned_at FROM user_roles WHERE tenant_id = %s ORDER BY assigned_at DESC",
                (),
                tenant_id=tenant_id,
            )
        except Exception:
            return []


def get_rbac_manager() -> RBACManager:
    """Get global RBAC manager instance."""
    return RBACManager()
