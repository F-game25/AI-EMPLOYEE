"""Multi-tenancy support — tenant isolation, context, and middleware.

Tenancy model:
- Each user belongs to ONE organization (tenant)
- Each tenant is identified by tenant_id (UUID)
- All state is keyed by tenant_id for isolation
- JWT tokens include tenant_id claim for verification
"""
from __future__ import annotations

import uuid
import logging
from typing import Optional
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

# Context variable to hold current tenant during request
_current_tenant: ContextVar[Optional[TenantContext]] = ContextVar('tenant', default=None)


@dataclass
class TenantContext:
    """Request-scoped tenant information."""
    tenant_id: str
    org_name: str
    user_email: str

    def __post_init__(self):
        if not self.tenant_id:
            raise ValueError("tenant_id is required")
        if not isinstance(self.tenant_id, str) or len(self.tenant_id) < 8:
            raise ValueError("tenant_id must be non-empty string (8+ chars)")


class TenantManager:
    """Manage tenant lifecycle, isolation, and context."""

    def __init__(self, ai_home: Path):
        self.ai_home = Path(ai_home)
        self.tenants_dir = self.ai_home / "tenants"
        self.tenants_dir.mkdir(parents=True, exist_ok=True)

    def create_tenant(self, org_name: str, user_email: str) -> str:
        """Create new tenant, return tenant_id."""
        tenant_id = str(uuid.uuid4())[:8]  # Short UUID for readability
        tenant_path = self.tenants_dir / tenant_id
        tenant_path.mkdir(exist_ok=True)

        # Create tenant state directory
        (tenant_path / "state").mkdir(exist_ok=True)
        (tenant_path / "config").mkdir(exist_ok=True)

        logger.info(f"Created tenant: {tenant_id} for {org_name} ({user_email})")
        return tenant_id

    def get_tenant_state_dir(self, tenant_id: str) -> Path:
        """Get the state directory for a tenant."""
        path = self.tenants_dir / tenant_id / "state"
        if not path.exists():
            raise ValueError(f"Tenant {tenant_id} not found")
        return path

    def get_tenant_config_dir(self, tenant_id: str) -> Path:
        """Get the config directory for a tenant."""
        path = self.tenants_dir / tenant_id / "config"
        if not path.exists():
            raise ValueError(f"Tenant {tenant_id} not found")
        return path

    def set_current_tenant(self, context: TenantContext) -> None:
        """Set current tenant context for this request."""
        _current_tenant.set(context)

    def get_current_tenant(self) -> Optional[TenantContext]:
        """Get current tenant context."""
        return _current_tenant.get()

    def require_current_tenant(self) -> TenantContext:
        """Get current tenant or raise error."""
        context = _current_tenant.get()
        if not context:
            raise RuntimeError("No tenant context set for this request")
        return context

    def clear_current_tenant(self) -> None:
        """Clear current tenant context (e.g., at end of request)."""
        _current_tenant.set(None)


# Global tenant manager (instantiate in main)
_tenant_manager: Optional[TenantManager] = None


def init_tenant_manager(ai_home: Path) -> TenantManager:
    """Initialize global tenant manager."""
    global _tenant_manager
    _tenant_manager = TenantManager(ai_home)
    return _tenant_manager


def get_tenant_manager() -> TenantManager:
    """Get global tenant manager."""
    if _tenant_manager is None:
        raise RuntimeError("Tenant manager not initialized. Call init_tenant_manager() first.")
    return _tenant_manager


# FastAPI dependency for tenant extraction from JWT
async def get_current_tenant_from_jwt(request) -> TenantContext:
    """Extract tenant from JWT token in request."""
    import jwt
    from fastapi import HTTPException

    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="No authorization token")

    token = auth_header[7:]  # Remove "Bearer " prefix

    try:
        payload = jwt.decode(token, options={"verify_signature": False})  # Signature verified elsewhere
        tenant_id = payload.get("tenant_id")
        org_name = payload.get("org_name", "")
        user_email = payload.get("email", "")

        if not tenant_id:
            raise HTTPException(status_code=401, detail="Token missing tenant_id")

        return TenantContext(tenant_id=tenant_id, org_name=org_name, user_email=user_email)
    except jwt.DecodeError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {e}")


# Helper to get tenant-aware state file path
def get_tenant_state_file(filename: str, tenant_id: Optional[str] = None) -> Path:
    """Get tenant-specific state file path.

    Args:
        filename: Name of the state file (e.g., "deals.json")
        tenant_id: Optional; if not provided, uses current tenant context

    Returns:
        Path to tenant-specific state file
    """
    if tenant_id is None:
        manager = get_tenant_manager()
        context = manager.require_current_tenant()
        tenant_id = context.tenant_id

    manager = get_tenant_manager()
    state_dir = manager.get_tenant_state_dir(tenant_id)
    return state_dir / filename
