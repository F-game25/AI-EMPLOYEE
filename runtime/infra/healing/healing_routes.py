"""FastAPI routes for self-healing — /healing/*"""
from __future__ import annotations
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from .circuit_breaker import get_circuit_registry
from .health_scorer import score_service
from .anomaly_isolator import get_anomaly_isolator
from .predictive_detector import get_predictive_detector
from .recovery_orchestrator import get_recovery_orchestrator

logger = logging.getLogger(__name__)
router = APIRouter()


def _tenant(req: Request) -> str:
    return getattr(req.state, "tenant_id", None) or req.headers.get("X-Tenant-Id", "system")


class QuarantineRequest(BaseModel):
    reason: str = "manual_quarantine"


class InjectFailureRequest(BaseModel):
    count: int = 6


@router.get("/status")
async def system_health_status():
    hs = score_service("ai_backend")
    cb = get_circuit_registry().list_all()
    return {
        "health_score": hs.score,
        "latency_score": hs.latency_score,
        "error_score": hs.error_score,
        "cpu_score": hs.cpu_score,
        "circuits": cb,
        "computed_at": hs.computed_at,
    }


@router.get("/agents")
async def list_agents(req: Request):
    tid = _tenant(req)
    quarantined = get_anomaly_isolator().list_quarantined(tid)
    circuits = {c["service"]: c for c in get_circuit_registry().list_all()}
    return {"quarantined": quarantined, "circuits": circuits}


@router.post("/agents/{agent_id}/quarantine")
async def quarantine_agent(agent_id: str, req: Request, body: QuarantineRequest):
    evt = get_anomaly_isolator().quarantine(agent_id, _tenant(req), body.reason)
    return {"ok": True, "event": evt.__dict__}


@router.post("/agents/{agent_id}/restore")
async def restore_agent(agent_id: str, req: Request):
    ok = get_anomaly_isolator().restore(agent_id, _tenant(req))
    if not ok:
        raise HTTPException(404, "agent_not_quarantined")
    return {"ok": True}


@router.get("/circuits")
async def list_circuits():
    return {"circuits": get_circuit_registry().list_all()}


@router.post("/circuits/{service}/reset")
async def reset_circuit(service: str):
    get_circuit_registry().force_closed(service)
    return {"ok": True, "service": service, "state": "closed"}


@router.get("/events")
async def get_events(limit: int = 50):
    return {"events": get_recovery_orchestrator().get_events(limit)}


@router.post("/simulate")
async def inject_failure(req: Request, body: InjectFailureRequest):
    # Accept service from query param
    service = req.query_params.get("service", "ai_backend")
    result = get_recovery_orchestrator().inject_failure(service, body.count)
    return result


@router.get("/predictions")
async def get_predictions(limit: int = 20):
    return {"predictions": get_predictive_detector().get_predictions(limit)}
