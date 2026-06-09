"""Swarm Controller — parallel multi-agent execution for complex goals.

Decomposes a goal into subtasks via the existing Planner, then runs each
subtask as a ReActAgent instance concurrently using a ThreadPoolExecutor.
Results are merged with a final LLM synthesis call.
"""
from __future__ import annotations

import json
import logging
import queue
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger("core.swarm")

# Per-run step queues for SSE streaming
_run_queues: dict[str, queue.Queue] = {}
_run_queues_lock = threading.Lock()

_SENTINEL = object()


def _get_queue(run_id: str) -> queue.Queue:
    with _run_queues_lock:
        if run_id not in _run_queues:
            _run_queues[run_id] = queue.Queue()
        return _run_queues[run_id]


def _close_queue(run_id: str) -> None:
    q = _get_queue(run_id)
    q.put(_SENTINEL)


def get_run_step_queue(run_id: str) -> queue.Queue:
    """Return the step event queue for a running swarm. Used by SSE stream."""
    return _get_queue(run_id)


@dataclass
class SwarmResult:
    run_id: str
    goal: str
    status: str  # "done" | "partial" | "failed"
    output: str
    subtask_results: dict[str, Any] = field(default_factory=dict)
    tokens_used: int = 0
    duration_ms: float = 0.0


class SwarmController:
    """Coordinates multiple ReActAgent instances across decomposed subtasks."""

    def __init__(
        self,
        max_agents: int = 4,
        react_max_steps: int = 15,
        on_step: Callable[[str, dict], None] | None = None,
    ) -> None:
        self.max_agents = max_agents
        self.react_max_steps = react_max_steps
        self.on_step = on_step  # callback(run_id, step_event)

    def run_swarm(self, goal: str, max_agents: int | None = None, context: dict | None = None) -> SwarmResult:
        run_id = str(uuid.uuid4())
        t_start = time.time()
        n_agents = max_agents or self.max_agents

        logger.info("swarm run_id=%s goal=%s max_agents=%d", run_id, goal[:80], n_agents)
        self._emit(run_id, {"type": "swarm_started", "goal": goal, "run_id": run_id})

        try:
            subtasks = self._decompose(goal, run_id)
        except Exception as exc:
            logger.error("swarm decompose failed: %s", exc)
            _close_queue(run_id)
            return SwarmResult(run_id=run_id, goal=goal, status="failed",
                               output=f"Planning failed: {exc}",
                               duration_ms=(time.time() - t_start) * 1000)

        self._emit(run_id, {"type": "plan_ready", "subtasks": [s["task"] for s in subtasks]})

        subtask_results: dict[str, Any] = {}
        total_tokens = 0

        with ThreadPoolExecutor(max_workers=min(n_agents, len(subtasks) or 1)) as pool:
            future_to_subtask = {
                pool.submit(self._run_subtask, run_id, st, context or {}): st
                for st in subtasks
            }
            for future in as_completed(future_to_subtask):
                st = future_to_subtask[future]
                try:
                    result = future.result()
                    subtask_results[st["id"]] = result
                    total_tokens += result.get("tokens_used", 0)
                    self._emit(run_id, {
                        "type": "subtask_done",
                        "subtask_id": st["id"],
                        "agent": st.get("agent", "react_agent"),
                        "status": result.get("status", "done"),
                    })
                except Exception as exc:
                    logger.warning("subtask %s failed: %s", st["id"], exc)
                    subtask_results[st["id"]] = {"status": "failed", "error": str(exc)}

        # Synthesise all subtask outputs into a final answer
        try:
            final_output, synth_tokens = self._synthesise(goal, subtask_results)
            total_tokens += synth_tokens
            status = "done"
        except Exception as exc:
            logger.warning("swarm synthesis failed: %s", exc)
            final_output = json.dumps(subtask_results, indent=2)
            status = "partial"

        self._emit(run_id, {"type": "swarm_done", "status": status})
        _close_queue(run_id)

        return SwarmResult(
            run_id=run_id,
            goal=goal,
            status=status,
            output=final_output,
            subtask_results=subtask_results,
            tokens_used=total_tokens,
            duration_ms=(time.time() - t_start) * 1000,
        )

    def _decompose(self, goal: str, run_id: str) -> list[dict]:
        """Use the existing Planner to break the goal into TaskNode subtasks."""
        try:
            from core.planner import Planner
            from core.orchestrator import get_llm_client
            planner = Planner(llm_client=get_llm_client())
            graph = planner.plan(goal=goal, run_id=run_id)
            subtasks = []
            for node in graph.tasks:
                agent = self._select_agent(node.skill)
                subtasks.append({
                    "id": node.task_id,
                    "task": node.input.get("goal", goal),
                    "skill": node.skill,
                    "agent": agent,
                    "dependencies": node.dependencies,
                })
            return subtasks or [{"id": "main", "task": goal, "skill": "problem-solver", "agent": "react_coder", "dependencies": []}]
        except Exception as exc:
            logger.warning("Planner unavailable, single-task fallback: %s", exc)
            return [{"id": "main", "task": goal, "skill": "general", "agent": "react_coder", "dependencies": []}]

    def _select_agent(self, skill: str) -> str:
        """Map a skill name to the best ReAct agent."""
        research_skills = {"web_search", "research", "market_research", "content"}
        code_skills = {"code_generation", "script", "debug", "refactor", "implement"}
        if any(s in skill.lower() for s in research_skills):
            return "react_researcher"
        if any(s in skill.lower() for s in code_skills):
            return "react_coder"
        return "react_coder"

    def _try_delegate_to_worker(self, run_id: str, subtask: dict, context: dict, vram_needed_mb: int) -> dict | None:
        """Attempt to run subtask on a cluster worker with sufficient free VRAM.

        Returns result dict if successful, None if no suitable worker or delegation fails.
        """
        try:
            from engine.compute.cluster_node import get_cluster_node
            node = get_cluster_node()
            if not node._enabled:
                return None
            worker = node.best_worker(need_vram_mb=vram_needed_mb)
            if worker is None:
                return None
            logger.info("swarm: delegating subtask %s to worker %s (vram_free=%dMB)",
                        subtask["id"], worker.node_id, worker.vram_free_mb)
            result = node.remote_agent_run(
                goal=subtask["task"],
                context=context,
                prefer_node=worker,
                max_steps=self.react_max_steps,
            )
            if result and result.get("ok"):
                return {
                    "output": result.get("output", ""),
                    "status": result.get("status", "done"),
                    "steps": result.get("steps", 0),
                    "tokens_used": result.get("tokens_used", 0),
                    "worker_node": worker.node_id,
                }
        except Exception as exc:
            logger.debug("worker delegation skipped: %s", exc)
        return None

    def _run_subtask(self, run_id: str, subtask: dict, context: dict) -> dict:
        from engine.agent.agent_loop import ReActAgent
        from tools.registry import get_tool_registry
        from core.orchestrator import get_llm_client

        # Assess VRAM needs and try cluster worker first if local is tight
        vram_needed = 0
        try:
            from engine.compute.compute_planner import assess_compute_needs
            plan = assess_compute_needs(subtask["task"], context_len=len(subtask["task"]))
            vram_needed = plan.vram_needed_mb
        except Exception:
            pass

        if vram_needed > 3000:
            worker_result = self._try_delegate_to_worker(run_id, subtask, context, vram_needed)
            if worker_result:
                return worker_result

        def _on_step(step):
            self._emit(run_id, {
                "type": "step",
                "subtask_id": subtask["id"],
                "step_num": step.step_num,
                "action": step.action,
                "thought": step.thought,
                "observation_ok": step.observation.get("ok", True),
            })

        reg = get_tool_registry()
        react = ReActAgent(
            tools=reg,
            llm=get_llm_client(),
            max_steps=self.react_max_steps,
            max_risk=2,
            on_step=_on_step,
        )
        result = react.run(subtask["task"], context=context)
        return {
            "output": result.output,
            "status": result.status,
            "steps": len(result.steps),
            "tokens_used": result.tokens_used,
            "run_id": result.run_id,
        }

    def _synthesise(self, goal: str, results: dict) -> tuple[str, int]:
        from core.orchestrator import get_llm_client
        llm = get_llm_client()
        summaries = "\n\n".join(
            f"Subtask {k}:\n{v.get('output', v.get('error', ''))}"
            for k, v in results.items()
        )
        prompt = (
            f"Goal: {goal}\n\n"
            f"Subtask results:\n{summaries}\n\n"
            "Synthesise the above into a single coherent final answer. "
            "Be concise. Include all key findings, outputs, and next steps."
        )
        completion = llm.complete(prompt=prompt, system="You are a synthesis agent. Combine subtask outputs into a clear final answer.")
        return completion.get("output", summaries), int(completion.get("tokens_used", 0))

    def _emit(self, run_id: str, event: dict) -> None:
        q = _get_queue(run_id)
        q.put(event)
        if self.on_step:
            try:
                self.on_step(run_id, event)
            except Exception:
                pass


_controller_instance: SwarmController | None = None
_controller_lock = threading.Lock()


def get_swarm_controller() -> SwarmController:
    global _controller_instance
    with _controller_lock:
        if _controller_instance is None:
            _controller_instance = SwarmController()
    return _controller_instance
