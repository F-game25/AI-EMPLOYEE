"""Executive function layer HTTP routes.

Endpoints for:
- Initiative lifecycle management (FIFO queue)
- Workload balancing and agent capacity monitoring
- Token budget tracking and enforcement
- Strategic planning (LLM-guided sequencing)
"""
import dataclasses
import logging
from fastapi import APIRouter, Request, HTTPException, status

from .schema import Initiative
from .initiative_manager import create, update, list_initiatives, get_initiative_manager
from .workload_balancer import get_workload_balancer
from .budget_tracker import get_status as budget_status
from .strategic_planner import list_decisions, plan_next

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/cognitive/executive", tags=["cognitive"])


def _tenant(req: Request) -> str:
    """Extract tenant_id from request state or headers."""
    tenant = getattr(req.state, "tenant_id", None)
    return tenant or req.headers.get("X-Tenant-Id", "system")


@router.get("/status", summary="Get executive status")
async def executive_status(req: Request):
    """Summary of active initiatives and workload."""
    try:
        tid = _tenant(req)
        inits = list_initiatives(tid)
        active = [i for i in inits if i["status"] == "active"]
        pending = [i for i in inits if i["status"] == "pending"]
        blocked = [i for i in inits if i["status"] == "blocked"]
        return {
            "tenant_id": tid,
            "active_count": len(active),
            "pending_count": len(pending),
            "blocked_count": len(blocked),
            "total_count": len(inits),
        }
    except Exception as e:
        logger.error(f"Executive status error: {e}")
        raise HTTPException(status_code=500, detail="Failed to get executive status")


@router.get("/initiatives", summary="List initiatives")
async def get_initiatives(req: Request, status_filter: str = None, limit: int = 100):
    """List initiatives for tenant, optionally filtered by status."""
    try:
        inits = list_initiatives(_tenant(req), status_filter)
        return {"initiatives": inits[:limit], "count": len(inits)}
    except Exception as e:
        logger.error(f"List initiatives error: {e}")
        raise HTTPException(status_code=500, detail="Failed to list initiatives")


@router.post("/initiatives", status_code=201, summary="Create initiative")
async def create_initiative(req: Request):
    """Create new initiative. Starts in 'pending' status."""
    try:
        body = await req.json()
        if "title" not in body:
            raise HTTPException(status_code=400, detail="title required")

        init = Initiative(
            title=body["title"],
            tenant_id=_tenant(req),
            description=body.get("description", ""),
            priority=body.get("priority", 5),
            estimated_cost_tokens=body.get("estimated_cost_tokens", 0),
            deadline=body.get("deadline"),
            dependencies=body.get("dependencies", []),
            assigned_agents=body.get("assigned_agents", []),
        )
        init_id = create(init)
        logger.info(f"Initiative created: {init_id} for tenant {_tenant(req)}")
        return {"ok": True, "id": init_id}
    except Exception as e:
        logger.error(f"Create initiative error: {e}")
        raise HTTPException(status_code=500, detail="Failed to create initiative")


@router.patch("/initiatives/{init_id}", summary="Update initiative")
async def update_initiative(init_id: str, req: Request):
    """Update initiative fields (status, priority, deadline, actual_cost_tokens)."""
    try:
        body = await req.json()
        update(init_id, **body)
        logger.info(f"Initiative {init_id} updated")
        return {"ok": True}
    except Exception as e:
        logger.error(f"Update initiative error: {e}")
        raise HTTPException(status_code=500, detail="Failed to update initiative")


@router.get("/workload", summary="Get workload state")
async def get_workload(req: Request):
    """Get per-agent queue depth, utilization, and latency metrics."""
    try:
        agents = get_workload_balancer().get_all()
        return {"agents": agents, "count": len(agents)}
    except Exception as e:
        logger.error(f"Get workload error: {e}")
        raise HTTPException(status_code=500, detail="Failed to get workload")


@router.get("/decisions", summary="List strategic decisions")
async def get_decisions(req: Request, limit: int = 20):
    """List recent executive strategic decisions."""
    try:
        decisions = list_decisions(_tenant(req), limit)
        return {"decisions": decisions, "count": len(decisions)}
    except Exception as e:
        logger.error(f"List decisions error: {e}")
        raise HTTPException(status_code=500, detail="Failed to list decisions")


@router.post("/plan", summary="Trigger strategic planning")
async def trigger_plan(req: Request):
    """Run strategic planner: rank top pending initiatives and emit decision."""
    try:
        decision = await plan_next(_tenant(req))
        if decision:
            return {"ok": True, "decision": dataclasses.asdict(decision)}
        return {"ok": True, "decision": None, "reason": "no_pending_initiatives"}
    except Exception as e:
        logger.error(f"Plan trigger error: {e}")
        raise HTTPException(status_code=500, detail="Planning failed")


@router.get("/budget", summary="Get token budget status")
async def get_budget(req: Request):
    """Get daily token budget used/limit for tenant."""
    try:
        status_dict = budget_status(_tenant(req))
        return status_dict
    except Exception as e:
        logger.error(f"Get budget error: {e}")
        raise HTTPException(status_code=500, detail="Failed to get budget status")
