from fastapi import APIRouter, Request
from .distributed_tracer import get_tracer
from .workflow_lineage import get_lineage_tracker
from .reasoning_lineage import get_reasoning_lineage_tracker
from .execution_heatmap import get_heatmap_aggregator
from .anomaly_correlator import get_anomaly_correlator

router = APIRouter()


def _tenant(req: Request) -> str:
    return getattr(req.state, "tenant_id", None) or req.headers.get("X-Tenant-Id", "system")


@router.get("/traces/{trace_id}")
async def get_trace(trace_id: str, req: Request):
    tracer = get_tracer()
    trace = tracer.get_trace(trace_id, _tenant(req))
    if not trace:
        return {"error": "trace_not_found"}
    return {
        "trace_id": trace.trace_id,
        "root_span_id": trace.root_span_id,
        "span_count": len(trace.spans),
        "spans": [
            {
                "id": s.id,
                "operation": s.operation_name,
                "duration_ms": s.duration_ms,
                "status": s.status,
            }
            for s in trace.spans
        ],
    }


@router.get("/lineage/{workflow_id}")
async def get_workflow_lineage(workflow_id: str, req: Request):
    tracker = get_lineage_tracker()
    ancestry = tracker.get_ancestry(workflow_id, _tenant(req))
    descendants = tracker.get_descendants_tree(workflow_id, _tenant(req))
    return {
        "workflow_id": workflow_id,
        "ancestors": ancestry,
        "descendants": descendants,
    }


@router.get("/reasoning/{trace_id}")
async def get_reasoning(trace_id: str, req: Request):
    tracker = get_reasoning_lineage_tracker()
    steps = tracker.get_trace(trace_id)
    if not steps:
        steps = tracker.get_from_neural_brain(trace_id)
    return {
        "trace_id": trace_id,
        "step_count": len(steps),
        "steps": steps,
    }


@router.get("/heatmap/{agent_id}")
async def get_agent_heatmap(agent_id: str, req: Request):
    aggregator = get_heatmap_aggregator()
    heatmap = aggregator.get_heatmap(agent_id)
    peak_hours = aggregator.get_peak_hours(agent_id)
    return {
        "agent_id": agent_id,
        "heatmap": heatmap,
        "peak_hours": peak_hours,
    }


@router.get("/anomaly-correlations")
async def get_anomaly_correlations(req: Request, limit: int = 50):
    correlator = get_anomaly_correlator()
    correlations = correlator.get_correlations(_tenant(req), limit)
    return {
        "correlations": correlations,
        "count": len(correlations),
    }


@router.get("/agent-telemetry")
async def get_agent_telemetry(req: Request):
    from ..explainability.decision_recorder import get_decision_recorder
    recorder = get_decision_recorder()
    telemetry = recorder.get_agent_telemetry(_tenant(req))
    return {"agents": telemetry}
