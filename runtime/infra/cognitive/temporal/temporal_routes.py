from fastapi import APIRouter, Request
from .deadline_tracker import list_upcoming
from .urgency_engine import compute_urgency
from .cycle_detector import get_cycles
from .scheduling_intelligence import get_schedule
import dataclasses

router = APIRouter()


def _tenant(req: Request) -> str:
    return getattr(req.state, "tenant_id", None) or req.headers.get("X-Tenant-Id", "system")


@router.get("/status")
async def temporal_status(req: Request):
    tid = _tenant(req)
    upcoming = list_upcoming(tid, 24)
    return {"upcoming_count": len(upcoming), "tenant_id": tid}


@router.get("/deadlines")
async def get_deadlines(req: Request, hours_ahead: int = 24):
    return {"deadlines": list_upcoming(_tenant(req), hours_ahead)}


@router.get("/urgency/{initiative_id}")
async def get_urgency(initiative_id: str, req: Request):
    deadline = 0.0
    try:
        from infra.cognitive.executive.initiative_manager import list_initiatives
        inits = list_initiatives(_tenant(req))
        for i in inits:
            if i["id"] == initiative_id:
                deadline = i.get("deadline", 0.0)
                break
    except Exception:
        pass
    if not deadline:
        return {"urgency": 0.0}
    u = compute_urgency(initiative_id, 5, deadline)
    return dataclasses.asdict(u)


@router.get("/cycles")
async def get_operational_cycles(req: Request):
    return {"cycles": get_cycles(_tenant(req))}


@router.get("/schedule")
async def get_recommended_schedule(req: Request):
    try:
        from infra.cognitive.executive.initiative_manager import list_initiatives
        inits = list_initiatives(_tenant(req), "active")
        return get_schedule(inits, _tenant(req))
    except Exception:
        return {"schedule": [], "count": 0, "tenant_id": _tenant(req)}
