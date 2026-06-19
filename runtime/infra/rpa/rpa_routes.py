"""FastAPI routes for RPA / browser control — /rpa/*"""
from __future__ import annotations
import base64
import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from .schema import BrowserAction, ActionType
from .session_manager import get_session_manager
from .replay_recorder import ReplayRecorder

logger = logging.getLogger(__name__)
router = APIRouter()

_MAX_WORKFLOW_ACTIONS = 500   # hard cap per workflow submission
_MAX_SESSIONS_PER_TENANT = 20 # prevent resource exhaustion


def _tenant(req: Request) -> str:
    return getattr(req.state, "tenant_id", None) or req.headers.get("X-Tenant-Id", "system")


def _require_tenant(req: Request) -> str:
    """Like _tenant() but raises 401 when no authenticated identity is present."""
    from fastapi import HTTPException as _HTTPException
    tid = getattr(req.state, "tenant_id", None) or req.headers.get("X-Tenant-Id")
    if not tid:
        raise _HTTPException(status_code=401, detail="authentication_required")
    return tid


def _require_computer_use() -> None:
    """Master Computer-Use switch — 403 unless enabled from the UI.

    Gates the side-effecting RPA doors (spawn + action) so the toggle governs
    both the companion's browser capabilities and the standalone RPA API.
    """
    try:
        from companion.computer_use_mode import computer_use_enabled
        on = computer_use_enabled()
    except Exception:  # noqa: BLE001 — fail safe → treat as off
        on = False
    if not on:
        raise HTTPException(
            status_code=403,
            detail="computer_use_disabled: enable Computer Use mode from the UI",
        )


# ── Pydantic models ──────────────────────────────────────────────────────────

class SpawnRequest(BaseModel):
    browser_type: str = "chromium"
    tags: dict = {}


class ActionRequest(BaseModel):
    type: str
    selector: Optional[str] = None
    value: Optional[str] = None
    timeout_ms: int = 5000
    verify: bool = True
    description: Optional[str] = None


class WorkflowRequest(BaseModel):
    actions: list[ActionRequest]


class SaveWorkflowRequest(BaseModel):
    name: str
    description: str = ""
    actions: list[dict]


# ── Session endpoints ────────────────────────────────────────────────────────

@router.post("/sessions")
async def spawn_session(req: Request, body: SpawnRequest):
    tid = _require_tenant(req)
    _require_computer_use()
    mgr = get_session_manager()
    active = [s for s in mgr.list_sessions(tid) if s.get("status") == "active"]
    if len(active) >= _MAX_SESSIONS_PER_TENANT:
        raise HTTPException(429, f"Max {_MAX_SESSIONS_PER_TENANT} concurrent sessions per tenant")
    try:
        session = await mgr.spawn(tid, body.browser_type, body.tags)
        return {"ok": True, "session": {
            "session_id": session.session_id,
            "status": session.status.value,
            "browser_type": session.browser_type,
            "cdp_ws_url": session.cdp_ws_url,
            "tags": session.tags,
        }}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sessions")
async def list_sessions(req: Request):
    return {"sessions": get_session_manager().list_sessions(_tenant(req))}


@router.delete("/sessions/{session_id}")
async def terminate_session(session_id: str, req: Request):
    ok = await get_session_manager().terminate(session_id, _require_tenant(req))
    if not ok:
        raise HTTPException(404, "session_not_found")
    return {"ok": True}


@router.post("/sessions/{session_id}/action")
async def execute_action(session_id: str, req: Request, body: ActionRequest):
    tid = _require_tenant(req)
    _require_computer_use()
    action = BrowserAction(
        type=ActionType(body.type),
        selector=body.selector,
        value=body.value,
        timeout_ms=body.timeout_ms,
        verify=body.verify,
        description=body.description,
    )
    result = await get_session_manager().execute_action(session_id, tid, action)
    return {
        "ok": result.ok,
        "action": result.action.value if hasattr(result.action, "value") else str(result.action),
        "value_extracted": result.value_extracted,
        "error": result.error,
        "duration_ms": result.duration_ms,
        "before_hash": result.before_hash,
        "after_hash": result.after_hash,
    }


@router.post("/sessions/{session_id}/workflow")
async def execute_workflow(session_id: str, req: Request, body: WorkflowRequest):
    if len(body.actions) > _MAX_WORKFLOW_ACTIONS:
        raise HTTPException(400, f"Workflow exceeds {_MAX_WORKFLOW_ACTIONS} action limit")
    tid = _require_tenant(req)
    actions = [BrowserAction(
        type=ActionType(a.type), selector=a.selector, value=a.value,
        timeout_ms=a.timeout_ms, verify=a.verify,
    ) for a in body.actions]
    results = await get_session_manager().execute_workflow(session_id, tid, actions)
    return {
        "ok": all(r.ok for r in results),
        "results": [{"ok": r.ok, "action": r.action.value if hasattr(r.action, "value") else str(r.action),
                     "error": r.error, "duration_ms": r.duration_ms} for r in results],
    }


@router.post("/sessions/{session_id}/takeover")
async def takeover(session_id: str, req: Request):
    token = await get_session_manager().takeover(session_id, _require_tenant(req))
    if not token:
        raise HTTPException(404, "session_not_found_or_no_cdp")
    return {"ok": True, "cdp_url": token.cdp_url, "expires_at": token.expires_at}


@router.get("/sessions/{session_id}/screenshot")
async def get_screenshot(session_id: str, req: Request):
    buf = await get_session_manager().screenshot(session_id, _tenant(req))
    if buf is None:
        raise HTTPException(404, "session_not_found_or_no_page")
    return {"ok": True, "png_base64": base64.b64encode(buf).decode()}


@router.get("/sessions/{session_id}/replay")
async def get_replay(session_id: str, req: Request):
    session = await get_session_manager().get_session(session_id, _tenant(req))
    if not session:
        raise HTTPException(404, "session_not_found")
    rec = ReplayRecorder(_tenant(req), session_id)
    frames = rec.read_frames()
    return {"ok": True, "frame_count": len(frames),
            "frames": [f.__dict__ for f in frames]}


# ── Workflow endpoints ───────────────────────────────────────────────────────

@router.post("/workflows")
async def save_workflow(req: Request, body: SaveWorkflowRequest):
    wf = get_session_manager().save_workflow(
        _require_tenant(req), body.name, body.description, body.actions)
    return {"ok": True, "workflow_id": wf.workflow_id}


@router.get("/workflows")
async def list_workflows(req: Request):
    return {"workflows": get_session_manager().list_workflows(_tenant(req))}


@router.post("/workflows/{workflow_id}/run")
async def run_workflow(workflow_id: str, req: Request, body: SpawnRequest):
    tid = _require_tenant(req)
    mgr = get_session_manager()
    wf = mgr.get_workflow(workflow_id, tid)
    if not wf:
        raise HTTPException(404, "workflow_not_found")
    session = await mgr.spawn(tid, body.browser_type, body.tags)
    actions = [BrowserAction(
        type=ActionType(a["type"]),
        selector=a.get("selector"),
        value=a.get("value"),
        timeout_ms=a.get("timeout_ms", 5000),
        verify=a.get("verify", True),
    ) for a in wf.actions]
    results = await mgr.execute_workflow(session.session_id, tid, actions)
    return {
        "ok": all(r.ok for r in results),
        "session_id": session.session_id,
        "results": [{"ok": r.ok, "error": r.error} for r in results],
    }
