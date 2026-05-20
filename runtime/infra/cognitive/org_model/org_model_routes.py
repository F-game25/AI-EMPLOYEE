from fastapi import APIRouter, Request, HTTPException
from .org_topology import get_topology, upsert
from .dependency_graph import get_graph, record_sequence
from .user_profiler import get_profile
from .operational_modeler import get_all_models, get_model, get_summary
from .schema import OrgNode

router = APIRouter()


def _tenant(req: Request) -> str:
    return getattr(req.state, "tenant_id", None) or req.headers.get("X-Tenant-Id", "system")


@router.get("/topology")
async def org_topology(req: Request):
    return {"data": get_topology(_tenant(req))}


@router.get("/workflows")
async def workflow_deps(req: Request):
    return {"data": get_graph(_tenant(req))}


@router.get("/user/{user_id}")
async def user_profile(user_id: str, req: Request):
    return {"data": get_profile(user_id, _tenant(req))}


@router.get("/agents")
async def agent_models(req: Request):
    return {"data": {"agents": get_all_models(_tenant(req))}}


@router.get("/snapshot")
async def org_snapshot(req: Request):
    tid = _tenant(req)
    return {
        "data": {
            "topology": get_topology(tid),
            "workflow_deps": get_graph(tid),
            "agent_models": get_all_models(tid),
        }
    }


@router.post("/node")
async def create_org_node(req: Request, body: dict):
    """Create or update an organizational node (agent, team, etc)."""
    try:
        node = OrgNode(
            name=body.get("name", "unknown"),
            tenant_id=_tenant(req),
            role=body.get("role", "agent"),
            node_type=body.get("node_type", "agent"),
            reports_to=body.get("reports_to"),
            metadata=body.get("metadata", {}),
        )
        node_id = upsert(node)
        return {"data": {"node_id": node_id, "ok": True}}
    except Exception as e:
        raise HTTPException(400, f"Failed to create node: {str(e)}")


@router.post("/workflow-edge")
async def record_workflow_edge(req: Request, body: dict):
    """Record a workflow dependency edge."""
    try:
        source = body.get("source", "")
        target = body.get("target", "")
        gap_s = body.get("gap_s", 0.0)
        if not source or not target:
            raise HTTPException(400, "source and target required")
        record_sequence(source, target, _tenant(req), gap_s)
        return {"data": {"ok": True}}
    except Exception as e:
        raise HTTPException(400, f"Failed to record workflow edge: {str(e)}")


@router.get("/agent/{agent_id}")
async def get_agent_model(agent_id: str, req: Request):
    model = get_model(agent_id, _tenant(req))
    if not model:
        raise HTTPException(404, "Agent model not found")
    return {"data": model}


@router.get("/summary")
async def org_summary(req: Request):
    return {"data": get_summary(_tenant(req))}
