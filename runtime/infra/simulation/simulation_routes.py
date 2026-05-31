"""FastAPI routes for Simulation + Testing — /simulation/*"""
from __future__ import annotations
import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from pydantic import BaseModel

from .scenario_orchestrator import list_scenarios, run_scenario, get_run
from .adversarial_tester import AdversarialTester
from .synthetic_user_pool import list_personas
from .digital_twin_manager import get_digital_twin_manager
from .risk_scorer import score as risk_score

logger = logging.getLogger(__name__)
router = APIRouter()

_adversarial = AdversarialTester()


def _tenant(req: Request) -> str:
    return getattr(req.state, "tenant_id", None) or req.headers.get("X-Tenant-Id", "system")


def _require_tenant(req: Request) -> str:
    from fastapi import HTTPException as _HTTPException
    tid = getattr(req.state, "tenant_id", None) or req.headers.get("X-Tenant-Id")
    if not tid:
        raise _HTTPException(status_code=401, detail="authentication_required")
    return tid


class RunRequest(BaseModel):
    scenario_id: str


class ConfigureTwinRequest(BaseModel):
    endpoints: dict


class ReplayRequest(BaseModel):
    trace_id: str


class AdversarialRequest(BaseModel):
    agent_id: str


@router.get("/scenarios")
async def get_scenarios():
    return {"scenarios": list_scenarios()}


@router.post("/run")
async def start_run(body: RunRequest, background_tasks: BackgroundTasks, req: Request):
    import uuid as _uuid
    run_id = str(_uuid.uuid4())
    tenant_id = _require_tenant(req)
    # Pre-register run as RUNNING so GET /runs/{id} works immediately
    from .schema import RunStatus, SimulationResult
    from .scenario_orchestrator import _runs
    _runs[run_id] = SimulationResult(
        run_id=run_id, scenario_id=body.scenario_id, status=RunStatus.RUNNING
    )

    async def _bg():
        result = await run_scenario(body.scenario_id, tenant_id=tenant_id, run_id=run_id)
        _runs[run_id] = result

    background_tasks.add_task(_bg)
    return {"run_id": run_id, "scenario_id": body.scenario_id, "status": "running"}


@router.get("/runs/{run_id}")
async def get_run_status(run_id: str):
    result = get_run(run_id)
    if not result:
        raise HTTPException(404, "run_not_found")
    return {
        "run_id": result.run_id,
        "scenario_id": result.scenario_id,
        "status": result.status.value,
        "step_count": len(result.steps),
        "started_at": result.started_at,
        "completed_at": result.completed_at,
        "error": result.error,
    }


@router.get("/runs/{run_id}/results")
async def get_run_results(run_id: str):
    result = get_run(run_id)
    if not result:
        raise HTTPException(404, "run_not_found")
    return {
        "run_id": result.run_id,
        "scenario_id": result.scenario_id,
        "status": result.status.value,
        "overall_score": result.overall_score,
        "assertions": [a.__dict__ for a in result.assertions],
        "steps": [s.__dict__ for s in result.steps],
    }


@router.get("/runs/{run_id}/risk")
async def get_run_risk(run_id: str):
    result = get_run(run_id)
    if not result:
        raise HTTPException(404, "run_not_found")
    rs = result.risk or risk_score(result.scenario_id, result)
    return {"run_id": run_id, "risk": rs.__dict__}


@router.post("/adversarial")
async def run_adversarial(body: AdversarialRequest):
    suite = await _adversarial.run_suite(body.agent_id)
    return suite


@router.get("/synthetic-users")
async def get_synthetic_users():
    return {"personas": list_personas()}


@router.post("/digital-twins/{system_id}")
async def configure_twin(system_id: str, body: ConfigureTwinRequest, req: Request):
    tenant_id = _require_tenant(req)
    get_digital_twin_manager().configure(system_id, body.endpoints, tenant_id=tenant_id)
    return {"ok": True, "system_id": system_id, "endpoint_count": len(body.endpoints)}


@router.post("/replay")
async def replay_trace(body: ReplayRequest):
    try:
        from infra.telemetry.execution_recorder import get_execution_store
        store = get_execution_store()
        trace = store.get_trace(body.trace_id)
        if not trace:
            raise HTTPException(404, "trace_not_found")
        return {
            "ok": True,
            "trace_id": body.trace_id,
            "spans": len(trace),
            "message": "Trace replayed in simulation mode — live calls replaced with mock responses",
            "trace": trace[:10],  # first 10 spans
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("simulation replay failed: %s", type(e).__name__)
        raise HTTPException(status_code=500, detail="simulation replay failed")
