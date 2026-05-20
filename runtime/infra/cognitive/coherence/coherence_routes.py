"""Coherence cognitive infrastructure HTTP routes.

Endpoints for:
- Coherence scoring (consistency, dedup, loop-free)
- Objective hierarchy management
- Contradiction detection and resolution
- Loop detection
- Workflow deduplication
"""
from fastapi import APIRouter, Request, HTTPException, status
import dataclasses
import logging

from .schema import ObjectiveNode
from .objective_hierarchy import add_objective, list_objectives, update_status, get_priority_stack
from .contradiction_detector import list_contradictions, resolve_contradiction
from .loop_detector import get_loop_detector
from .deduplication_engine import list_active, cleanup_expired
from .coherence_scorer import compute as compute_score

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/cognitive/coherence", tags=["cognitive"])


def _tenant(req: Request) -> str:
    """Extract tenant_id from request state or headers."""
    tenant = getattr(req.state, "tenant_id", None)
    return tenant or req.headers.get("X-Tenant-Id", "system")


@router.get("/status", summary="Get coherence score")
async def coherence_status(req: Request):
    """Compute composite coherence score for tenant.

    Returns: {overall, consistency_score, dedup_score, loop_free_score}
    """
    try:
        score = compute_score(_tenant(req))
        return dataclasses.asdict(score)
    except Exception as e:
        logger.error(f"Coherence score error: {e}")
        raise HTTPException(status_code=500, detail="Failed to compute coherence score")


@router.get("/objectives", summary="List objectives")
async def get_objectives(req: Request, status_filter: str = None, limit: int = 100):
    """List objectives for tenant, optionally filtered by status."""
    try:
        objs = list_objectives(_tenant(req), status_filter)
        return {"objectives": objs[:limit], "count": len(objs)}
    except Exception as e:
        logger.error(f"List objectives error: {e}")
        raise HTTPException(status_code=500, detail="Failed to list objectives")


@router.get("/objectives/priority-stack", summary="Get priority stack")
async def get_objective_stack(req: Request):
    """Get active objectives ordered by priority (highest first)."""
    try:
        stack = get_priority_stack(_tenant(req))
        return {"stack": stack, "count": len(stack)}
    except Exception as e:
        logger.error(f"Priority stack error: {e}")
        raise HTTPException(status_code=500, detail="Failed to get priority stack")


@router.post("/objectives", status_code=201, summary="Create objective")
async def create_objective(req: Request):
    """Create new objective for tenant."""
    try:
        body = await req.json()
        if "title" not in body:
            raise HTTPException(status_code=400, detail="title required")

        obj = ObjectiveNode(
            title=body["title"],
            tenant_id=_tenant(req),
            description=body.get("description", ""),
            priority=body.get("priority", 5),
            parent_id=body.get("parent_id"),
            source_agent=body.get("source_agent"),
        )
        obj_id = add_objective(obj)
        logger.info(f"Objective created: {obj_id} for tenant {_tenant(req)}")
        return {"ok": True, "id": obj_id}
    except Exception as e:
        logger.error(f"Create objective error: {e}")
        raise HTTPException(status_code=500, detail="Failed to create objective")


@router.patch("/objectives/{obj_id}", summary="Update objective status")
async def set_objective_status(obj_id: str, req: Request):
    """Update objective status (active, completed, archived)."""
    try:
        body = await req.json()
        status_val = body.get("status", "archived")
        update_status(obj_id, status_val)
        logger.info(f"Objective {obj_id} status -> {status_val}")
        return {"ok": True}
    except Exception as e:
        logger.error(f"Update objective error: {e}")
        raise HTTPException(status_code=500, detail="Failed to update objective")


@router.get("/contradictions", summary="List contradictions")
async def get_contradictions(req: Request, resolved: bool = False, limit: int = 50):
    """List detected contradictions, optionally filtered by resolution status."""
    try:
        conts = list_contradictions(_tenant(req), resolved, limit)
        return {"contradictions": conts, "count": len(conts)}
    except Exception as e:
        logger.error(f"List contradictions error: {e}")
        raise HTTPException(status_code=500, detail="Failed to list contradictions")


@router.post("/contradictions/{cont_id}/resolve", summary="Resolve contradiction")
async def resolve(cont_id: str, req: Request):
    """Mark contradiction as resolved with optional resolution text."""
    try:
        body = await req.json()
        resolution = body.get("resolution", "manual")
        resolve_contradiction(cont_id, resolution)
        logger.info(f"Contradiction {cont_id} resolved: {resolution}")
        return {"ok": True}
    except Exception as e:
        logger.error(f"Resolve contradiction error: {e}")
        raise HTTPException(status_code=500, detail="Failed to resolve contradiction")


@router.get("/loops", summary="List detected loops")
async def get_loops(req: Request):
    """Get list of detected autonomy loops in current window."""
    try:
        loops = get_loop_detector().get_detected()
        tenant = _tenant(req)
        tenant_loops = [l for l in loops if l.get("tenant") == tenant]
        return {"loops": tenant_loops, "count": len(tenant_loops)}
    except Exception as e:
        logger.error(f"List loops error: {e}")
        raise HTTPException(status_code=500, detail="Failed to list loops")


@router.get("/duplicates", summary="List active duplicates")
async def get_duplicates(req: Request, limit: int = 100):
    """Get list of active workflow fingerprints (dedup state)."""
    try:
        dups = list_active(_tenant(req))
        return {"duplicates": dups[:limit], "count": len(dups)}
    except Exception as e:
        logger.error(f"List duplicates error: {e}")
        raise HTTPException(status_code=500, detail="Failed to list duplicates")


@router.post("/cleanup", summary="Cleanup expired state")
async def cleanup(req: Request):
    """Force cleanup of expired fingerprints and old records."""
    try:
        count = cleanup_expired()
        logger.info(f"Cleanup: {count} expired fingerprints removed")
        return {"ok": True, "cleaned": count}
    except Exception as e:
        logger.error(f"Cleanup error: {e}")
        raise HTTPException(status_code=500, detail="Cleanup failed")
