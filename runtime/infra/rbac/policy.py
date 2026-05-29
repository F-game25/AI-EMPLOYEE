"""RBAC Policy Engine — Python side.

Mirrors backend/infra/rbac/policy.js so Python routes enforce the same rules.
FastAPI dependency injection pattern: use `require_permission(P.TASKS_SUBMIT)`.
"""
from __future__ import annotations

import logging
import os
from enum import Enum
from typing import Optional

import httpx
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

logger = logging.getLogger("rbac_policy")

OPA_URL = os.environ.get("POLICY_OPA_URL")

# ── Roles ─────────────────────────────────────────────────────────────────────

class Role(str, Enum):
    SUPER_ADMIN      = "super_admin"
    ORG_ADMIN        = "org_admin"
    MANAGER          = "manager"
    EMPLOYEE         = "employee"
    AUDITOR          = "auditor"
    SECURITY_OFFICER = "security_officer"

# ── Permissions ───────────────────────────────────────────────────────────────

class P:
    AGENTS_READ       = "agents:read"
    AGENTS_WRITE      = "agents:write"
    AGENTS_EXECUTE    = "agents:execute"
    AGENTS_STOP       = "agents:stop"
    AGENTS_CONFIGURE  = "agents:configure"
    TASKS_READ        = "tasks:read"
    TASKS_SUBMIT      = "tasks:submit"
    TASKS_CANCEL      = "tasks:cancel"
    WORKFLOWS_READ    = "workflows:read"
    WORKFLOWS_START   = "workflows:start"
    WORKFLOWS_SIGNAL  = "workflows:signal"
    HITL_READ         = "hitl:read"
    HITL_APPROVE      = "hitl:approve"
    HITL_REJECT       = "hitl:reject"
    SECRETS_READ      = "secrets:read"
    SECRETS_WRITE     = "secrets:write"
    SECRETS_ROTATE    = "secrets:rotate"
    SECRETS_DELETE    = "secrets:delete"
    EVOLUTION_READ    = "evolution:read"
    EVOLUTION_APPROVE = "evolution:approve"
    EVOLUTION_DEPLOY  = "evolution:deploy"
    SYSTEM_READ       = "system:read"
    SYSTEM_CONFIGURE  = "system:configure"
    SYSTEM_HALT       = "system:halt"
    USERS_READ        = "users:read"
    USERS_WRITE       = "users:write"
    AUDIT_READ        = "audit:read"
    AUDIT_EXPORT      = "audit:export"
    SANDBOX_EXECUTE   = "sandbox:execute"
    SANDBOX_CONFIGURE = "sandbox:configure"
    FINANCE_READ      = "finance:read"
    FINANCE_APPROVE   = "finance:approve"

# ── Role permission map ───────────────────────────────────────────────────────

_ALL_PERMS = [v for k, v in P.__dict__.items() if not k.startswith("_")]

ROLE_PERMISSIONS: dict[Role, set[str]] = {
    Role.SUPER_ADMIN:      set(_ALL_PERMS),
    Role.ORG_ADMIN: {
        P.AGENTS_READ, P.AGENTS_WRITE, P.AGENTS_EXECUTE, P.AGENTS_STOP, P.AGENTS_CONFIGURE,
        P.TASKS_READ, P.TASKS_SUBMIT, P.TASKS_CANCEL,
        P.WORKFLOWS_READ, P.WORKFLOWS_START, P.WORKFLOWS_SIGNAL,
        P.HITL_READ, P.HITL_APPROVE, P.HITL_REJECT,
        P.SECRETS_READ, P.SECRETS_WRITE, P.SECRETS_ROTATE,
        P.EVOLUTION_READ, P.EVOLUTION_APPROVE,
        P.SYSTEM_READ, P.SYSTEM_CONFIGURE,
        P.USERS_READ, P.USERS_WRITE,
        P.AUDIT_READ, P.AUDIT_EXPORT,
        P.SANDBOX_EXECUTE,
        P.FINANCE_READ, P.FINANCE_APPROVE,
    },
    Role.MANAGER: {
        P.AGENTS_READ, P.AGENTS_EXECUTE, P.AGENTS_STOP,
        P.TASKS_READ, P.TASKS_SUBMIT, P.TASKS_CANCEL,
        P.WORKFLOWS_READ, P.WORKFLOWS_START, P.WORKFLOWS_SIGNAL,
        P.HITL_READ, P.HITL_APPROVE, P.HITL_REJECT,
        P.SYSTEM_READ, P.USERS_READ, P.AUDIT_READ,
        P.FINANCE_READ, P.EVOLUTION_READ,
    },
    Role.EMPLOYEE: {
        P.AGENTS_READ, P.AGENTS_EXECUTE,
        P.TASKS_READ, P.TASKS_SUBMIT,
        P.WORKFLOWS_READ, P.WORKFLOWS_START,
        P.HITL_READ, P.SYSTEM_READ, P.FINANCE_READ,
    },
    Role.AUDITOR: {
        P.AGENTS_READ, P.TASKS_READ, P.WORKFLOWS_READ,
        P.HITL_READ, P.SYSTEM_READ, P.USERS_READ,
        P.AUDIT_READ, P.AUDIT_EXPORT,
        P.EVOLUTION_READ, P.FINANCE_READ,
    },
    Role.SECURITY_OFFICER: {
        P.AGENTS_READ, P.AGENTS_STOP,
        P.SECRETS_READ, P.SECRETS_ROTATE, P.SECRETS_DELETE,
        P.SYSTEM_READ, P.AUDIT_READ, P.AUDIT_EXPORT,
        P.USERS_READ, P.EVOLUTION_READ, P.SANDBOX_CONFIGURE,
    },
}

# ── Decision enum ─────────────────────────────────────────────────────────────

class Decision(str, Enum):
    ALLOW    = "allow"
    DENY     = "deny"
    ESCALATE = "escalate"

# ── Policy engine ─────────────────────────────────────────────────────────────

class PolicyEngine:
    async def evaluate(
        self,
        role: Role | str,
        permission: str,
        *,
        tenant_id: str = "system",
        user_id: Optional[str] = None,
        context: dict | None = None,
    ) -> dict:
        context = context or {}
        role_str = role.value if isinstance(role, Role) else role

        # 1. OPA
        opa = await self._query_opa({
            "role": role_str, "permission": permission,
            "tenant_id": tenant_id, "user_id": user_id, "context": context,
        })
        if opa:
            return opa

        # 2. Built-in rules
        builtin = self._builtin(role_str, permission, context)
        if builtin:
            return builtin

        # 3. RBAC
        role_enum = Role(role_str) if role_str in Role._value2member_map_ else None
        grants = ROLE_PERMISSIONS.get(role_enum, set()) if role_enum else set()
        resource = permission.split(":")[0]
        granted = permission in grants or f"{resource}:*" in grants
        return {
            "decision": Decision.ALLOW if granted else Decision.DENY,
            "reason": "Permission granted by role" if granted else f"Role '{role_str}' lacks '{permission}'",
            "source": "rbac",
        }

    def _builtin(self, role: str, permission: str, context: dict) -> dict | None:
        cost = context.get("estimated_cost_usd", 0)
        if cost > 10:
            can = permission in ROLE_PERMISSIONS.get(Role.ORG_ADMIN, set())
            return {
                "decision": Decision.ALLOW if role in (Role.SUPER_ADMIN, Role.ORG_ADMIN) else Decision.ESCALATE,
                "reason": "Operation exceeds $10 cost threshold",
                "source": "builtin:financial_limit",
            }
        if permission == P.EVOLUTION_DEPLOY and role not in (Role.SUPER_ADMIN.value, Role.ORG_ADMIN.value):
            return {"decision": Decision.DENY, "reason": "Evolution deployment restricted to org-admin+", "source": "builtin:evolution_deploy_guard"}
        if permission == P.SYSTEM_HALT and role != Role.SUPER_ADMIN.value:
            return {"decision": Decision.DENY, "reason": "System halt restricted to super_admin", "source": "builtin:system_halt_guard"}
        return None

    async def _query_opa(self, input_data: dict) -> dict | None:
        if not OPA_URL:
            return None
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                resp = await client.post(OPA_URL, json={"input": input_data})
                data = resp.json()
                if data.get("result") is True:
                    return {"decision": Decision.ALLOW, "source": "opa"}
                if data.get("result") is False:
                    return {"decision": Decision.DENY, "source": "opa"}
        except Exception as e:
            logger.debug("OPA query failed: %s", e)
        return None

_engine = PolicyEngine()

def get_policy_engine() -> PolicyEngine:
    return _engine

# ── FastAPI dependency ────────────────────────────────────────────────────────

def require_permission(permission: str):
    """FastAPI dependency — raises 403 if permission denied."""
    async def _dep(request: Request):
        user   = getattr(request.state, "user",   {}) or {}
        role   = user.get("role", Role.EMPLOYEE.value)
        tenant = user.get("tenant_id", "system")
        ctx    = {}

        result = await _engine.evaluate(role, permission, tenant_id=tenant, context=ctx)
        if result["decision"] == Decision.DENY:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                                detail=result.get("reason", "Access denied"))
        if result["decision"] == Decision.ESCALATE:
            raise HTTPException(status_code=status.HTTP_202_ACCEPTED,
                                detail={"escalate": True, "reason": result.get("reason")})
        return result
    return _dep
