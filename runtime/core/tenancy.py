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
import os
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
        # Relaxed from 8→3 chars (2026-05-18): the 8-char rule blocked the legitimate
        # 'default' local-mode tenant. Privacy/isolation does NOT depend on tenant_id
        # length — it depends on namespace separation (Chroma collection, vault root,
        # pending_queue path). Length validation is here only to prevent empty/single
        # char accidents; 3+ is sufficient.
        if not isinstance(self.tenant_id, str) or len(self.tenant_id) < 3:
            raise ValueError("tenant_id must be non-empty string (3+ chars)")


class TenantManager:
    """Manage tenant lifecycle, isolation, and context."""

    def __init__(self, ai_home: Path):
        self.ai_home = Path(ai_home)
        self.tenants_dir = self.ai_home / "tenants"
        self.tenants_dir.mkdir(parents=True, exist_ok=True)

    def create_tenant(self, org_name: str, user_email: str, region: Optional[str] = None) -> str:
        """Create new tenant, return tenant_id.

        Args:
            org_name: Human-readable organisation name.
            user_email: Owner's email address.
            region: Data-residency region code ("eu" | "us").  If omitted, the
                    value of the DEPLOYMENT_REGION env var is used; falls back
                    to "us" when neither is provided.
        """
        import json as _json
        from core.region import get_registry as _get_registry

        tenant_id = str(uuid.uuid4())[:8]  # Short UUID for readability
        tenant_path = self.tenants_dir / tenant_id
        tenant_path.mkdir(exist_ok=True)

        # Create tenant sub-directories
        (tenant_path / "state").mkdir(exist_ok=True)
        (tenant_path / "config").mkdir(exist_ok=True)

        # Resolve region: explicit arg > DEPLOYMENT_REGION env var > default "us"
        resolved_region = region or os.getenv("DEPLOYMENT_REGION", "us")

        # Persist tenant metadata (org, email, region)
        meta = {
            "tenant_id": tenant_id,
            "org_name": org_name,
            "user_email": user_email,
            "region": resolved_region,
        }
        (tenant_path / "config" / "tenant.json").write_text(_json.dumps(meta, indent=2))

        # Register in the region registry
        _get_registry().assign_region(tenant_id, resolved_region)

        logger.info(f"Created tenant: {tenant_id} for {org_name} ({user_email}) region={resolved_region}")
        return tenant_id

    def ensure_tenant(self, tenant_id: str, org_name: str = "Auto", user_email: str = "") -> Path:
        """Idempotent: create tenant dirs if missing. Used by local-mode boot to materialize
        the 'default' tenant on first request without going through register flow."""
        tenant_path = self.tenants_dir / tenant_id
        if not tenant_path.exists():
            tenant_path.mkdir(parents=True, exist_ok=True)
            (tenant_path / "state").mkdir(exist_ok=True)
            (tenant_path / "config").mkdir(exist_ok=True)
            logger.info(f"Auto-provisioned tenant: {tenant_id} ({org_name})")
        return tenant_path / "state"

    def get_tenant_state_dir(self, tenant_id: str) -> Path:
        """Get the state directory for a tenant. Auto-provisions if missing (local mode)."""
        path = self.tenants_dir / tenant_id / "state"
        if not path.exists():
            # Auto-provision rather than raise — supports local-mode bootstrap
            return self.ensure_tenant(tenant_id)
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
        secret = os.getenv("JWT_SECRET_KEY") or os.getenv("JWT_SECRET")
        if not secret:
            raise HTTPException(status_code=500, detail="JWT secret is not configured")

        payload = jwt.decode(token, secret, algorithms=["HS256"])
        tenant_id = payload.get("tenant_id")
        org_name = payload.get("org_name", "")
        user_email = payload.get("email", "")

        if not tenant_id:
            raise HTTPException(status_code=401, detail="Token missing tenant_id")

        return TenantContext(tenant_id=tenant_id, org_name=org_name, user_email=user_email)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
    except HTTPException:
        raise
    except Exception as e:
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
