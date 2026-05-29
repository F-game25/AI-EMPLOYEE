import dataclasses
from fastapi import APIRouter, Request
from .identity_manager import get_or_create, increment_interaction
from .relationship_memory import get_context
from .habit_recognizer import get_habits
from .proactive_engine import list_insights, dismiss
from .communication_adapter import get_profile

router = APIRouter()


def _tenant(req: Request) -> str:
    return getattr(req.state, "tenant_id", None) or req.headers.get("X-Tenant-Id", "system")


@router.get("/identity")
async def get_identity(req: Request):
    identity = get_or_create(_tenant(req))
    return dataclasses.asdict(identity)


@router.get("/relationship/{user_id}")
async def relationship(user_id: str, req: Request):
    return get_context(user_id, _tenant(req))


@router.get("/habits/{user_id}")
async def get_user_habits(user_id: str, req: Request):
    return {"habits": get_habits(user_id, _tenant(req))}


@router.get("/insights")
async def get_insights(req: Request):
    return {"insights": list_insights(_tenant(req))}


@router.post("/insights/{insight_id}/dismiss")
async def dismiss_insight(insight_id: str):
    dismiss(insight_id)
    return {"ok": True}


@router.get("/communication-profile/{user_id}")
async def comm_profile(user_id: str, req: Request):
    return get_profile(user_id, _tenant(req))
