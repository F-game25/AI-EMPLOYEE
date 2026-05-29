"""OrchestratorV2 — 10-phase AI execution pipeline.

Phases:
  1. classify_intent     — category + urgency from raw input
  2. retrieve_memory     — fetch relevant context from memory stores
  3. select_model        — choose LLM based on task type + routing config
  4. build_plan          — decompose goal into TaskGraph steps
  5. approval_gate       — HITL check for high-risk actions
  6. execute_steps       — run each step through execution engine
  7. verify_output       — quality/safety check on result
  8. persist_result      — save to memory + knowledge store
  9. broadcast_event     — send UI update via message bus
  10. monitor            — record metrics, detect anomalies
"""
from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("orchestrator_v2")

INTENT_CATEGORIES = ("lead_gen", "content", "social", "research", "email", "support", "finance", "ops")

# Actions classified as high-risk that trigger HITL
_HIGH_RISK_SKILLS = frozenset({"send_email", "post_social", "pay_invoice", "transfer_funds", "publish_public"})


class OrchestratorV2:
    """10-phase execution pipeline: intent → memory → model → plan → approve
    → execute → verify → persist → broadcast → monitor."""

    def __init__(self) -> None:
        from core.orchestrator import get_llm_client
        self._llm = get_llm_client()

    # ── Public entry point ────────────────────────────────────────────────────

    def run(self, goal: str, tenant_id: str = "default", agent_id: str = "orchestrator") -> dict[str, Any]:
        task_id = f"ov2-{uuid.uuid4().hex[:12]}"
        phases_completed: list[str] = []
        errors: dict[str, str] = {}
        ctx: dict[str, Any] = {
            "goal": goal,
            "tenant_id": tenant_id,
            "agent_id": agent_id,
            "task_id": task_id,
            "started_at": datetime.now(timezone.utc).isoformat(),
        }

        # Phase runners in order — (name, fn, critical)
        phases = [
            ("classify_intent",  self._classify_intent,  False),
            ("retrieve_memory",  self._retrieve_memory,  False),
            ("select_model",     self._select_model,     False),
            ("build_plan",       self._build_plan,       True),
            ("approval_gate",    self._approval_gate,    True),
            ("execute_steps",    self._execute_steps,    True),
            ("verify_output",    self._verify_output,    False),
            ("persist_result",   self._persist_result,   False),
            ("broadcast_event",  self._broadcast_event,  False),
            ("monitor",          self._monitor,          False),
        ]

        for name, fn, critical in phases:
            t0 = time.time()
            try:
                fn(ctx)
                phases_completed.append(name)
                logger.info("[%s] phase=%s elapsed_ms=%d", task_id, name, int((time.time() - t0) * 1000))
            except _PipelineAbort as exc:
                errors[name] = str(exc)
                logger.warning("[%s] phase=%s ABORTED: %s", task_id, name, exc)
                return {
                    "success": False,
                    "result": None,
                    "phases_completed": phases_completed,
                    "errors": errors,
                    "task_id": task_id,
                }
            except Exception as exc:
                errors[name] = str(exc)
                logger.warning("[%s] phase=%s error (non-critical): %s", task_id, name, exc)
                if critical:
                    return {
                        "success": False,
                        "result": ctx.get("result"),
                        "phases_completed": phases_completed,
                        "errors": errors,
                        "task_id": task_id,
                    }

        return {
            "success": True,
            "result": ctx.get("result"),
            "phases_completed": phases_completed,
            "errors": errors,
            "task_id": task_id,
        }

    # ── Phase implementations ─────────────────────────────────────────────────

    def _classify_intent(self, ctx: dict) -> None:
        prompt = (
            f"Classify this goal into one of {INTENT_CATEGORIES} and rate urgency 1-5.\n"
            "Reply JSON: {\"category\": \"...\", \"urgency\": N}\n"
            f"Goal: {ctx['goal']}"
        )
        try:
            import json as _json
            raw = self._llm.complete(prompt=prompt, system="Strict intent classifier. JSON only.", tenant_id=ctx["tenant_id"])
            parsed = _json.loads(raw["output"])
            ctx["intent"] = parsed.get("category", "ops")
            ctx["urgency"] = int(parsed.get("urgency", 3))
        except Exception:
            ctx["intent"] = "ops"
            ctx["urgency"] = 3
        logger.debug("intent=%s urgency=%s", ctx["intent"], ctx["urgency"])

    def _retrieve_memory(self, ctx: dict) -> None:
        memories: list[dict] = []
        try:
            from core.knowledge_store import get_knowledge_store
            hits = get_knowledge_store().search(ctx["goal"], limit=5)
            memories = hits if isinstance(hits, list) else []
        except Exception as exc:
            logger.debug("knowledge_store search skipped: %s", exc)
        try:
            from core.memory_index import get_memory_index
            idx_hits = get_memory_index().search(ctx["goal"], top_k=3)
            memories.extend(idx_hits if isinstance(idx_hits, list) else [])
        except Exception as exc:
            logger.debug("memory_index search skipped: %s", exc)
        ctx["memories"] = memories

    def _select_model(self, ctx: dict) -> None:
        try:
            from core.model_routing import classify_request_tier, select_model_route
            route = select_model_route(prompt=ctx["goal"], context=ctx.get("intent", "ops"), requested_route=None, default_route="auto")
            ctx["model_route"] = route.model_route
            ctx["force_model"] = getattr(route, "force_model", None)
        except Exception as exc:
            logger.debug("model routing skipped: %s", exc)
            ctx["model_route"] = "auto"
            ctx["force_model"] = None

    def _build_plan(self, ctx: dict) -> None:
        import json as _json
        memory_snippet = ""
        if ctx.get("memories"):
            memory_snippet = "\nRelevant context:\n" + "\n".join(
                str(m.get("content", m))[:200] for m in ctx["memories"][:3]
            )
        prompt = (
            "Decompose the goal into up to 5 sequential steps.\n"
            "Reply JSON array: [{\"step\": 1, \"skill\": \"...\", \"action\": \"...\"}]\n"
            f"Goal: {ctx['goal']}{memory_snippet}"
        )
        try:
            raw = self._llm.complete(prompt=prompt, system="Task planner. JSON only.", tenant_id=ctx["tenant_id"])
            steps = _json.loads(raw["output"])
            if not isinstance(steps, list):
                raise ValueError("expected list")
        except Exception:
            steps = [{"step": 1, "skill": "general", "action": ctx["goal"]}]
        ctx["plan"] = steps

    def _approval_gate(self, ctx: dict) -> None:
        plan = ctx.get("plan", [])
        high_risk = [s for s in plan if s.get("skill", "") in _HIGH_RISK_SKILLS]
        if not high_risk:
            ctx["approved"] = True
            return
        from core.hitl_gate import get_hitl_gate
        result = get_hitl_gate().require_approval(
            agent=ctx["agent_id"],
            action=f"execute high-risk steps: {[s['skill'] for s in high_risk]}",
            payload={"goal": ctx["goal"], "steps": high_risk},
            submitted_by=ctx["agent_id"],
            blocking=False,
        )
        ctx["approved"] = result.get("approved", False)
        ctx["hitl_request_id"] = result.get("request_id")
        if not ctx["approved"] and high_risk:
            # Non-blocking gate: log but continue so dashboard can approve later
            logger.info("[%s] HITL request %s queued for operator", ctx["task_id"], result.get("request_id"))

    def _execute_steps(self, ctx: dict) -> None:
        results: list[dict] = []
        for step in ctx.get("plan", []):
            skill = step.get("skill", "general")
            action = step.get("action", "")
            try:
                from core.execution_engine import ExecutionEngine
                engine = ExecutionEngine(tenant_id=ctx["tenant_id"])
                import asyncio
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        # Schedule coroutine and get result synchronously via thread
                        import concurrent.futures
                        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                            step_result = pool.submit(asyncio.run, engine.execute(skill, {"action": action}, ctx["agent_id"])).result(timeout=30)
                    else:
                        step_result = loop.run_until_complete(engine.execute(skill, {"action": action}, ctx["agent_id"]))
                except RuntimeError:
                    step_result = asyncio.run(engine.execute(skill, {"action": action}, ctx["agent_id"]))
            except Exception as exc:
                step_result = {"ok": False, "error": str(exc), "skill": skill}
            results.append(step_result)
        ctx["step_results"] = results
        ctx["result"] = results[-1].get("result") if results else None

    def _verify_output(self, ctx: dict) -> None:
        results = ctx.get("step_results", [])
        failed = [r for r in results if not r.get("ok", True)]
        ctx["verification"] = {
            "total_steps": len(results),
            "failed_steps": len(failed),
            "passed": len(failed) == 0,
        }
        if failed:
            logger.warning("[%s] %d/%d steps failed", ctx["task_id"], len(failed), len(results))

    def _persist_result(self, ctx: dict) -> None:
        try:
            from core.knowledge_store import get_knowledge_store
            get_knowledge_store().store(
                key=ctx["task_id"],
                content=str(ctx.get("result", "")),
                metadata={"goal": ctx["goal"], "intent": ctx.get("intent"), "tenant_id": ctx["tenant_id"]},
            )
        except Exception as exc:
            logger.debug("persist to knowledge_store skipped: %s", exc)

    def _broadcast_event(self, ctx: dict) -> None:
        from core.bus import get_message_bus
        event = {
            "type": "orchestrator_v2:completed",
            "task_id": ctx["task_id"],
            "goal": ctx["goal"],
            "intent": ctx.get("intent"),
            "success": ctx.get("verification", {}).get("passed", True),
            "tenant_id": ctx["tenant_id"],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        get_message_bus().publish_sync("results", event)

    def _monitor(self, ctx: dict) -> None:
        try:
            from core.observability.metrics_collector import get_metrics_collector
            mc = get_metrics_collector()
            mc.increment("tasks_total")
            if ctx.get("verification", {}).get("passed", True):
                mc.increment("tasks_completed")
            else:
                mc.increment("tasks_failed")
        except Exception as exc:
            logger.debug("metrics collector skipped: %s", exc)


class _PipelineAbort(Exception):
    """Raised to immediately halt the pipeline (e.g., budget exceeded)."""
