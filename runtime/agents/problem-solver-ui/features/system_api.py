"""Mode Manager & Change Log API endpoints."""
from __future__ import annotations

import sys
from pathlib import Path
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

router = APIRouter(prefix="/api", tags=["system"])

# Ensure runtime/ packages are importable from within features/
_RUNTIME_DIR = Path(__file__).parent.parent.parent.parent
for _p in [
    str(_RUNTIME_DIR),
    str(_RUNTIME_DIR / "core"),
    str(_RUNTIME_DIR / "actions"),
    str(_RUNTIME_DIR / "memory"),
]:
    if _p not in sys.path:
        sys.path.insert(0, _p)


# ── Mode endpoints ─────────────────────────────────────────────────────────────

@router.get("/mode")
def get_mode():
    """Return the current operating mode."""
    try:
        from core.mode_manager import get_mode_manager
        return JSONResponse(get_mode_manager().status())
    except Exception as exc:
        return JSONResponse({"mode": "MANUAL", "error": str(exc)})


class SetModeRequest(BaseModel):
    mode: str


@router.post("/mode")
def set_mode(body: SetModeRequest):
    """Set the operating mode (AUTO / MANUAL / BLACKLIGHT)."""
    try:
        from core.mode_manager import get_mode_manager
        new_mode = get_mode_manager().set_mode(body.mode)
        return JSONResponse({"mode": new_mode, "status": "ok"})
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── Change log endpoints ───────────────────────────────────────────────────────

@router.get("/changelog")
def get_changelog(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """Return paginated change log entries (newest first)."""
    try:
        from core.change_log import get_changelog as _get_changelog
        log = _get_changelog()
        entries = log.read(limit=limit, offset=offset)
        total = log.total()
        return JSONResponse({
            "total": total,
            "limit": limit,
            "offset": offset,
            "entries": entries,
        })
    except Exception as exc:
        return JSONResponse({"total": 0, "entries": [], "error": str(exc)})


# ── ActionBus approval endpoints ──────────────────────────────────────────────

@router.get("/actions/pending")
def list_pending_actions():
    """List actions awaiting human approval (MANUAL mode)."""
    try:
        from actions.action_bus import get_action_bus
        return JSONResponse({"pending": get_action_bus().list_pending()})
    except Exception as exc:
        return JSONResponse({"pending": [], "error": str(exc)})


@router.post("/actions/{action_id}/approve")
def approve_action(action_id: str):
    """Approve a pending action."""
    try:
        from actions.action_bus import get_action_bus
        return JSONResponse(get_action_bus().approve(action_id))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/actions/{action_id}/reject")
def reject_action(action_id: str):
    """Reject a pending action."""
    try:
        from actions.action_bus import get_action_bus
        return JSONResponse(get_action_bus().reject(action_id))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── Skill registry ────────────────────────────────────────────────────────────

@router.get("/skills")
def list_skills(category: str | None = None):
    """Return the unified skill manifest."""
    try:
        from core.skill_registry import get_registry
        registry = get_registry()
        if category:
            skills = registry.list_skills(category=category)
            return JSONResponse({"category": category, "skills": skills})
        return JSONResponse(registry.to_json())
    except Exception as exc:
        return JSONResponse({"skills": [], "error": str(exc)})


# ── Task engine ───────────────────────────────────────────────────────────────

class RunGoalRequest(BaseModel):
    goal: str


@router.post("/tasks/run")
def run_goal(body: RunGoalRequest):
    """Run a goal through the 3-layer task engine (plan → execute → validate)."""
    try:
        from core.task_engine import get_task_engine
        result = get_task_engine().run_goal(body.goal)
        return JSONResponse(result)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/tasks/recent")
def recent_tasks(limit: int = Query(20, ge=1, le=100)):
    """Return recent task log entries."""
    try:
        from core.task_engine import get_task_engine
        return JSONResponse({"tasks": get_task_engine().recent_runs(limit=limit)})
    except Exception as exc:
        return JSONResponse({"tasks": [], "error": str(exc)})


# ── Money mode ────────────────────────────────────────────────────────────────

class ContentPipelineRequest(BaseModel):
    topic: str
    platforms: list[str] = ["twitter"]
    affiliate_product: str = ""
    dry_run: bool = False


@router.post("/money/content-pipeline")
def run_content_pipeline(body: ContentPipelineRequest):
    """Run the content generation pipeline."""
    try:
        from core.money_mode import get_money_mode
        result = get_money_mode().run_content_pipeline(
            topic=body.topic,
            platforms=body.platforms,
            affiliate_product=body.affiliate_product,
            dry_run=body.dry_run,
        )
        return JSONResponse(result)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


class AffiliateDraftRequest(BaseModel):
    product: str
    niche: str
    output_format: str = "blog_post"


@router.post("/money/affiliate-draft")
def affiliate_draft(body: AffiliateDraftRequest):
    """Draft affiliate content for review (not auto-published)."""
    try:
        from core.money_mode import get_money_mode
        result = get_money_mode().affiliate_content_draft(
            product=body.product,
            niche=body.niche,
            output_format=body.output_format,
        )
        return JSONResponse(result)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
