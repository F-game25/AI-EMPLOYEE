"""FastAPI routes for Agent Marketplace — /marketplace/*"""
from __future__ import annotations
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Request, UploadFile, File
from pydantic import BaseModel

from .registry import get_registry
from .manifest_validator import validate as validate_manifest

logger = logging.getLogger(__name__)
router = APIRouter()

_MAX_PLUGIN_BYTES = 50 * 1024 * 1024  # 50 MB hard cap on plugin packages


def _tenant(req: Request) -> str:
    return getattr(req.state, "tenant_id", None) or req.headers.get("X-Tenant-Id", "system")


def _require_tenant(req: Request) -> str:
    from fastapi import HTTPException as _HTTPException
    tid = getattr(req.state, "tenant_id", None) or req.headers.get("X-Tenant-Id")
    if not tid:
        raise _HTTPException(status_code=401, detail="authentication_required")
    return tid


def _user(req: Request) -> str:
    user = getattr(req.state, "user", None)
    return (user.get("sub") or user.get("email") or "system") if user else "system"


class ApproveRequest(BaseModel):
    approved: bool
    notes: str = ""


@router.get("/plugins")
async def list_plugins(req: Request):
    return {"plugins": get_registry().list_plugins(_tenant(req))}


@router.post("/plugins/install")
async def install_plugin(req: Request, file: UploadFile = File(...)):
    tid = _require_tenant(req)
    # Stream with size cap to prevent memory exhaustion
    chunks = []
    total = 0
    async for chunk in file:
        total += len(chunk)
        if total > _MAX_PLUGIN_BYTES:
            raise HTTPException(413, f"Package exceeds {_MAX_PLUGIN_BYTES // (1024*1024)} MB limit")
        chunks.append(chunk)
    data = b"".join(chunks)
    result = get_registry().install_from_bytes(data, tid, requested_by=_user(req))
    if not result["ok"]:
        raise HTTPException(400, result.get("error", "install_failed"))
    return result


@router.get("/plugins/{plugin_id}")
async def get_plugin(plugin_id: str, req: Request):
    p = get_registry().get_plugin(plugin_id, _tenant(req))
    if not p:
        raise HTTPException(404, "plugin_not_found")
    return p


@router.delete("/plugins/{plugin_id}")
async def uninstall_plugin(plugin_id: str, req: Request):
    ok = get_registry().uninstall(plugin_id, _require_tenant(req))
    if not ok:
        raise HTTPException(404, "plugin_not_found")
    return {"ok": True}


@router.post("/plugins/{plugin_id}/enable")
async def enable_plugin(plugin_id: str, req: Request):
    ok = get_registry().enable(plugin_id, _require_tenant(req))
    if not ok:
        raise HTTPException(400, "plugin_not_installed_or_already_enabled")
    return {"ok": True}


@router.post("/plugins/{plugin_id}/disable")
async def disable_plugin(plugin_id: str, req: Request):
    ok = get_registry().disable(plugin_id, _require_tenant(req))
    if not ok:
        raise HTTPException(400, "plugin_not_enabled")
    return {"ok": True}


@router.get("/approvals")
async def list_approvals(req: Request, status: str = "pending"):
    return {"approvals": get_registry().list_approvals(_tenant(req), status)}


@router.post("/approvals/{approval_id}/approve")
async def approve(approval_id: str, req: Request, body: ApproveRequest):
    ok = get_registry().resolve_approval(approval_id, body.approved, _user(req), body.notes)
    if not ok:
        raise HTTPException(404, "approval_not_found_or_already_resolved")
    return {"ok": True, "approved": body.approved}


@router.post("/approvals/{approval_id}/reject")
async def reject(approval_id: str, req: Request):
    ok = get_registry().resolve_approval(approval_id, False, _user(req), "Rejected")
    if not ok:
        raise HTTPException(404, "approval_not_found_or_already_resolved")
    return {"ok": True, "approved": False}


@router.get("/capabilities")
async def list_capabilities(req: Request):
    return {"capabilities": get_registry().list_capabilities(_tenant(req))}


@router.post("/validate")
async def validate_package(req: Request, file: UploadFile = File(...)):
    import json, zipfile, io
    data = await file.read()
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
        manifest_data = json.loads(zf.read("manifest.json"))
    except Exception as e:
        raise HTTPException(400, f"Invalid package: {e}")
    ok, errors = validate_manifest(manifest_data)
    return {"valid": ok, "errors": errors, "manifest": manifest_data if ok else None}
