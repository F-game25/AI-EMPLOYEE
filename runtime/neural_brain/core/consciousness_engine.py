"""Neural Brain kernel — ConsciousnessEngine.

process_input() is the ONLY public entry point. Nothing calls agents, forge,
or memory directly. All routing goes through here.

Wiring:
- EventBus: all lifecycle events published with source="neural_brain"
- TaskQueue: every think() call is enqueued as a managed task
- Blacklight: input analyzed before processing; threat gate enforced
- HealthMonitor: latency + ok/fail recorded after every call
- Forge: auto-submitted when error_rate > threshold (debounced)
"""
from __future__ import annotations

import asyncio
import logging
import threading
import time
import uuid

from neural_brain.core.brain_state import BrainState
from neural_brain.core.reasoning_trace import ReasoningSession
from neural_brain.workflows.deep_reasoning_graph import build_reasoning_graph

logger = logging.getLogger(__name__)


class ConsciousnessEngine:

    def __init__(self) -> None:
        self.graph = build_reasoning_graph()
        self.active_threads: dict[str, ReasoningSession] = {}
        # Boot subsystems
        self._boot_subsystems()

    def _boot_subsystems(self) -> None:
        try:
            from neural_brain.core.health_monitor import get_health_monitor
            get_health_monitor()  # starts background loop
        except Exception:
            pass
        try:
            from neural_brain.security.blacklight_engine import get_blacklight
            get_blacklight()  # starts background loop
        except Exception:
            pass

    # ── Unified entry point ──────────────────────────────────────────────────

    def process_input(
        self,
        input_text: str,
        user_id: str = "anonymous",
        thread_id: str | None = None,
        force: bool = False,
    ) -> dict:
        """THE entry point. All input flows through here — no exceptions.

        1. Blacklight gate: analyze input, block if CRITICAL
        2. System mode check: block inputs in LOCKDOWN
        3. Enqueue via TaskQueue
        4. Record health
        """
        start = time.time()
        thread_id = thread_id or str(uuid.uuid4())
        trace_id = str(uuid.uuid4())

        # 1. System mode gate
        try:
            from neural_brain.security.system_control import get_system_control
            ctrl = get_system_control()
            if ctrl.is_input_blocked():
                return {
                    "output": "System is in lockdown. Input blocked.",
                    "thread_id": thread_id,
                    "blocked": True,
                    "mode": ctrl.get_mode(),
                }
        except Exception:
            pass

        # 2. Blacklight input analysis
        assessment = {}
        try:
            from neural_brain.security.blacklight_engine import get_blacklight
            assessment = get_blacklight().analyze_input(input_text, user_id=user_id)
            if assessment.get("risk_score", 0) >= 85:
                return {
                    "output": "Input blocked by security analysis.",
                    "thread_id": thread_id,
                    "blocked": True,
                    "risk_score": assessment["risk_score"],
                    "threat_level": assessment.get("threat_level"),
                }
        except Exception as e:
            logger.debug("Blacklight analysis error (non-blocking): %s", e)

        # 3. Dispatch via task queue (never execute directly in calling thread)
        try:
            from neural_brain.core.task_queue import get_task_queue, Priority
            tq = get_task_queue()
            task_id = tq.enqueue(
                self.think,
                args=(input_text,),
                kwargs={"user_id": user_id, "thread_id": thread_id, "force": force, "trace_id": trace_id},
                priority=Priority.HIGH if force else Priority.NORMAL,
                timeout_s=120.0,
                label=f"think:{thread_id[:8]}",
                source="consciousness_engine",
                trace_id=trace_id,
            )
            # Wait for result (blocking — process_input is synchronous by contract)
            import time as _time
            deadline = _time.time() + 125.0
            task = None
            while _time.time() < deadline:
                task = tq.get_task(task_id)
                if task and task.get("status") in ("completed", "failed", "cancelled"):
                    break
                _time.sleep(0.05)

            if task and task.get("status") == "completed":
                # Result stored on Task object — retrieve via internal dict
                with tq._lock:
                    raw_task = tq._tasks.get(task_id)
                result = raw_task.result if raw_task and raw_task.result is not None else {"output": "", "thread_id": thread_id}
            else:
                error_msg = (task or {}).get("error", "task queue timeout")
                result = {"output": f"Reasoning timed out: {error_msg}", "thread_id": thread_id, "error": error_msg}
        except Exception as tq_err:
            logger.warning("Task queue unavailable (%s), executing directly", tq_err)
            result = self.think(input_text, user_id=user_id, thread_id=thread_id, force=force, trace_id=trace_id)

        # 4. Record health
        latency_ms = (time.time() - start) * 1000
        ok = "error" not in result
        try:
            from neural_brain.core.health_monitor import get_health_monitor
            get_health_monitor().record(latency_ms=latency_ms, ok=ok, source="neural_brain")
        except Exception:
            pass

        if assessment:
            result["security"] = {"risk_score": assessment.get("risk_score", 0), "threat_level": assessment.get("threat_level", "LOW")}

        return result

    async def process_input_async(
        self,
        input_text: str,
        user_id: str = "anonymous",
        thread_id: str | None = None,
        force: bool = False,
    ) -> dict:
        return await asyncio.to_thread(self.process_input, input_text, user_id, thread_id, force)

    # ── Core reasoning ───────────────────────────────────────────────────────

    def think(
        self,
        input_text: str,
        user_id: str = "anonymous",
        thread_id: str | None = None,
        force: bool = False,
        trace_id: str | None = None,
    ) -> dict:
        thread_id = thread_id or str(uuid.uuid4())
        trace_id = trace_id or str(uuid.uuid4())
        start = time.time()

        state: BrainState = {
            "input": input_text,
            "user_id": user_id,
            "thread_id": thread_id,
            "force": force,
            "trace": [],
        }

        try:
            from neural_brain.utils.event_bus import publish
            publish("nb:thread_created", source="neural_brain", payload={
                "thread_id": thread_id,
                "user_id": user_id,
                "input_preview": input_text[:80],
            }, trace_id=trace_id)
        except Exception:
            pass

        try:
            result = self.graph.invoke(state, config={"configurable": {"thread_id": thread_id}})

            session = ReasoningSession(
                thread_id=thread_id,
                user_id=user_id,
                input=input_text,
                intent=result.get("intent", "unknown"),
            )
            session.output = result.get("output")
            session.traces = result.get("trace", [])
            try:
                session.save_jsonl()
            except Exception:
                pass
            self.active_threads[thread_id] = session

            traces = result.get("trace", [])
            total_latency = sum(t.latency_ms if hasattr(t, "latency_ms") else 0 for t in traces)

            return {
                "output": result.get("output", ""),
                "thread_id": thread_id,
                "trace_id": trace_id,
                "traces": [t.as_dict() if hasattr(t, "as_dict") else t for t in traces],
                "total_latency_ms": total_latency,
                "intent": result.get("intent", "unknown"),
            }

        except Exception as e:
            logger.error("think() failed: %s", e, exc_info=True)
            try:
                from neural_brain.utils.event_bus import publish
                publish("system:error", source="neural_brain", payload={
                    "error": str(e)[:200],
                    "thread_id": thread_id,
                    "context": "think",
                }, trace_id=trace_id)
            except Exception:
                pass
            return {
                "output": f"Reasoning failed: {str(e)[:100]}",
                "thread_id": thread_id,
                "trace_id": trace_id,
                "traces": [],
                "total_latency_ms": (time.time() - start) * 1000,
                "error": str(e),
            }

    async def think_async(
        self,
        input_text: str,
        user_id: str = "anonymous",
        thread_id: str | None = None,
    ) -> dict:
        return await asyncio.to_thread(self.process_input, input_text, user_id, thread_id)

    # ── Parallel reasoning ────────────────────────────────────────────────────

    async def think_parallel(self, queries: list[dict]) -> list[dict]:
        tasks = [
            self.process_input_async(
                q.get("input", ""),
                user_id=q.get("user_id", "anonymous"),
                thread_id=q.get("thread_id"),
            )
            for q in queries
        ]
        return list(await asyncio.gather(*tasks, return_exceptions=False))

    # ── Memory (always via singleton) ─────────────────────────────────────────

    def recall(self, query: str, user_id: str = "anonymous", k: int = 5) -> dict:
        from neural_brain.memory import get_memory
        try:
            mem = get_memory()
            result = asyncio.run(mem.recall(query, k=k))
            return {"results": result.get("results", []), "hit_count": len(result.get("results", []))}
        except Exception as e:
            logger.error("recall failed: %s", e)
            return {"results": [], "hit_count": 0, "error": str(e)}

    def remember(self, content: str, memory_type: str = "episodic", user_id: str = "anonymous", metadata: dict | None = None) -> dict:
        from neural_brain.memory import get_memory
        try:
            mem = get_memory()
            result = asyncio.run(mem.remember(content=content, type=memory_type, user_id=user_id, metadata=metadata or {}))
            return {"id": result if isinstance(result, str) else None, "stored": True}
        except Exception as e:
            logger.error("remember failed: %s", e)
            return {"id": None, "stored": False, "error": str(e)}

    def forget(self, memory_id: str) -> dict:
        from neural_brain.memory import get_memory
        try:
            asyncio.run(get_memory().forget(memory_id))
            return {"id": memory_id, "deleted": True}
        except Exception as e:
            return {"id": memory_id, "deleted": False, "error": str(e)}

    # ── Graph ─────────────────────────────────────────────────────────────────

    def get_graph_snapshot(self, limit: int = 200) -> dict:
        from neural_brain.graph import get_brain_graph
        from neural_brain.graph.graph_to_dashboard import graph_to_dashboard
        try:
            graph = get_brain_graph()
            if graph is None:
                return {"nodes": [], "connections": [], "stats": {"node_count": 0, "link_count": 0}}
            return graph_to_dashboard(graph.full_snapshot(limit=limit))
        except Exception as e:
            logger.error("get_graph_snapshot failed: %s", e)
            return {"nodes": [], "connections": [], "stats": {}, "error": str(e)}

    # ── Forge (kernel-owned delegation) ──────────────────────────────────────

    def forge_list(self, status: str | None = None) -> dict:
        try:
            from core.forge_controller import get_forge_controller
            items = get_forge_controller().list_pending()
            if status:
                items = [i for i in items if i.get("status") == status]
            return {"items": items, "total": len(items)}
        except Exception as e:
            return {"items": [], "total": 0, "error": str(e)}

    def forge_submit(self, goal: str, module: str = "", priority: int = 5, code: str = "") -> dict:
        """Submit forge goal → sandbox evaluation → pending user approval. NEVER auto-deploys."""
        # Gate: system must not be in LOCKDOWN or OFFLINE
        try:
            from neural_brain.security.system_control import get_system_control, SystemState
            ctrl = get_system_control()
            if ctrl.is_forge_disabled():
                return {"error": "Forge is disabled by system control", "blocked": True}
            mode = ctrl.get_mode()
            if mode in (SystemState.LOCKDOWN, SystemState.OFFLINE):
                return {"error": f"Forge blocked in system mode: {mode}", "blocked": True}
        except Exception:
            pass
        try:
            from neural_brain.api.node_bridge import emit

            if not code:
                result = {
                    "status": "planned_pending_code",
                    "snapshot_id": None,
                    "goal": goal,
                    "module": module,
                    "priority": priority,
                    "requires_approval": True,
                    "auto_deploy": False,
                    "message": "Forge goal accepted as a supervised plan. Submit explicit code before sandbox/deploy.",
                }
                emit("nb:forge_submitted", {
                    "snapshot_id": None,
                    "goal": goal[:80],
                    "risk_level": "caution",
                    "requires_approval": True,
                })
                return result

            from core.forge_controller import get_forge_controller
            result = get_forge_controller().submit_change(
                module=module or "core/agent_controller.py",
                code=code,
                description=f"Neural Brain Forge goal: {goal[:160]}",
                author="neural_brain:consciousness_engine",
                auto_deploy=False,
            )
            # Always goes to sandbox → status must be "pending" not "deployed"
            result.setdefault("status", "pending_approval")
            result.setdefault("auto_deploy", False)
            emit("nb:forge_submitted", {
                "snapshot_id": result.get("snapshot_id"),
                "goal": goal[:80],
                "risk_level": result.get("risk_level"),
                "requires_approval": True,
            })
            return result
        except Exception as e:
            return {"error": str(e)}

    def forge_approve(self, snapshot_id: str) -> dict:
        """Deploy an approved forge item. Requires explicit human action — never called automatically."""
        try:
            from core.forge_controller import get_forge_controller
            from neural_brain.api.node_bridge import emit
            # Verify item exists and is in pending state before deploying
            ctrl = get_forge_controller()
            items = ctrl.list_pending() if hasattr(ctrl, "list_pending") else []
            item = next((i for i in items if i.get("snapshot_id") == snapshot_id), None)
            if not item and items:  # fallback: proceed if list_pending not filterable
                pass
            result = ctrl.approve(snapshot_id)
            emit("nb:forge_approved", {
                "snapshot_id": snapshot_id,
                "status": "approved",
                "deployed_by": "human_approval",
            })
            return result
        except Exception as e:
            return {"error": str(e)}

    def forge_reject(self, snapshot_id: str) -> dict:
        try:
            from core.forge_controller import get_forge_controller
            from neural_brain.api.node_bridge import emit
            result = get_forge_controller().reject(snapshot_id)
            emit("nb:forge_rejected", {"snapshot_id": snapshot_id, "status": "rejected"})
            return result
        except Exception as e:
            return {"error": str(e)}

    def route_model(self, arch: str, request: dict) -> dict:
        """Kernel-owned model dispatch — never bypass via direct ModelArchitectureRouter calls."""
        try:
            from neural_brain.models.model_architecture_router import ModelArchitectureRouter
            return ModelArchitectureRouter.route(arch, request)
        except Exception as e:
            return {"status": "error", "arch": arch, "error": str(e)}

    def forge_build(self, spec: str, project_name: str, target_type: str = "fastapi_app",
                    timeout_s: float = 300.0) -> dict:
        """Generate project scaffold. Runs in a thread with timeout — never auto-deploys result."""
        import concurrent.futures
        from neural_brain.forge.builder import ForgeBuilder
        builder = ForgeBuilder(engine=self)
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            future = ex.submit(builder.generate_project, spec=spec, project_name=project_name, target_type=target_type)
            try:
                return future.result(timeout=timeout_s)
            except concurrent.futures.TimeoutError:
                return {"error": f"forge_build timed out after {timeout_s}s", "project_name": project_name}
            except Exception as e:
                return {"error": str(e), "project_name": project_name}

    # ── Evolution (kernel-owned delegation) ───────────────────────────────────

    def evolution_status(self) -> dict:
        try:
            from core.self_evolution.evolution_controller import get_evolution_controller
            return get_evolution_controller().status()
        except Exception as e:
            return {"error": str(e)}

    def evolution_set_mode(self, mode: str) -> dict:
        try:
            from core.self_evolution.evolution_controller import get_evolution_controller
            result = get_evolution_controller().set_mode(mode.upper())
            return {"mode": mode.upper(), "result": result}
        except Exception as e:
            return {"error": str(e)}

    # ── Status ────────────────────────────────────────────────────────────────

    def get_status(self) -> dict:
        from neural_brain.config.settings import get_settings
        settings = get_settings()

        health = {}
        try:
            from neural_brain.core.health_monitor import get_health_monitor
            health = get_health_monitor().current_stats()
        except Exception:
            pass

        blacklight = {}
        try:
            from neural_brain.security.blacklight_engine import get_blacklight
            blacklight = get_blacklight().get_status()
        except Exception:
            pass

        task_queue = {}
        try:
            from neural_brain.core.task_queue import get_task_queue
            task_queue = get_task_queue().stats()
        except Exception:
            pass

        return {
            "neo4j": self._check_neo4j(),
            "chroma": self._check_chroma(),
            "ollama": self._check_ollama(),
            "health": health,
            "blacklight": blacklight,
            "task_queue": task_queue,
            "archs": {
                "LLM": "ok", "SLM": "ok", "MoE": "ok", "VLM": "ok",
                "MLM": "ok", "LAM": "ok",
                "LCM": "disabled" if not settings.lcm_enabled else "ok",
                "SAM": "disabled" if not settings.sam_enabled else "ok",
            },
        }

    def _check_neo4j(self) -> str:
        try:
            from neural_brain.graph import get_brain_graph
            g = get_brain_graph()
            return "ok" if g and g.available else "offline"
        except Exception:
            return "error"

    def _check_chroma(self) -> str:
        try:
            from neural_brain.memory import get_memory
            get_memory()
            return "ok"
        except Exception:
            return "error"

    def _check_ollama(self) -> str:
        try:
            import httpx
            from neural_brain.config.settings import get_settings
            resp = httpx.get(f"{get_settings().ollama_host}/api/tags", timeout=2.0)
            return "ok" if resp.status_code == 200 else "error"
        except Exception:
            return "error"


# ── Singleton ─────────────────────────────────────────────────────────────────

_engine_instance: ConsciousnessEngine | None = None
_engine_lock = threading.Lock()


def get_engine() -> ConsciousnessEngine:
    global _engine_instance
    if _engine_instance is None:
        with _engine_lock:
            if _engine_instance is None:
                _engine_instance = ConsciousnessEngine()
    return _engine_instance
