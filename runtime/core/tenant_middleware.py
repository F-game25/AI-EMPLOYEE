"""FastAPI middleware for tenant extraction and isolation.

Extracts tenant_id from JWT token and sets request-scoped context.
Enforces tenant isolation on all routes that access data.
"""
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
import jwt
import logging

from .tenancy import TenantContext, get_tenant_manager

logger = logging.getLogger(__name__)


class TenantMiddleware(BaseHTTPMiddleware):
    """Extract and validate tenant from JWT, set context for request."""

    def __init__(self, app, secret_key: str):
        super().__init__(app)
        self.secret_key = secret_key
        # Routes that don't require tenant context (auth, health, etc.)
        self.exempt_routes = {
            "/health",
            "/health/detail",
            "/events",
            "/security/status",
            "/auth/register",
            "/auth/login",
            "/auth/refresh",
            "/auth/token",
            "/version",
            "/openapi.json",
            "/docs",
            "/redoc",
        }
        # NOTE: previous `exempt_prefixes` removed (2026-05-18 security audit CRITICAL).
        # Tenant context MUST be set for vault/memory/learning/topics — removing the bypass
        # restores per-tenant data isolation. Node forwards Authorization with valid JWT
        # so tenant_id is extracted normally.
        self.exempt_prefixes: tuple[str, ...] = ()

    async def dispatch(self, request: Request, call_next):
        """Extract tenant from JWT, set context, call handler, cleanup."""
        path = request.url.path

        # Skip tenant extraction for exempt routes
        if path in self.exempt_routes or path.startswith("/openapi"):
            response = await call_next(request)
            return response
        if any(path.startswith(p) for p in self.exempt_prefixes):
            response = await call_next(request)
            return response

        # Extract JWT from Authorization header
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return JSONResponse(
                {"detail": "Missing or invalid Authorization header"},
                status_code=401,
            )

        token = auth_header[7:]  # Remove "Bearer " prefix

        try:
            # Decode JWT (signature should be verified elsewhere with FastAPI Depends)
            payload = jwt.decode(token, self.secret_key, algorithms=["HS256"])
            tenant_id = payload.get("tenant_id")
            org_name = payload.get("org_name", "")
            email = payload.get("email", "")

            if not tenant_id:
                return JSONResponse(
                    {"detail": "Token missing tenant_id claim"},
                    status_code=401,
                )

            # Create and set tenant context
            context = TenantContext(
                tenant_id=tenant_id,
                org_name=org_name,
                user_email=email,
            )
            manager = get_tenant_manager()
            manager.set_current_tenant(context)

            # Validate tenant exists
            try:
                manager.get_tenant_state_dir(tenant_id)
            except ValueError:
                logger.warning(f"Token references non-existent tenant: {tenant_id}")
                return JSONResponse(
                    {"detail": "Tenant not found"},
                    status_code=403,
                )

            # Process request
            response = await call_next(request)

            # Cleanup tenant context
            manager.clear_current_tenant()

            return response

        except jwt.DecodeError as e:
            logger.warning(f"JWT decode error: {e}")
            return JSONResponse(
                {"detail": f"Invalid token: {e}"},
                status_code=401,
            )
        except jwt.ExpiredSignatureError:
            return JSONResponse(
                {"detail": "Token expired"},
                status_code=401,
            )
        except Exception as e:
            logger.error(f"Tenant middleware error: {e}")
            return JSONResponse(
                {"detail": "Internal server error"},
                status_code=500,
            )
