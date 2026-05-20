import dataclasses
from fastapi import APIRouter, Request, HTTPException
from .decision_recorder import list_recent, get as get_decision, list_by_agent, get_by_workflow, get_decision_recorder
from .causal_tracer import trace as causal_trace, get_causal_tracer
from .reasoning_replayer import replay
from .memory_provenance import get_provenance, record_retrieval
from .explanation_builder import build

router = APIRouter()


def _tenant(req: Request) -> str:
    return getattr(req.state, "tenant_id", None) or req.headers.get("X-Tenant-Id", "system")


@router.get("/decisions")
async def list_decisions(req: Request):
    return {"data": {"decisions": list_recent(_tenant(req))}}


@router.get("/decisions/{decision_id}")
async def get_decision_detail(decision_id: str, req: Request):
    d = get_decision(decision_id)
    if not d:
        raise HTTPException(404, "Decision not found")
    return {"data": d}


@router.get("/decisions/{decision_id}/explain")
async def explain_decision(decision_id: str, req: Request):
    report = build(decision_id, _tenant(req))
    return {"data": dataclasses.asdict(report)}


@router.get("/causal-chain/{event_id}")
async def get_causal_chain(event_id: str, req: Request):
    chain = causal_trace(event_id, _tenant(req))
    return {"data": dataclasses.asdict(chain)}


@router.get("/replay/{trace_id}")
async def replay_trace(trace_id: str):
    return {"data": replay(trace_id)}


@router.get("/provenance/{decision_id}")
async def get_memory_provenance(decision_id: str):
    return {"data": {"provenance": get_provenance(decision_id)}}


@router.get("/agent/{agent_id}")
async def agent_decisions(agent_id: str, req: Request, limit: int = 50):
    return {"data": {"decisions": list_by_agent(agent_id, limit)}}


@router.get("/workflow/{workflow_id}")
async def workflow_decisions(workflow_id: str, limit: int = 50):
    return {"data": {"decisions": get_by_workflow(workflow_id)}}


@router.post("/record")
async def record_decision(req: Request, body: dict):
    """Record a new decision with memory provenance."""
    from .schema import DecisionRecord
    from .decision_recorder import record
    try:
        decision = DecisionRecord(
            id=body.get("id"),
            tenant_id=_tenant(req),
            agent_id=body.get("agent_id", "unknown"),
            decision_type=body.get("decision_type", "action"),
            input_summary=body.get("input_summary", ""),
            output_summary=body.get("output_summary", ""),
            memories_used=body.get("memories_used", []),
            alternatives_considered=body.get("alternatives_considered", []),
            confidence=body.get("confidence", 0.8),
            workflow_id=body.get("workflow_id"),
        )
        decision_id = record(decision)
        return {"data": {"decision_id": decision_id, "ok": True}}
    except Exception as e:
        raise HTTPException(400, f"Failed to record decision: {str(e)}")
