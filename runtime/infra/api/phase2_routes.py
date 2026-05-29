"""Phase 2 FastAPI route registrations — RAG, Planning, Economics, Governance, Telemetry.

Mount this router in the main FastAPI app:
    from infra.api.phase2_routes import phase2_router
    app.include_router(phase2_router)
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

logger = logging.getLogger("infra.phase2_routes")

phase2_router = APIRouter()


# ── Pydantic models ───────────────────────────────────────────────────────────

class RAGQueryRequest(BaseModel):
    query: str
    top_k: int = 8
    source_filter: list[str] | None = None
    rerank: bool = True
    caller_permissions: list[str] | None = None

class RAGIngestRequest(BaseModel):
    title: str = ""
    content: str
    url: str = ""
    source_type: str = "file"
    metadata: dict = Field(default_factory=dict)

class RAGSyncRequest(BaseModel):
    source_type: str
    full: bool = False

class GoalCreateRequest(BaseModel):
    title: str
    description: str = ""
    horizon: str = "quarterly"
    priority: str = "p2"
    owner_id: str = "system"
    due_at: float = 0.0
    parent_id: str | None = None
    key_results: list[dict] = Field(default_factory=list)
    milestones: list[dict] = Field(default_factory=list)
    depends_on: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    review_cadence_days: int = 7

class GoalStatusRequest(BaseModel):
    status: str

class KRUpdateRequest(BaseModel):
    current: float

class EvalRequest(BaseModel):
    task_id: str = ""
    tenant_id: str = ""
    task_type: str = "generation"
    description: str = ""
    required_capabilities: list[str] = Field(default_factory=lambda: ["text"])
    expected_input_tokens: int = 500
    expected_output_tokens: int = 200
    sla_latency_tier: str = "balanced"
    priority: str = "p2"
    business_context: dict = Field(default_factory=dict)
    hint_value_usd: float = 0.0

class RecordActualRequest(BaseModel):
    task_id: str
    tenant_id: str = ""
    model_id: str
    input_tokens: int
    output_tokens: int
    expected_value_usd: float = 0.0
    latency_ms: float = 0.0
    outcome: str = "success"
    agent_id: str = ""

class BudgetRequest(BaseModel):
    ceiling_usd: float
    tenant_id: str = ""

class ValidateRequest(BaseModel):
    agent_id: str
    task_id: str = ""
    plan: dict
    estimated_cost_usd: float = 0.0
    use_consensus: bool = False
    metadata: dict = Field(default_factory=dict)

class VetoRequest(BaseModel):
    reason: str = "manual veto"
    actor: str = "admin"


def _tenant(request: Request) -> str:
    return request.headers.get("X-Tenant-Id", "system")


def _server_error(operation: str) -> HTTPException:
    logger.warning("phase2 %s failed", operation)
    return HTTPException(status_code=500, detail=f"{operation} failed")


_ERROR_KEYS = {"error", "errors", "detail", "details", "exception", "traceback", "stack"}


def _public_stats(value) -> dict:
    if not isinstance(value, dict):
        return {"status": "completed"}
    public = {"status": str(value.get("status") or "completed")[:64]}
    for key in ("created", "updated", "deleted", "skipped", "failed", "count", "total"):
        if key in value:
            try:
                public[key] = int(value.get(key, 0) or 0)
            except (TypeError, ValueError):
                public[key] = 0
    return public


# ── RAG routes ────────────────────────────────────────────────────────────────

@phase2_router.get("/rag/status")
async def rag_status(request: Request):
    try:
        from infra.rag.sync_daemon import get_sync_daemon
        return {"ok": True, "stats": get_sync_daemon().get_stats()}
    except Exception:
        logger.warning("rag status failed")
        return {"ok": False, "error": "rag status failed"}

@phase2_router.post("/rag/query")
async def rag_query(req: RAGQueryRequest, request: Request):
    tenant_id = _tenant(request)
    try:
        from infra.rag.retrieval import get_retrieval_orchestrator
        orchestrator = get_retrieval_orchestrator(tenant_id)
        results = await orchestrator.retrieve(
            req.query, top_k=req.top_k, source_filter=req.source_filter,
            rerank=req.rerank, caller_permissions=req.caller_permissions,
        )
        return {
            "ok": True, "count": len(results),
            "context": orchestrator.format_context(results),
            "results": [
                {"text": r.chunk.text[:500], "score": r.score,
                 "source": r.source_attribution, "rerank_score": r.rerank_score}
                for r in results
            ],
        }
    except Exception:
        raise _server_error("rag query")

@phase2_router.post("/rag/sync")
async def rag_sync(req: RAGSyncRequest, request: Request):
    tenant_id = _tenant(request)
    try:
        from infra.rag.schema import SourceType
        from infra.rag.sync_daemon import get_sync_daemon
        st = SourceType(req.source_type)
        await get_sync_daemon().trigger_sync(tenant_id, st, full=req.full)
        return {"ok": True, "stats": {"status": "completed"}}
    except Exception:
        raise _server_error("rag sync")

@phase2_router.post("/rag/ingest")
async def rag_ingest(req: RAGIngestRequest, request: Request):
    tenant_id = _tenant(request)
    try:
        import hashlib
        from infra.rag.schema import SourceDocument, SourceType
        from infra.rag.pipeline import get_pipeline
        doc = SourceDocument(
            id=f"file::{tenant_id}::{uuid.uuid4()}",
            source_type=SourceType.FILE,
            source_id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            title=req.title or "Untitled",
            url=req.url,
            content_hash=hashlib.sha256(req.content.encode()).hexdigest(),
            raw_text=req.content,
            metadata=req.metadata,
            permissions=["org"],
            ingested_at=time.time(),
            modified_at=time.time(),
        )
        pipeline = get_pipeline(tenant_id)
        n = await pipeline.ingest_doc(doc)
        return {"ok": True, "chunks": n, "doc_id": doc.id}
    except Exception:
        raise _server_error("rag ingest")

@phase2_router.get("/rag/sources")
async def rag_sources(request: Request):
    try:
        from infra.rag.sync_daemon import get_sync_daemon
        daemon = get_sync_daemon()
        return {"ok": True, "sources": [
            {"tenant_id": c.tenant_id, "source_type": c.source_type.value,
             "enabled": c.enabled, "interval_s": c.effective_interval()}
            for c in daemon._configs
        ]}
    except Exception:
        logger.warning("rag sources failed")
        return {"ok": False, "error": "rag sources failed"}


# ── Planning routes ───────────────────────────────────────────────────────────

@phase2_router.post("/planning/goals")
async def create_goal(req: GoalCreateRequest, request: Request):
    tenant_id = _tenant(request)
    try:
        from infra.planning.goal_engine import get_goal_engine
        from infra.planning.schema import Horizon, Priority
        engine = get_goal_engine()
        due = req.due_at or (time.time() + 90 * 86400)
        goal = engine.create_goal(
            tenant_id=tenant_id, title=req.title, description=req.description,
            horizon=Horizon(req.horizon), priority=Priority(req.priority),
            owner_id=req.owner_id, due_at=due, parent_id=req.parent_id,
            key_results=req.key_results, milestones=req.milestones,
            depends_on=req.depends_on, tags=req.tags,
            review_cadence_days=req.review_cadence_days,
        )
        return {"ok": True, "goal": goal.to_dict()}
    except Exception:
        raise _server_error("phase2 route")

@phase2_router.get("/planning/goals")
async def list_goals(request: Request,
                     status: str | None = None,
                     horizon: str | None = None,
                     overdue: bool = False):
    tenant_id = _tenant(request)
    try:
        from infra.planning.goal_engine import get_goal_engine
        from infra.planning.schema import GoalStatus, Horizon
        engine = get_goal_engine()
        goals = engine.list_goals(
            tenant_id,
            status=GoalStatus(status) if status else None,
            horizon=Horizon(horizon) if horizon else None,
            overdue_only=overdue,
        )
        return {"ok": True, "count": len(goals), "goals": [g.to_dict() for g in goals]}
    except Exception:
        raise _server_error("phase2 route")

@phase2_router.get("/planning/goals/{goal_id}")
async def get_goal(goal_id: str, request: Request):
    tenant_id = _tenant(request)
    try:
        from infra.planning.goal_engine import get_goal_engine
        engine = get_goal_engine()
        goal = engine.get_goal(goal_id, tenant_id)
        if not goal:
            raise HTTPException(404, "Goal not found")
        return {"ok": True, "goal": goal.to_dict()}
    except HTTPException:
        raise
    except Exception:
        raise _server_error("phase2 route")

@phase2_router.patch("/planning/goals/{goal_id}/status")
async def update_goal_status(goal_id: str, req: GoalStatusRequest, request: Request):
    tenant_id = _tenant(request)
    try:
        from infra.planning.goal_engine import get_goal_engine
        from infra.planning.schema import GoalStatus
        engine = get_goal_engine()
        ok = engine.update_status(goal_id, tenant_id, GoalStatus(req.status))
        return {"ok": ok}
    except Exception:
        raise _server_error("phase2 route")

@phase2_router.patch("/planning/goals/{goal_id}/kr/{kr_id}")
async def update_kr(goal_id: str, kr_id: str, req: KRUpdateRequest, request: Request):
    tenant_id = _tenant(request)
    try:
        from infra.planning.goal_engine import get_goal_engine
        engine = get_goal_engine()
        ok = engine.update_key_result(goal_id, tenant_id, kr_id, req.current)
        return {"ok": ok}
    except Exception:
        raise _server_error("phase2 route")

@phase2_router.get("/planning/goals/{goal_id}/events")
async def goal_events(goal_id: str, request: Request):
    try:
        from infra.planning.goal_engine import get_goal_engine
        events = get_goal_engine().get_events(goal_id)
        return {"ok": True, "events": events}
    except Exception:
        raise _server_error("phase2 route")

@phase2_router.post("/planning/plan/weekly")
async def generate_weekly_plan(request: Request):
    tenant_id = _tenant(request)
    try:
        from infra.planning.strategic_planner import get_strategic_planner
        plan = await get_strategic_planner(tenant_id).generate_weekly_plan()
        return {"ok": True, "plan": plan}
    except Exception:
        raise _server_error("phase2 route")

@phase2_router.post("/planning/plan/reprioritize")
async def reprioritize(request: Request):
    tenant_id = _tenant(request)
    try:
        from infra.planning.strategic_planner import get_strategic_planner
        changes = await get_strategic_planner(tenant_id).reprioritize()
        return {"ok": True, "changes": changes}
    except Exception:
        raise _server_error("phase2 route")

@phase2_router.get("/planning/tree/{root_id}")
async def objective_tree(root_id: str, request: Request):
    tenant_id = _tenant(request)
    try:
        from infra.planning.strategic_planner import get_strategic_planner
        tree = get_strategic_planner(tenant_id).get_objective_tree(root_id)
        return {"ok": True, "tree": tree}
    except Exception:
        raise _server_error("phase2 route")


# ── Economics routes ──────────────────────────────────────────────────────────

@phase2_router.post("/economics/evaluate")
async def econ_evaluate(req: EvalRequest, request: Request):
    tenant_id = req.tenant_id or _tenant(request)
    try:
        from infra.economics.engine import get_economic_orchestrator, TaskProfile
        profile = TaskProfile(
            task_id=req.task_id or str(uuid.uuid4()),
            tenant_id=tenant_id,
            task_type=req.task_type,
            description=req.description,
            required_capabilities=req.required_capabilities,
            expected_input_tokens=req.expected_input_tokens,
            expected_output_tokens=req.expected_output_tokens,
            sla_latency_tier=req.sla_latency_tier,
            priority=req.priority,
            business_context=req.business_context,
            hint_value_usd=req.hint_value_usd,
        )
        decision = get_economic_orchestrator().evaluate(profile)
        return {"ok": True, **decision.__dict__}
    except Exception:
        raise _server_error("phase2 route")

@phase2_router.post("/economics/record")
async def econ_record(req: RecordActualRequest, request: Request):
    tenant_id = req.tenant_id or _tenant(request)
    try:
        from infra.economics.engine import get_economic_orchestrator
        cost = get_economic_orchestrator().record_actual(
            task_id=req.task_id, tenant_id=tenant_id, model_id=req.model_id,
            input_tokens=req.input_tokens, output_tokens=req.output_tokens,
            expected_value_usd=req.expected_value_usd, latency_ms=req.latency_ms,
            outcome=req.outcome, agent_id=req.agent_id,
        )
        return {"ok": True, "actual_cost_usd": round(cost, 6)}
    except Exception:
        raise _server_error("phase2 route")

@phase2_router.get("/economics/summary")
async def econ_summary(request: Request):
    tenant_id = _tenant(request)
    try:
        from infra.economics.engine import get_economic_orchestrator
        return {"ok": True, "summary": get_economic_orchestrator().get_summary(tenant_id)}
    except Exception:
        raise _server_error("phase2 route")

@phase2_router.get("/economics/costs")
async def econ_costs(request: Request):
    tenant_id = _tenant(request)
    try:
        from infra.economics.engine import get_economic_orchestrator
        return {"ok": True, "costs": get_economic_orchestrator().top_costs(tenant_id)}
    except Exception:
        raise _server_error("phase2 route")

@phase2_router.get("/economics/models")
async def econ_models():
    try:
        from infra.economics.model_pricing import get_pricing_catalog
        return {"ok": True, "models": [
            {"model_id": m.model_id, "provider": m.provider,
             "input_per_1m": m.input_per_1m, "output_per_1m": m.output_per_1m,
             "context_window": m.context_window, "latency_tier": m.latency_tier,
             "capabilities": m.capabilities}
            for m in get_pricing_catalog().all_models()
        ]}
    except Exception:
        raise _server_error("phase2 route")

@phase2_router.put("/economics/budget")
async def set_budget(req: BudgetRequest, request: Request):
    tenant_id = req.tenant_id or _tenant(request)
    try:
        from infra.economics.engine import get_economic_orchestrator
        get_economic_orchestrator().set_budget(tenant_id, req.ceiling_usd)
        return {"ok": True, "tenant_id": tenant_id, "ceiling_usd": req.ceiling_usd}
    except Exception:
        raise _server_error("phase2 route")


# ── Governance routes ─────────────────────────────────────────────────────────

@phase2_router.post("/governance/validate")
async def governance_validate(req: ValidateRequest, request: Request):
    tenant_id = _tenant(request)
    try:
        from infra.governance.validation_chain import get_validation_chain
        chain = get_validation_chain(tenant_id)
        result = await chain.validate(
            agent_id=req.agent_id,
            task_id=req.task_id or str(uuid.uuid4()),
            planner_output=req.plan,
            estimated_cost_usd=req.estimated_cost_usd,
            use_consensus=req.use_consensus,
            metadata=req.metadata,
        )
        return {
            "ok": True,
            "approved": result.approved,
            "verdict": result.final_verdict.value,
            "requires_hitl": result.requires_hitl,
            "hitl_reason": result.hitl_reason,
            "chain_id": result.chain_id,
            "total_latency_ms": round(result.total_latency_ms, 1),
            "stages": [
                {"stage": s.stage, "verdict": s.verdict.value,
                 "reason": s.reason, "confidence": s.confidence,
                 "flags": s.flags}
                for s in result.stages
            ],
        }
    except Exception:
        logger.warning("governance validate failed")
        raise _server_error("phase2 route")

@phase2_router.get("/governance/agents")
async def list_agents(request: Request):
    tenant_id = _tenant(request)
    try:
        from infra.governance.trust import get_trust_ledger
        agents = get_trust_ledger().list_agents(tenant_id)
        return {"ok": True, "agents": agents}
    except Exception:
        raise _server_error("phase2 route")

@phase2_router.get("/governance/agents/{agent_id}")
async def get_agent_trust(agent_id: str, request: Request):
    tenant_id = _tenant(request)
    try:
        from infra.governance.trust import get_trust_ledger, TRUST_VETO_THRESHOLD, TRUST_ESCALATE_THRESHOLD, TRUST_FULL_AUTONOMY
        ledger = get_trust_ledger()
        profile = ledger.get_profile(agent_id, tenant_id)
        events = ledger.get_events(agent_id, tenant_id)
        score = profile.get("trust_score", 0.5)
        level = "vetoed" if score < TRUST_VETO_THRESHOLD else \
                "restricted" if score < TRUST_ESCALATE_THRESHOLD else \
                "supervised" if score < TRUST_FULL_AUTONOMY else "full_autonomy"
        return {"ok": True, "profile": profile, "trust_level": level, "events": events}
    except Exception:
        raise _server_error("phase2 route")

@phase2_router.post("/governance/agents/{agent_id}/veto")
async def veto_agent(agent_id: str, req: VetoRequest, request: Request):
    tenant_id = _tenant(request)
    try:
        from infra.governance.trust import get_trust_ledger
        get_trust_ledger().record_veto(agent_id, tenant_id, req.reason)
        score = get_trust_ledger().get_score(agent_id, tenant_id)
        return {"ok": True, "agent_id": agent_id, "new_score": score}
    except Exception:
        raise _server_error("phase2 route")

@phase2_router.get("/governance/trust/stats")
async def trust_stats(request: Request):
    tenant_id = _tenant(request)
    try:
        from infra.governance.trust import get_trust_ledger, TRUST_VETO_THRESHOLD, TRUST_ESCALATE_THRESHOLD, TRUST_FULL_AUTONOMY
        agents = get_trust_ledger().list_agents(tenant_id)
        scores = [a["trust_score"] for a in agents]
        return {
            "ok": True,
            "total_agents": len(agents),
            "avg_trust": round(sum(scores) / len(scores), 3) if scores else 0,
            "vetoed": sum(1 for s in scores if s < TRUST_VETO_THRESHOLD),
            "restricted": sum(1 for s in scores if TRUST_VETO_THRESHOLD <= s < TRUST_ESCALATE_THRESHOLD),
            "supervised": sum(1 for s in scores if TRUST_ESCALATE_THRESHOLD <= s < TRUST_FULL_AUTONOMY),
            "full_autonomy": sum(1 for s in scores if s >= TRUST_FULL_AUTONOMY),
        }
    except Exception:
        raise _server_error("phase2 route")


# ── Telemetry routes ──────────────────────────────────────────────────────────

@phase2_router.get("/telemetry/traces")
async def list_traces(request: Request,
                      agent_id: str | None = None,
                      status: str | None = None,
                      limit: int = 50):
    tenant_id = _tenant(request)
    try:
        from infra.telemetry.execution_recorder import get_execution_store
        records = get_execution_store().query(
            tenant_id=tenant_id, agent_id=agent_id, status=status, limit=limit,
        )
        return {"ok": True, "count": len(records), "records": records}
    except Exception:
        raise _server_error("phase2 route")

@phase2_router.get("/telemetry/traces/{trace_id}")
async def get_trace(trace_id: str):
    try:
        from infra.telemetry.execution_recorder import get_execution_store
        records = get_execution_store().get_trace(trace_id)
        return {"ok": True, "trace_id": trace_id, "records": records}
    except Exception:
        raise _server_error("phase2 route")

@phase2_router.get("/telemetry/lineage/{record_id}")
async def get_lineage(record_id: str):
    try:
        from infra.telemetry.execution_recorder import get_execution_store
        lineage = get_execution_store().get_lineage(record_id)
        return {"ok": True, "record_id": record_id, "lineage": lineage}
    except Exception:
        raise _server_error("phase2 route")

@phase2_router.get("/telemetry/spans")
async def get_otel_spans():
    try:
        from infra.telemetry.otel import get_in_memory_spans
        return {"ok": True, "spans": get_in_memory_spans()}
    except Exception:
        raise _server_error("phase2 route")

@phase2_router.post("/telemetry/replay/{trace_id}")
async def replay_trace(trace_id: str):
    try:
        from infra.telemetry.execution_recorder import get_execution_store
        records = get_execution_store().get_trace(trace_id)
        if not records:
            raise HTTPException(404, "Trace not found")
        # Replay = reconstruct decision tree + return annotated record
        replay = {
            "trace_id": trace_id,
            "record_count": len(records),
            "timeline": sorted(records, key=lambda r: r.get("started_at", 0)),
            "decision_tree": [
                d for r in records for d in r.get("decisions", [])
            ],
            "token_summary": {
                "total_input": sum(u["input_tokens"] for r in records for u in r.get("token_usage", [])),
                "total_output": sum(u["output_tokens"] for r in records for u in r.get("token_usage", [])),
                "total_cost_usd": sum(r.get("total_cost_usd", 0) for r in records),
            },
        }
        return {"ok": True, "replay": replay}
    except HTTPException:
        raise
    except Exception:
        raise _server_error("phase2 route")

@phase2_router.get("/telemetry/anomalies")
async def get_anomalies(request: Request, limit: int = 20):
    tenant_id = _tenant(request)
    try:
        from infra.telemetry.execution_recorder import get_execution_store, get_anomaly_detector
        store = get_execution_store()
        detector = get_anomaly_detector()
        records = store.query(tenant_id=tenant_id, limit=limit)
        anomalies = []
        for r_dict in records:
            # Reconstruct minimal record for anomaly check
            flags = []
            dur = r_dict.get("duration_ms", 0)
            cost = r_dict.get("total_cost_usd", 0)
            if dur > 60000:
                flags.append(f"slow_execution:{dur:.0f}ms")
            if cost > 5:
                flags.append(f"high_cost:${cost:.2f}")
            if r_dict.get("status") == "failure":
                flags.append("execution_failed")
            if flags:
                anomalies.append({"record_id": r_dict["record_id"], "task_id": r_dict.get("task_id"),
                                   "agent_id": r_dict.get("agent_id"), "flags": flags})
        return {"ok": True, "anomalies": anomalies}
    except Exception:
        raise _server_error("phase2 route")

@phase2_router.get("/telemetry/decisions/{task_id}")
async def get_decisions(task_id: str, request: Request):
    tenant_id = _tenant(request)
    try:
        from infra.telemetry.execution_recorder import get_execution_store
        records = get_execution_store().query(tenant_id=tenant_id, task_id=task_id, limit=10)
        all_decisions = [d for r in records for d in r.get("decisions", [])]
        return {"ok": True, "task_id": task_id, "decisions": all_decisions}
    except Exception:
        raise _server_error("phase2 route")
