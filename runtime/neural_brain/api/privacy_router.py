"""Privacy, telemetry, and update API routes.

/api/privacy/*  — privacy mode management (admin only)
/api/telemetry/* — local stats + feedback (admin + user)
/api/updates/*  — update check/download/apply (admin only)
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

privacy_router  = APIRouter(prefix="/api/privacy",  tags=["privacy"])
telemetry_router = APIRouter(prefix="/api/telemetry", tags=["telemetry"])
updates_router  = APIRouter(prefix="/api/updates",  tags=["updates"])
logger = logging.getLogger(__name__)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_role(request: Request) -> str:
    return getattr(request.state, "role", "user")

def _require_admin(request: Request) -> None:
    from neural_brain.auth.rbac import require_role, Role
    if not require_role(_get_role(request), Role.ADMIN):
        raise HTTPException(status_code=403, detail="Admin role required")


def _server_error(operation: str, exc_type: str) -> HTTPException:
    logger.warning("privacy API %s failed: %s", operation, exc_type)
    return HTTPException(status_code=500, detail=f"{operation} failed")


# ── Schemas ───────────────────────────────────────────────────────────────────

class SetPrivacyModeRequest(BaseModel):
    mode: str = Field(..., description="OFFLINE | HYBRID | CONNECTED")

class SetTelemetryRequest(BaseModel):
    enabled: bool
    endpoint: str = ""

class SetAutoUpdateRequest(BaseModel):
    enabled: bool
    endpoint: str = ""

class FeedbackRequest(BaseModel):
    issue_type: str = Field(..., max_length=64)
    severity: str = Field(default="MEDIUM")
    description_category: str = Field(..., max_length=64,
        description="Category label only — NOT the actual issue text")
    extra_metrics: dict | None = None


# ── /api/privacy/* ────────────────────────────────────────────────────────────

@privacy_router.get("/status")
async def privacy_status(request: Request):
    from neural_brain.config.privacy_mode import get_privacy
    return {"ok": True, **get_privacy().get_status()}


@privacy_router.post("/mode")
async def set_privacy_mode(req: SetPrivacyModeRequest, request: Request):
    _require_admin(request)
    try:
        from neural_brain.config.privacy_mode import get_privacy, PrivacyMode
        get_privacy().set_mode(PrivacyMode(req.mode.upper()))
        return {"ok": True, "mode": req.mode.upper()}
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid mode '{req.mode}' — use OFFLINE|HYBRID|CONNECTED")


@privacy_router.post("/telemetry")
async def configure_telemetry(req: SetTelemetryRequest, request: Request):
    _require_admin(request)
    from neural_brain.config.privacy_mode import get_privacy
    get_privacy().set_telemetry(req.enabled, req.endpoint)
    return {"ok": True, "telemetry_enabled": req.enabled}


@privacy_router.post("/auto-update")
async def configure_auto_update(req: SetAutoUpdateRequest, request: Request):
    _require_admin(request)
    from neural_brain.config.privacy_mode import get_privacy
    get_privacy().set_auto_update(req.enabled, req.endpoint)
    return {"ok": True, "auto_update": req.enabled}


# ── /api/telemetry/* ─────────────────────────────────────────────────────────

@telemetry_router.get("/stats")
async def telemetry_stats(request: Request):
    """Local stats — available to all authenticated users."""
    try:
        from neural_brain.telemetry.telemetry_engine import get_telemetry_engine
        return {"ok": True, **get_telemetry_engine().get_stats()}
    except Exception as e:
        raise _server_error("telemetry stats", type(e).__name__)


@telemetry_router.get("/errors")
async def top_errors(request: Request, limit: int = 10):
    try:
        from neural_brain.telemetry.telemetry_engine import get_telemetry_engine
        return {"ok": True, "errors": get_telemetry_engine().get_top_errors(limit)}
    except Exception as e:
        raise _server_error("top errors", type(e).__name__)


@telemetry_router.get("/summary")
async def event_summary(request: Request, window_hours: int = 24):
    try:
        from neural_brain.telemetry.telemetry_engine import get_telemetry_engine
        return {"ok": True, "summary": get_telemetry_engine().get_event_summary(window_hours)}
    except Exception as e:
        raise _server_error("event summary", type(e).__name__)


@telemetry_router.post("/bundle")
async def force_bundle(request: Request):
    """Force immediate bundle creation (admin only)."""
    _require_admin(request)
    try:
        from neural_brain.telemetry.telemetry_engine import get_telemetry_engine
        bundle_id = get_telemetry_engine().force_bundle()
        return {"ok": True, "bundle_id": bundle_id}
    except Exception as e:
        raise _server_error("bundle creation", type(e).__name__)


@telemetry_router.post("/rotate-id")
async def rotate_system_id(request: Request):
    """Rotate the anonymous system ID (breaks linkability to past bundles)."""
    _require_admin(request)
    try:
        from neural_brain.telemetry.telemetry_engine import get_telemetry_engine
        new_id = get_telemetry_engine().rotate_system_id()
        return {"ok": True, "new_id_prefix": new_id[:8]}
    except Exception as e:
        raise _server_error("system id rotation", type(e).__name__)


@telemetry_router.post("/feedback")
async def submit_feedback(req: FeedbackRequest, request: Request):
    """User feedback — explicit opt-in. Only category labels are stored, not text."""
    try:
        from neural_brain.telemetry.telemetry_engine import get_telemetry_engine
        feedback_id = get_telemetry_engine().submit_feedback(
            issue_type=req.issue_type,
            severity=req.severity,
            description_category=req.description_category,
            extra_metrics=req.extra_metrics,
        )
        return {"ok": True, "feedback_id": feedback_id}
    except Exception as e:
        raise _server_error("feedback submission", type(e).__name__)


@telemetry_router.get("/analyze")
async def run_local_analysis(request: Request):
    """Run local AI analysis of current metrics and get improvement suggestions."""
    try:
        from neural_brain.telemetry.local_analyzer import get_local_analyzer
        issues = get_local_analyzer().analyze()
        return {"ok": True, "issues": issues, "count": len(issues)}
    except Exception as e:
        raise _server_error("local analysis", type(e).__name__)


@telemetry_router.get("/analyze/last")
async def last_analysis(request: Request):
    try:
        from neural_brain.telemetry.local_analyzer import get_local_analyzer
        return {"ok": True, "issues": get_local_analyzer().get_last_analysis()}
    except Exception as e:
        raise _server_error("last analysis", type(e).__name__)


# ── /api/updates/* ────────────────────────────────────────────────────────────

@updates_router.get("/status")
async def update_status(request: Request):
    _require_admin(request)
    try:
        from neural_brain.updates.update_manager import get_update_manager
        return {"ok": True, **get_update_manager().get_status()}
    except Exception as e:
        raise _server_error("update status", type(e).__name__)


@updates_router.post("/check")
async def check_updates(request: Request):
    _require_admin(request)
    try:
        from neural_brain.updates.update_manager import get_update_manager
        info = get_update_manager().check()
        return {"ok": True, "available": info}
    except Exception as e:
        raise _server_error("update check", type(e).__name__)


@updates_router.post("/download")
async def download_update(request: Request, version: str | None = None):
    _require_admin(request)
    try:
        from neural_brain.updates.update_manager import get_update_manager
        path = get_update_manager().download(version)
        if path is None:
            return {"ok": False, "detail": "No update available or download failed"}
        return {"ok": True, "path": str(path)}
    except Exception as e:
        raise _server_error("update download", type(e).__name__)


@updates_router.post("/apply")
async def apply_update(request: Request, dry_run: bool = False):
    _require_admin(request)
    try:
        from neural_brain.updates.update_manager import get_update_manager
        from neural_brain.updates.update_manager import _PENDING_DIR
        # Find most recently downloaded package
        packages = sorted(_PENDING_DIR.glob("*.tar.gz"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not packages:
            return {"ok": False, "detail": "No downloaded package found — run /download first"}
        result = get_update_manager().apply(packages[0], dry_run=dry_run)
        return {"ok": result.get("ok", False), **result}
    except Exception as e:
        raise _server_error("update apply", type(e).__name__)
