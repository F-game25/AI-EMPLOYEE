"""Auth API — /api/auth/* (public) + /api/admin/* (ADMIN only)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

auth_router = APIRouter(prefix="/api/auth", tags=["auth"])
admin_router = APIRouter(prefix="/api/admin", tags=["admin"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    username: str
    password: str
    device_id: str = ""


class RegisterRequest(BaseModel):
    username: str
    password: str
    email: str = ""
    role: str = "user"  # ignored for self-registration — only admin can set roles


class RefreshRequest(BaseModel):
    refresh_token: str


class ChangeRoleRequest(BaseModel):
    role: str


class BlockRequest(BaseModel):
    reason: str = "admin_action"


# ── Auth helpers ──────────────────────────────────────────────────────────────

def _get_user_id(request: Request) -> str:
    return getattr(request.state, "user_id", "anonymous")

def _get_role(request: Request) -> str:
    return getattr(request.state, "role", "user")

def _require_admin(request: Request) -> None:
    from neural_brain.auth.rbac import require_role, Role
    if not require_role(_get_role(request), Role.ADMIN):
        raise HTTPException(status_code=403, detail="Admin role required")

def _require_dev(request: Request) -> None:
    from neural_brain.auth.rbac import require_role, Role
    if not require_role(_get_role(request), Role.DEV):
        raise HTTPException(status_code=403, detail="Dev role required")


# ── /api/auth/* ───────────────────────────────────────────────────────────────

@auth_router.post("/login")
async def login(req: LoginRequest, request: Request):
    ip = request.client.host if request.client else "0.0.0.0"
    ua = request.headers.get("user-agent", "")
    try:
        from neural_brain.auth.auth_manager import get_auth_manager
        result = get_auth_manager().login(
            username=req.username, password=req.password,
            ip=ip, device_id=req.device_id, user_agent=ua,
        )
        return {"ok": True, **result}
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))


@auth_router.post("/register")
async def register(req: RegisterRequest):
    try:
        from neural_brain.auth.auth_manager import get_auth_manager
        # Self-registration always gets 'user' role regardless of what's requested
        user = get_auth_manager().register(
            username=req.username, password=req.password, email=req.email, role="user"
        )
        return {"ok": True, "user_id": user.user_id, "username": user.username, "role": user.role}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@auth_router.post("/refresh")
async def refresh(req: RefreshRequest):
    try:
        from neural_brain.auth.jwt_handler import rotate_refresh_token
        access, refresh = rotate_refresh_token(req.refresh_token)
        return {"ok": True, "access_token": access, "refresh_token": refresh}
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))


@auth_router.post("/logout")
async def logout(request: Request):
    user_id = _get_user_id(request)
    jwt_payload = getattr(request.state, "jwt_payload", {})
    device_id = jwt_payload.get("device", "")
    try:
        from neural_brain.auth.jwt_handler import revoke_device
        from neural_brain.auth.session_manager import get_session_manager
        revoke_device(user_id, device_id)
        get_session_manager().revoke_device(user_id, device_id)
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@auth_router.get("/me")
async def me(request: Request):
    user_id = _get_user_id(request)
    from neural_brain.auth.auth_manager import get_auth_manager
    user = get_auth_manager().get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    sessions = []
    try:
        from neural_brain.auth.session_manager import get_session_manager
        sessions = get_session_manager().get_active_sessions(user_id)
    except Exception:
        pass
    return {"ok": True, "user": user, "sessions": sessions}


# ── /api/admin/* ──────────────────────────────────────────────────────────────

@admin_router.get("/users")
async def list_users(request: Request):
    _require_admin(request)
    from neural_brain.auth.auth_manager import get_auth_manager
    return {"ok": True, "users": get_auth_manager().list_users()}


@admin_router.get("/users/{user_id}")
async def get_user(user_id: str, request: Request):
    _require_admin(request)
    from neural_brain.auth.auth_manager import get_auth_manager
    user = get_auth_manager().get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {"ok": True, "user": user}


@admin_router.post("/users/{user_id}/block")
async def block_user(user_id: str, req: BlockRequest, request: Request):
    _require_admin(request)
    from neural_brain.auth.auth_manager import get_auth_manager
    get_auth_manager().block_user(user_id, req.reason)
    return {"ok": True, "blocked": user_id}


@admin_router.post("/users/{user_id}/unblock")
async def unblock_user(user_id: str, request: Request):
    _require_admin(request)
    from neural_brain.auth.auth_manager import get_auth_manager
    get_auth_manager().unblock_user(user_id)
    return {"ok": True, "unblocked": user_id}


@admin_router.post("/users/{user_id}/role")
async def set_role(user_id: str, req: ChangeRoleRequest, request: Request):
    _require_admin(request)
    from neural_brain.auth.auth_manager import get_auth_manager
    get_auth_manager().set_role(user_id, req.role)
    return {"ok": True, "user_id": user_id, "role": req.role}


@admin_router.post("/users/{user_id}/logout")
async def force_logout(user_id: str, request: Request):
    _require_admin(request)
    from neural_brain.auth.auth_manager import get_auth_manager
    count = get_auth_manager().force_logout(user_id)
    return {"ok": True, "sessions_revoked": count}


@admin_router.get("/sessions")
async def list_sessions(request: Request):
    _require_admin(request)
    from neural_brain.auth.session_manager import get_session_manager
    return {"ok": True, "sessions": get_session_manager().get_all_active()}


@admin_router.post("/sessions/invalidate-all")
async def invalidate_all_sessions(request: Request):
    _require_admin(request)
    from neural_brain.security.blacklight_engine import get_blacklight
    count = get_blacklight().invalidate_all_sessions("admin_forced")
    return {"ok": True, "sessions_invalidated": count}


@admin_router.post("/keys/rotate")
async def rotate_keys(request: Request):
    _require_admin(request)
    from neural_brain.security.key_manager import get_key_manager
    version = get_key_manager().force_rotate()
    return {"ok": True, "new_version": version}


@admin_router.get("/keys/status")
async def key_status(request: Request):
    _require_admin(request)
    from neural_brain.security.key_manager import get_key_manager
    return {"ok": True, **get_key_manager().get_status()}


@admin_router.get("/security/status")
async def security_status(request: Request):
    _require_admin(request)
    from neural_brain.security.blacklight_engine import get_blacklight
    return {"ok": True, **get_blacklight().get_status()}


@admin_router.post("/security/lockdown")
async def force_lockdown(request: Request):
    _require_admin(request)
    from neural_brain.security.system_control import get_system_control
    get_system_control().lockdown_system("admin_manual_lockdown")
    return {"ok": True, "mode": "LOCKDOWN"}


@admin_router.post("/security/unlock")
async def force_unlock(request: Request):
    _require_admin(request)
    from neural_brain.security.system_control import get_system_control, SystemState
    ctrl = get_system_control()
    ctrl.set_mode(SystemState.NORMAL, reason="admin_manual_unlock", threat_score=0)
    ctrl.resume_agents()
    ctrl.enable_forge()
    return {"ok": True, "mode": "NORMAL"}


@admin_router.get("/telemetry")
async def get_telemetry(
    request: Request,
    category: str | None = None,
    user_id: str | None = None,
    errors_only: bool = False,
    limit: int = 200,
):
    _require_admin(request)
    from neural_brain.core.telemetry import get_telemetry
    records = get_telemetry().query(
        category=category, user_id=user_id, errors_only=errors_only, limit=limit
    )
    return {"ok": True, "records": records}


@admin_router.get("/telemetry/summary")
async def telemetry_summary(request: Request, window_s: float = 3600):
    _require_admin(request)
    from neural_brain.core.telemetry import get_telemetry
    return {"ok": True, **get_telemetry().get_summary(window_s)}


@admin_router.get("/telemetry/errors")
async def top_errors(request: Request, limit: int = 20):
    _require_admin(request)
    from neural_brain.core.telemetry import get_telemetry
    return {"ok": True, "errors": get_telemetry().get_top_errors(limit)}


@admin_router.get("/health")
async def system_health(request: Request):
    _require_admin(request)
    from neural_brain.core.health_monitor import get_health_monitor
    return {"ok": True, **get_health_monitor().get_summary()}


@admin_router.get("/agents")
async def agents_status(request: Request):
    _require_dev(request)
    from neural_brain.core.task_queue import get_task_queue
    return {"ok": True, **get_task_queue().stats()}


@admin_router.post("/agents/restart")
async def restart_agents(request: Request):
    _require_admin(request)
    from neural_brain.core.task_queue import get_task_queue
    from neural_brain.security.system_control import get_system_control
    ctrl = get_system_control()
    ctrl.resume_agents()
    cancelled = get_task_queue().cancel_all()
    return {"ok": True, "tasks_cancelled": cancelled}


@admin_router.post("/forge/trigger")
async def trigger_forge(request: Request):
    _require_admin(request)
    try:
        from neural_brain.utils.event_bus import publish
        publish("forge:health_trigger", source="admin", payload={"reason": "admin_manual"})
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@admin_router.delete("/memory/segment")
async def clear_memory_segment(request: Request, type: str = "episodic"):
    _require_admin(request)
    return {"ok": True, "cleared": type, "note": "Memory clear not implemented in current memory backend"}


@admin_router.get("/debug/engine")
async def debug_engine(request: Request):
    _require_admin(request)
    try:
        from neural_brain.core.consciousness_engine import get_engine
        return {"ok": True, **get_engine().get_status()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
