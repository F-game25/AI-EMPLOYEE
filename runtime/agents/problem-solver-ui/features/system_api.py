"""Mode Manager & Change Log API endpoints."""
from __future__ import annotations

import logging
import sys
from pathlib import Path
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

router = APIRouter(prefix="/api", tags=["system"])
_log = logging.getLogger(__name__)


def _sanitize_task_response(task_dict: dict) -> dict:
    """Build a safe response dict — error field is always redacted to prevent stack trace exposure."""
    # Construct a new dict from scratch with only the safe fields
    safe = {}
    for key, value in task_dict.items():
        if key == "error":
            # Never forward raw error strings — they may contain stack traces
            raw = value or ""
            if raw:
                first_line = str(raw).split("\n")[0]
                safe["error"] = first_line if first_line and "Traceback" not in first_line else "Task processing error"
            else:
                safe["error"] = ""
        else:
            safe[key] = value
    return safe


# Ensure runtime/ packages are importable from within features/
_RUNTIME_DIR = Path(__file__).parent.parent.parent.parent
for _p in [
    str(_RUNTIME_DIR),
    str(_RUNTIME_DIR / "core"),
    str(_RUNTIME_DIR / "actions"),
    str(_RUNTIME_DIR / "memory"),
    str(_RUNTIME_DIR / "brain"),
]:
    if _p not in sys.path:
        sys.path.insert(0, _p)


# ── Mode endpoints ─────────────────────────────────────────────────────────────

@router.get("/mode")
def get_mode():
    """Return the current operating mode."""
    try:
        from core.mode_manager import get_mode_manager
        return JSONResponse(get_mode_manager().status())
    except Exception:
        _log.exception("get_mode failed")
        return JSONResponse({"mode": "MANUAL", "error": "Unable to read mode"})


class SetModeRequest(BaseModel):
    mode: str


@router.post("/mode")
def set_mode(body: SetModeRequest):
    """Set the operating mode (AUTO / MANUAL / BLACKLIGHT)."""
    try:
        from core.mode_manager import get_mode_manager
        new_mode = get_mode_manager().set_mode(body.mode)
        return JSONResponse({"mode": new_mode, "status": "ok"})
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid mode value")
    except Exception:
        _log.exception("set_mode failed")
        raise HTTPException(status_code=500, detail="Internal server error")


# ── Change log endpoints ───────────────────────────────────────────────────────

@router.get("/changelog")
def get_changelog(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """Return paginated change log entries (newest first)."""
    try:
        from core.change_log import get_changelog as _get_changelog
        log = _get_changelog()
        entries = log.read(limit=limit, offset=offset)
        total = log.total()
        return JSONResponse({
            "total": total,
            "limit": limit,
            "offset": offset,
            "entries": entries,
        })
    except Exception:
        _log.exception("get_changelog failed")
        return JSONResponse({"total": 0, "entries": [], "error": "Unable to read changelog"})


# ── ActionBus approval endpoints ──────────────────────────────────────────────

@router.get("/actions/pending")
def list_pending_actions():
    """List actions awaiting human approval (MANUAL mode)."""
    try:
        from actions.action_bus import get_action_bus
        return JSONResponse({"pending": get_action_bus().list_pending()})
    except Exception:
        _log.exception("list_pending_actions failed")
        return JSONResponse({"pending": [], "error": "Unable to list pending actions"})


@router.get("/actions/metrics")
def action_metrics():
    """Execution metrics for secure actions (global + per-action breakdown)."""
    try:
        from actions.action_bus import get_action_bus
        return JSONResponse({"metrics": get_action_bus().metrics()})
    except Exception:
        _log.exception("action_metrics failed")
        return JSONResponse({"metrics": {}, "error": "Unable to read action metrics"})


@router.post("/actions/{action_id}/approve")
def approve_action(action_id: str):
    """Approve a pending action."""
    try:
        from actions.action_bus import get_action_bus
        return JSONResponse(get_action_bus().approve(action_id))
    except Exception:
        _log.exception("approve_action failed")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/actions/{action_id}/reject")
def reject_action(action_id: str):
    """Reject a pending action."""
    try:
        from actions.action_bus import get_action_bus
        return JSONResponse(get_action_bus().reject(action_id))
    except Exception:
        _log.exception("reject_action failed")
        raise HTTPException(status_code=500, detail="Internal server error")


# ── Skill registry ────────────────────────────────────────────────────────────

@router.get("/skills")
def list_skills(category: str | None = None):
    """Return the unified skill manifest."""
    try:
        from core.skill_registry import get_registry
        registry = get_registry()
        if category:
            skills = registry.list_skills(category=category)
            return JSONResponse({"category": category, "skills": skills})
        return JSONResponse(registry.to_json())
    except Exception:
        _log.exception("list_skills failed")
        return JSONResponse({"skills": [], "error": "Unable to load skill registry"})


# ── Task engine ───────────────────────────────────────────────────────────────

class RunGoalRequest(BaseModel):
    goal: str


@router.post("/tasks/run")
def run_goal(body: RunGoalRequest):
    """Run a goal through the central controller pipeline."""
    try:
        from api.contracts import normalize_task_response
        from core.agent_controller import get_agent_controller
        result = get_agent_controller().run_goal(body.goal)
        return JSONResponse(normalize_task_response(result))
    except Exception:
        _log.exception("run_goal failed")
        raise HTTPException(status_code=500, detail="Internal server error")


def _brain_status_payload() -> dict:
    try:
        import server as _server  # type: ignore

        if hasattr(_server, "_load_brain"):
            _brain = _server._load_brain()
            if _brain is None:
                if hasattr(_server, "_brain_fallback_status"):
                    payload = dict(_server._brain_fallback_status())
                else:
                    # Neural network not loaded — registry still provides
                    # strategy selection and learning, so report as active.
                    payload = {"available": True}
            else:
                payload = dict(_brain.stats())
                cfg = getattr(_brain, "cfg", {})
                payload.update(
                    {
                        "available": True,
                        "cfg_input_size": cfg.get("model", {}).get("input_size"),
                        "cfg_output_size": cfg.get("model", {}).get("output_size"),
                        "cfg_hidden": str(cfg.get("model", {}).get("hidden_sizes", "")),
                        "cfg_batch_size": cfg.get("training", {}).get("batch_size"),
                        "cfg_update_freq": cfg.get("training", {}).get("update_frequency"),
                    }
                )
            from core.brain_registry import brain as _brain_registry

            payload["status"] = "active"
            payload["memory_size"] = _brain_registry.memory_size()
            payload["last_updated"] = _brain_registry.last_updated()
            payload["recent_learning_events"] = _brain_registry.insights().get("recent_learning_events", [])
            return payload
    except Exception:
        pass

    from core.brain_registry import brain as _brain_registry

    return _brain_registry.status()


@router.get("/brain/status")
def brain_status():
    """Return global brain status for UI visibility."""
    try:
        return JSONResponse(_brain_status_payload())
    except Exception:
        _log.exception("brain_status failed")
        return JSONResponse({"status": "active", "available": True, "memory_size": 0, "mode": "ONLINE", "error": "Brain status load failed; showing default state"})


@router.get("/brain/insights")
def brain_insights():
    """Return brain learning/decision insights."""
    try:
        from core.brain_registry import brain as _brain_registry

        return JSONResponse(_brain_registry.insights())
    except Exception:
        _log.exception("brain_insights failed")
        return JSONResponse({"active": True, "recent_learning_events": [], "performance_metrics": {}, "error": "Brain insights load failed; showing default state"})


@router.get("/brain/knowledge")
def brain_knowledge(query: str = Query("", min_length=0)):
    """Return learned knowledge topics and optional search hits."""
    try:
        from core.knowledge_store import get_knowledge_store

        store = get_knowledge_store()
        snap = store.snapshot()
        return JSONResponse(
            {
                "topics": snap.get("topics", {}),
                "user_profile": snap.get("user_profile", {}),
                "hits": store.search_knowledge(query) if query else [],
            }
        )
    except Exception:
        _log.exception("brain_knowledge failed")
        return JSONResponse({"topics": {}, "user_profile": {}, "hits": [], "error": "Knowledge store unavailable"})


@router.post("/brain/learn-topic")
def brain_learn_topic(body: dict):
    """Ingest research knowledge for a requested topic prompt.

    Preferred request field: ``topic``.
    Backward-compatible fallback: ``prompt``.
    """
    try:
        from core.research_agent import ResearchAgent

        prompt = str(body.get("topic") or body.get("prompt") or "").strip()
        if not prompt:
            raise HTTPException(status_code=400, detail="topic is required")
        result = ResearchAgent().learn_topic(prompt)
        return JSONResponse({"ok": True, "result": result})
    except HTTPException:
        raise
    except Exception:
        _log.exception("brain_learn_topic failed")
        return JSONResponse({"ok": False, "result": {}, "error": "Unable to learn topic"})


@router.get("/tasks/recent")
def recent_tasks(limit: int = Query(20, ge=1, le=100)):
    """Return recent task log entries."""
    try:
        from core.task_engine import get_task_engine
        return JSONResponse({"tasks": get_task_engine().recent_runs(limit=limit)})
    except Exception:
        _log.exception("recent_tasks failed")
        return JSONResponse({"tasks": [], "error": "Unable to read task log"})


# ── Money mode ────────────────────────────────────────────────────────────────

class ContentPipelineRequest(BaseModel):
    topic: str
    platforms: list[str] = ["twitter"]
    affiliate_product: str = ""
    dry_run: bool = False


@router.post("/money/content-pipeline")
def run_content_pipeline(body: ContentPipelineRequest):
    """Run the content generation pipeline."""
    try:
        from core.money_mode import get_money_mode
        result = get_money_mode().run_content_pipeline(
            topic=body.topic,
            platforms=body.platforms,
            affiliate_product=body.affiliate_product,
            dry_run=body.dry_run,
        )
        return JSONResponse(result)
    except Exception:
        _log.exception("run_content_pipeline failed")
        raise HTTPException(status_code=500, detail="Internal server error")


class AffiliateDraftRequest(BaseModel):
    product: str
    niche: str
    output_format: str = "blog_post"


@router.post("/money/affiliate-draft")
def affiliate_draft(body: AffiliateDraftRequest):
    """Draft affiliate content for review (not auto-published)."""
    try:
        from core.money_mode import get_money_mode
        result = get_money_mode().affiliate_content_draft(
            product=body.product,
            niche=body.niche,
            output_format=body.output_format,
        )
        return JSONResponse(result)
    except Exception:
        _log.exception("affiliate_draft failed")
        raise HTTPException(status_code=500, detail="Internal server error")


class LeadPipelineRequest(BaseModel):
    source: str
    audience: str
    channels: list[str] = ["email"]
    dry_run: bool = False


@router.post("/money/lead-pipeline")
def run_lead_pipeline(body: LeadPipelineRequest):
    """Run data scraping → lead filtering → storage pipeline."""
    try:
        from core.money_mode import get_money_mode
        result = get_money_mode().run_lead_pipeline(
            source=body.source,
            audience=body.audience,
            channels=body.channels,
            dry_run=body.dry_run,
        )
        return JSONResponse(result)
    except Exception:
        _log.exception("run_lead_pipeline failed")
        raise HTTPException(status_code=500, detail="Internal server error")


class OpportunityPipelineRequest(BaseModel):
    opportunity: str
    budget: float = 0.0
    dry_run: bool = False


@router.post("/money/opportunity-pipeline")
def run_opportunity_pipeline(body: OpportunityPipelineRequest):
    """Run outreach → response tracking → conversion pipeline."""
    try:
        from core.money_mode import get_money_mode
        result = get_money_mode().run_opportunity_pipeline(
            opportunity=body.opportunity,
            budget=body.budget,
            dry_run=body.dry_run,
        )
        return JSONResponse(result)
    except Exception:
        _log.exception("run_opportunity_pipeline failed")
        raise HTTPException(status_code=500, detail="Internal server error")


class AutomationControlRequest(BaseModel):
    action: str
    goal: str = "Execute monetization cycle"
    override_action_id: str = ""


@router.post("/automation/control")
def control_automation(body: AutomationControlRequest):
    """Start/stop automation cycles and allow manual override operations."""
    action = body.action.lower().strip()
    try:
        from core.mode_manager import get_mode_manager
        mode = get_mode_manager().current_mode
        if action == "start":
            if mode == "MANUAL":
                return JSONResponse({
                    "status": "blocked",
                    "reason": "Switch to AUTO or BLACKLIGHT to start autonomous execution.",
                })
            from core.agent_controller import get_agent_controller
            result = get_agent_controller().run_goal(body.goal)
            return JSONResponse({"status": "started", "mode": mode, "result": result})
        if action == "stop":
            return JSONResponse({
                "status": "stopped",
                "mode": mode,
                "message": "Automation stop acknowledged. New runs are paused by operator intent.",
            })
        if action == "override":
            if not body.override_action_id:
                raise HTTPException(status_code=400, detail="override_action_id required for override")
            from actions.action_bus import get_action_bus
            decision = get_action_bus().approve(body.override_action_id)
            return JSONResponse({"status": "override_applied", "decision": decision})
        raise HTTPException(status_code=400, detail="Unsupported action. Use start, stop, or override.")
    except HTTPException:
        raise
    except Exception:
        _log.exception("control_automation failed")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/memory/insights")
def memory_insights(goal_type: str = Query("general")):
    """Expose local-first learning insights from historical outcomes."""
    try:
        from memory.strategy_store import get_strategy_store
        store = get_strategy_store()
        return JSONResponse({
            "goal_type": goal_type,
            "insights": store.learn_for_goal(goal_type),
            "summary": store.performance_summary(goal_type=goal_type),
        })
    except Exception:
        _log.exception("memory_insights failed")
        return JSONResponse({
            "goal_type": goal_type,
            "insights": {"insight": "Unable to read local memory."},
            "summary": {"total_attempts": 0, "success_rate": 0.0},
        })


@router.get("/product/dashboard")
def product_dashboard(
    task_limit: int = Query(12, ge=1, le=100),
    roi_limit: int = Query(12, ge=1, le=200),
):
    """Consolidated product metrics for a user-facing AI Employee dashboard."""
    response: dict = {
        "mode": {},
        "tasks": {"tasks_executed": 0, "success_rate": 0.0},
        "revenue": {"total_revenue": 0.0, "events": 0},
        "value": {"value_generated": 0.0, "revenue_component": 0.0, "pipeline_component": 0.0},
        "top_skills": [],
        "top_strategies": [],
        "activity_feed": [],
        "execution_logs": [],
        "pipelines": {"runs": 0, "success_rate": 0.0, "pipelines": []},
        "learning": {},
    }
    try:
        from core.mode_manager import get_mode_manager
        response["mode"] = get_mode_manager().status()
    except Exception:
        pass
    try:
        from core.task_engine import get_task_engine
        engine = get_task_engine()
        response["tasks"] = engine.daily_stats()
        response["execution_logs"] = engine.recent_runs(limit=task_limit)
        response["top_skills"] = engine.top_skills(limit=5)
    except Exception:
        pass
    try:
        from core.roi_tracker import get_roi_tracker
        tracker = get_roi_tracker()
        response["revenue"] = tracker.daily_summary()
        response["activity_feed"] = tracker.recent(limit=roi_limit)
    except Exception:
        pass
    try:
        from memory.strategy_store import get_strategy_store
        store = get_strategy_store()
        response["top_strategies"] = store.top_performers(limit=5)
        response["learning"] = store.performance_summary(limit=5)
    except Exception:
        pass
    try:
        from core.pipeline_store import get_pipeline_store
        pstore = get_pipeline_store()
        response["pipelines"] = pstore.overview()
        response["pipeline_runs"] = pstore.recent_runs(limit=6)
    except Exception:
        pass
    try:
        from actions.action_bus import get_action_bus
        response["pending_actions"] = get_action_bus().list_pending()
    except Exception:
        response["pending_actions"] = []
    try:
        from core.self_improvement.telemetry import get_telemetry
        response["self_improvement"] = get_telemetry().dashboard_payload().get(
            "self_improvement", {}
        )
    except Exception:
        response["self_improvement"] = {"active": False}
    try:
        from core.self_improvement.learning import LearningModule
        response["improvement_learning"] = LearningModule().get_insights()
    except Exception:
        response["improvement_learning"] = {}
    response["value"] = {
        "revenue_component": round(float(response.get("revenue", {}).get("total_revenue", 0.0) or 0.0), 3),
        "pipeline_component": round(float(response.get("pipelines", {}).get("total_estimated_roi", 0.0) or 0.0), 3),
        "value_generated": round(
            float(response.get("revenue", {}).get("total_revenue", 0.0) or 0.0)
            + float(response.get("pipelines", {}).get("total_estimated_roi", 0.0) or 0.0),
            3,
        ),
    }
    return JSONResponse(response)


# ── Self-Improvement Loop endpoints ───────────────────────────────────────────

class _ImprovementTaskRequest(BaseModel):
    description: str
    target_area: str = "general"
    constraints: list[str] = []
    risk_class: str = "medium"
    approval_policy: str = "manual"


@router.post("/self-improvement/queue")
def si_queue_task(body: _ImprovementTaskRequest):
    """Queue a new self-improvement task."""
    try:
        from core.self_improvement.queue import get_queue
        task = get_queue().enqueue(
            description=body.description,
            target_area=body.target_area,
            constraints=body.constraints,
            risk_class=body.risk_class,
            approval_policy=body.approval_policy,
        )
        return JSONResponse(_sanitize_task_response(task.to_dict()))
    except Exception as exc:
        _log.exception("si_queue_task failed")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/self-improvement/queue")
def si_list_queue(status: str = Query(default="")):
    """List all tasks in the improvement queue."""
    try:
        from core.self_improvement.queue import get_queue
        return JSONResponse(get_queue().list_all(status=status or None))
    except Exception as exc:
        _log.exception("si_list_queue failed")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/self-improvement/queue/summary")
def si_queue_summary():
    """Return queue summary for dashboard."""
    try:
        from core.self_improvement.queue import get_queue
        return JSONResponse(get_queue().summary())
    except Exception as exc:
        _log.exception("si_queue_summary failed")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/self-improvement/task/{task_id}")
def si_get_task(task_id: str):
    """Get a specific improvement task with all artifacts."""
    try:
        from core.self_improvement.queue import get_queue
        task = get_queue().get(task_id)
        if task is None:
            raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
        return JSONResponse(_sanitize_task_response(task.to_dict()))
    except HTTPException:
        raise
    except Exception as exc:
        _log.exception("si_get_task failed")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/self-improvement/task/{task_id}/run")
def si_run_task(task_id: str):
    """Run the full improvement pipeline for a queued task."""
    try:
        from core.self_improvement.queue import get_queue
        from core.self_improvement.controller import get_controller
        queue = get_queue()
        task = queue.get(task_id)
        if task is None:
            raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
        controller = get_controller()
        result = controller.run_pipeline(task)
        queue.update(result)
        return JSONResponse(_sanitize_task_response(result.to_dict()))
    except HTTPException:
        raise
    except Exception as exc:
        _log.exception("si_run_task failed")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/self-improvement/task/{task_id}/approve")
def si_approve_task(task_id: str):
    """Manually approve a task awaiting approval."""
    try:
        from core.self_improvement.queue import get_queue
        from core.self_improvement.controller import get_controller
        queue = get_queue()
        task = queue.get(task_id)
        if task is None:
            raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
        controller = get_controller()
        result = controller.approve_task(task)
        queue.update(result)
        return JSONResponse(_sanitize_task_response(result.to_dict()))
    except HTTPException:
        raise
    except Exception as exc:
        _log.exception("si_approve_task failed")
        raise HTTPException(status_code=500, detail="Internal server error")


class _RejectRequest(BaseModel):
    reason: str = ""


@router.post("/self-improvement/task/{task_id}/reject")
def si_reject_task(task_id: str, body: _RejectRequest = _RejectRequest()):
    """Manually reject a task awaiting approval."""
    try:
        from core.self_improvement.queue import get_queue
        from core.self_improvement.controller import get_controller
        queue = get_queue()
        task = queue.get(task_id)
        if task is None:
            raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
        controller = get_controller()
        result = controller.reject_task(task, reason=body.reason)
        queue.update(result)
        return JSONResponse(_sanitize_task_response(result.to_dict()))
    except HTTPException:
        raise
    except Exception as exc:
        _log.exception("si_reject_task failed")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/self-improvement/task/{task_id}/deploy")
def si_deploy_task(task_id: str):
    """Deploy an approved task."""
    try:
        from core.self_improvement.queue import get_queue
        from core.self_improvement.controller import get_controller
        queue = get_queue()
        task = queue.get(task_id)
        if task is None:
            raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
        controller = get_controller()
        result = controller.deploy_approved(task)
        queue.update(result)
        return JSONResponse(_sanitize_task_response(result.to_dict()))
    except HTTPException:
        raise
    except Exception as exc:
        _log.exception("si_deploy_task failed")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/self-improvement/task/{task_id}/rollback")
def si_rollback_task(task_id: str):
    """Rollback a deploying/deployed task."""
    try:
        from core.self_improvement.queue import get_queue
        from core.self_improvement.controller import get_controller
        queue = get_queue()
        task = queue.get(task_id)
        if task is None:
            raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
        controller = get_controller()
        result = controller.rollback_task(task)
        queue.update(result)
        return JSONResponse(_sanitize_task_response(result.to_dict()))
    except HTTPException:
        raise
    except Exception as exc:
        _log.exception("si_rollback_task failed")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/self-improvement/telemetry")
def si_telemetry():
    """Return self-improvement telemetry for the dashboard."""
    try:
        from core.self_improvement.telemetry import get_telemetry
        return JSONResponse(get_telemetry().dashboard_payload())
    except Exception as exc:
        _log.exception("si_telemetry failed")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/self-improvement/learning")
def si_learning_insights():
    """Return learning insights from the improvement feedback loop."""
    try:
        from core.self_improvement.learning import LearningModule
        return JSONResponse(LearningModule().get_insights())
    except Exception as exc:
        _log.exception("si_learning_insights failed")
        raise HTTPException(status_code=500, detail="Internal server error")


# ── Autonomy daemon & system mode endpoints ────────────────────────────────────

class SystemModeBody(BaseModel):
    mode: str  # "OFF" | "ON" | "AUTO"


@router.get("/autonomy/mode")
def get_autonomy_mode():
    """Return the current system autonomy mode."""
    try:
        from core.system_mode import get_system_mode
        return JSONResponse(get_system_mode().status())
    except Exception as exc:
        _log.exception("get_autonomy_mode failed")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/autonomy/mode")
def set_autonomy_mode(body: SystemModeBody):
    """Set the system autonomy mode (OFF / ON / AUTO)."""
    try:
        from core.system_mode import get_system_mode
        sm = get_system_mode()
        new_mode = sm.set_mode(body.mode)
        return JSONResponse(sm.status())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid mode value")
    except Exception as exc:
        _log.exception("set_autonomy_mode failed")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/autonomy/emergency-stop")
def emergency_stop():
    """Immediately halt all autonomous execution."""
    try:
        from core.system_mode import get_system_mode
        from core.autonomy_daemon import get_daemon
        sm = get_system_mode()
        sm.emergency_stop()
        daemon = get_daemon()
        daemon.stop()
        return JSONResponse({
            "status": "stopped",
            "message": "Emergency stop executed. Daemon halted, mode set to OFF.",
            **sm.status(),
        })
    except Exception as exc:
        _log.exception("emergency_stop failed")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/autonomy/status")
def get_autonomy_status():
    """Return full autonomy daemon status for the dashboard."""
    try:
        from core.autonomy_daemon import get_daemon
        return JSONResponse(get_daemon().status())
    except Exception as exc:
        _log.exception("get_autonomy_status failed")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/autonomy/start")
def start_daemon():
    """Start the autonomy daemon background loop."""
    try:
        from core.autonomy_daemon import get_daemon
        daemon = get_daemon()
        daemon.start()
        return JSONResponse(daemon.status())
    except Exception as exc:
        _log.exception("start_daemon failed")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/autonomy/stop")
def stop_daemon():
    """Gracefully stop the autonomy daemon."""
    try:
        from core.autonomy_daemon import get_daemon
        daemon = get_daemon()
        daemon.stop()
        return JSONResponse(daemon.status())
    except Exception as exc:
        _log.exception("stop_daemon failed")
        raise HTTPException(status_code=500, detail="Internal server error")
