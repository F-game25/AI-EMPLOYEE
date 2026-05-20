import dataclasses
from fastapi import APIRouter, Request
from .outcome_tracker import get_recent
from .reinforcement_engine import get_all_scores, compute as compute_effectiveness
from .routing_optimizer import list_suggestions, generate_suggestions, accept
from .strategy_optimizer import get_preferences

router = APIRouter()


def _tenant(req: Request) -> str:
    return getattr(req.state, "tenant_id", None) or req.headers.get("X-Tenant-Id", "system")


@router.get("/status")
async def learning_status(req: Request):
    tid = _tenant(req)
    scores = get_all_scores(tid)
    degraded = [s for s in scores if s["score"] < 0.6]
    return {"total_agents": len(scores), "degraded": len(degraded), "tenant_id": tid}


@router.get("/outcomes")
async def get_outcomes(req: Request, agent_id: str = None):
    return {"outcomes": get_recent(_tenant(req), agent_id)}


@router.get("/effectiveness")
async def get_effectiveness(req: Request):
    return {"agents": get_all_scores(_tenant(req))}


@router.get("/routing-suggestions")
async def get_suggestions(req: Request):
    return {"suggestions": list_suggestions(_tenant(req))}


@router.post("/routing-suggestions/generate")
async def generate(req: Request):
    tid = _tenant(req)
    sug = generate_suggestions(tid)
    return {"ok": True, "generated": len(sug)}


@router.post("/routing-suggestions/{suggestion_id}/accept")
async def accept_suggestion(suggestion_id: str):
    accept(suggestion_id, True)
    return {"ok": True}


@router.post("/routing-suggestions/{suggestion_id}/reject")
async def reject_suggestion(suggestion_id: str):
    accept(suggestion_id, False)
    return {"ok": True}


@router.get("/strategy-preferences")
async def get_strategy(req: Request):
    return {"preferences": get_preferences(_tenant(req))}
