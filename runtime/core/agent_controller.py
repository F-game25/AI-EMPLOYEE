"""Central orchestrator coordinating planner, executor, validator."""
from __future__ import annotations

import asyncio
import os
import time
import uuid
import threading
import logging
from typing import Any, Callable, Optional

from analytics.structured_logger import StructuredLogger, get_structured_logger
from core.brain_registry import brain
from core.contracts import TaskGraph, TaskNode
from core.context_evaluator import ContextSufficiencyEvaluator, get_context_evaluator
from core.auto_research_agent import AutoResearchAgent, get_auto_researcher
from core.knowledge_store import get_knowledge_store
from core.learning_engine import get_learning_engine
from core.memory_index import get_memory_index
from core.research_agent import ResearchAgent
from core.executor import Executor
from core.planner import Planner
from core.validator import Validator
from security.policy import SecurityPolicy, get_security_policy
from skills.catalog import SkillCatalog, get_skill_catalog


class AgentController:
    """Application-layer orchestrator with deterministic data flow."""

    def __init__(
        self,
        *,
        planner: Planner | None = None,
        executor: Executor | None = None,
        validator: Validator | None = None,
        logger: StructuredLogger | None = None,
        skills: SkillCatalog | None = None,
        policy: SecurityPolicy | None = None,
    ) -> None:
        self._logger = logger or get_structured_logger()
        self._planner = planner or Planner(logger=self._logger)
        catalog = skills or get_skill_catalog()
        guard = policy or get_security_policy()
        self._executor = executor or Executor(
            skills=catalog,
            policy=guard,
            logger=self._logger,
            action_emitter=self._emit_action,
        )
        self._validator = validator or Validator(logger=self._logger)
        self.brain = brain
        self._research = ResearchAgent()
        # Research loop wiring (lazy/safe — failures degrade gracefully)
        self._context_evaluator: Optional[ContextSufficiencyEvaluator] = None
        self._auto_researcher: Optional[AutoResearchAgent] = None
        self._broadcast_fn: Callable[[str, dict], None] = lambda _e, _p: None
        # Per-task context-check user response futures, keyed by task/run id
        self._context_responses: dict[str, dict] = {}
        self._context_lock = threading.Lock()

    @property
    def planner(self) -> Planner:
        return self._planner

    @property
    def executor(self) -> Executor:
        return self._executor

    @property
    def validator(self) -> Validator:
        return self._validator

    def build_task_graph(self, *, goal: str, run_id: str) -> TaskGraph:
        goal_type = self._planner.classify_goal(goal)
        brain_strategy = self.brain.get_strategy(goal=goal, goal_type=goal_type)
        best = self._best_strategies(goal)
        best = [brain_strategy, *best]
        self._logger.log_event(
            component="controller",
            action="brain_used",
            result="strategy_selected",
            latency_ms=0.0,
            meta={
                "run_id": run_id,
                "goal_type": goal_type,
                "skill": brain_strategy.get("agent", "problem-solver"),
                "bucket": brain_strategy.get("brain", {}).get("bucket", 7),
                "source": brain_strategy.get("brain", {}).get("source", "fallback"),
            },
        )
        return self._planner.plan(goal=goal, run_id=run_id, best_strategies=best)

    def run_goal(
        self,
        goal: str,
        *,
        persist_task: Callable[[str, TaskNode], None] | None = None,
    ) -> dict:
        run_id = str(uuid.uuid4())[:8]
        start = time.perf_counter()
        self._learn_from_conversation(goal)

        if self._research.is_learn_command(goal):
            return self._run_learn_topic_goal(goal=goal, run_id=run_id, start=start, persist_task=persist_task)

        # ── Context sufficiency + autonomous research loop ────────────────
        ctx_summary = self._run_context_research_loop(goal=goal, run_id=run_id)

        graph = self.build_task_graph(goal=goal, run_id=run_id)
        if ctx_summary and graph.tasks:
            # Tag first task with context score + findings for downstream skills
            graph.tasks[0].context_score = float(ctx_summary.get("final_score", 0.0))
            graph.tasks[0].research_findings = ctx_summary
        tasks = self._executor.execute_graph(graph)
        for task in tasks:
            verdict = self._validator.validate(task)
            task.passed = verdict.passed
            task.score = verdict.score
            if persist_task:
                persist_task(run_id, task)
            self._feedback_loop(goal=goal, task=task)
        summary = self._build_summary(run_id=run_id, goal=goal, graph=graph)
        self._logger.log_event(
            component="controller",
            action="run_goal",
            result="success",
            latency_ms=(time.perf_counter() - start) * 1000,
            meta={"run_id": run_id, "tasks": len(tasks)},
        )
        return summary

    def _run_learn_topic_goal(
        self,
        *,
        goal: str,
        run_id: str,
        start: float,
        persist_task: Callable[[str, TaskNode], None] | None,
    ) -> dict:
        result = self._research.learn_topic(goal)
        topic = result.get("topic", "general_research")
        task = TaskNode(
            task_id=f"{run_id}-t1",
            skill="problem-solver",
            input={"goal": goal, "intent": "task_learn_topic", "topic": topic},
            expected_output={"status": "success", "topic": topic},
            status="success",
            output=result,
            score=1.0,
            passed=True,
        )
        graph = TaskGraph(run_id=run_id, goal=goal, tasks=[task])
        if persist_task:
            persist_task(run_id, task)
        self._feedback_loop(goal=goal, task=task)
        self._logger.log_event(
            component="controller",
            action="run_goal",
            result="learn_topic",
            latency_ms=(time.perf_counter() - start) * 1000,
            meta={"run_id": run_id, "topic": topic},
        )
        return {
            "run_id": run_id,
            "goal": goal,
            "task_graph": graph.to_contract(),
            "tasks": [self._task_summary(task)],
            "performance_score": 1.0,
            "success_rate": 1.0,
            "learned_topic": result,
        }

    @staticmethod
    def _learn_from_conversation(text: str) -> None:
        try:
            get_knowledge_store().learn_from_conversation(text)
            get_learning_engine().add_conversation_message(role="user", message=text)
            get_memory_index().add_memory(text, importance=0.7)
        except Exception:
            logging.getLogger(__name__).debug("conversation learning failed", exc_info=True)
            return

    def _build_summary(self, *, run_id: str, goal: str, graph: TaskGraph) -> dict:
        rows = [self._task_summary(task) for task in graph.tasks]
        score = round(sum(task.score for task in graph.tasks) / max(len(graph.tasks), 1), 3)
        success = round(sum(1 for task in graph.tasks if task.status == "success") / max(len(graph.tasks), 1), 3)
        return {
            "run_id": run_id,
            "goal": goal,
            "task_graph": graph.to_contract(),
            "tasks": rows,
            "performance_score": score,
            "success_rate": success,
        }

    def _task_summary(self, task: TaskNode) -> dict:
        return {
            "task_id": task.task_id,
            "skill": task.skill,
            "status": task.status,
            "success": task.status == "success",
            "attempts": task.attempts,
            "score": round(task.score, 3),
            "error": task.error,
            "output": task.output,
        }

    def _best_strategies(self, goal: str) -> list[dict]:
        try:
            from memory.strategy_store import get_strategy_store

            goal_type = self._planner.classify_goal(goal)
            return get_strategy_store().get_best_strategy(goal_type)
        except Exception as exc:
            self._logger.log_event(
                component="controller",
                action="best_strategies",
                result="fallback",
                latency_ms=0.0,
                meta={"reason": str(exc)},
            )
            return []

    def _feedback_loop(self, *, goal: str, task: TaskNode) -> None:
        try:
            from memory.strategy_store import get_strategy_store

            goal_type = self._planner.classify_goal(goal)
            get_strategy_store().record(
                goal_type=goal_type,
                agent=task.skill,
                config=task.input,
                outcome_score=task.score,
                outcome_status="success" if task.status == "success" else "failed",
                context={
                    "task_id": task.task_id,
                    "attempts": task.attempts,
                    "started_at": task.started_at,
                    "finished_at": task.finished_at,
                },
                outcome={
                    "status": task.status,
                    "output": task.output,
                    "error": task.error,
                },
                notes=task.error or "ok",
            )
            learning = self.brain.learn_from_task(goal=goal, task=task)
            self._logger.log_event(
                component="controller",
                action="brain_used",
                result="feedback_recorded",
                latency_ms=0.0,
                meta={
                    "task_id": task.task_id,
                    "skill": task.skill,
                    "status": task.status,
                    "learned": learning.get("learned", False),
                    "reward": learning.get("reward", 0.0),
                },
            )
        except Exception as exc:
            self._logger.log_event(
                component="controller",
                action="feedback_loop",
                result="error",
                latency_ms=0.0,
                meta={"reason": str(exc)},
            )

    # ── Context sufficiency + research loop ───────────────────────────────
    def set_broadcast(self, fn: Callable[[str, dict], None]) -> None:
        """Allow the FastAPI server to inject its WS broadcaster."""
        self._broadcast_fn = fn or (lambda _e, _p: None)
        if self._auto_researcher is not None:
            self._auto_researcher._broadcast = self._broadcast_fn

    def respond_to_context_check(self, task_id: str, choice: str) -> bool:
        """Backend hook: user clicked YES/NO on the context-check modal."""
        with self._context_lock:
            slot = self._context_responses.get(task_id)
            if not slot:
                return False
            slot["choice"] = "research" if choice == "research" else "continue"
            evt = slot.get("event")
            if evt:
                evt.set()
            return True

    def _research_mode(self) -> str:
        mode = (os.getenv("AUTO_RESEARCH_MODE") or "ask").lower()
        return mode if mode in ("auto", "ask", "off") else "ask"

    def _ensure_research_components(self) -> None:
        if self._context_evaluator is None:
            try:
                self._context_evaluator = get_context_evaluator()
            except Exception as e:
                self._logger.log_event(
                    component="controller", action="research_setup", result="evaluator_unavailable",
                    latency_ms=0.0, meta={"reason": str(e)},
                )
        if self._auto_researcher is None:
            try:
                self._auto_researcher = get_auto_researcher(broadcaster=self._broadcast_fn)
            except Exception as e:
                self._logger.log_event(
                    component="controller", action="research_setup", result="researcher_unavailable",
                    latency_ms=0.0, meta={"reason": str(e)},
                )

    def _await_user_choice(self, task_id: str, timeout: float) -> str:
        evt = threading.Event()
        with self._context_lock:
            self._context_responses[task_id] = {"event": evt, "choice": "continue"}
        evt.wait(timeout=timeout)
        with self._context_lock:
            slot = self._context_responses.pop(task_id, {})
        return slot.get("choice") or "continue"

    def _run_context_research_loop(self, *, goal: str, run_id: str) -> dict:
        mode = self._research_mode()
        if mode == "off":
            return {}
        self._ensure_research_components()
        if not self._context_evaluator or not self._auto_researcher:
            return {}

        try:
            eval_result = self._context_evaluator.evaluate(goal)
        except Exception as e:
            logging.getLogger(__name__).debug("context evaluate failed: %s", e)
            return {}

        summary: dict[str, Any] = {
            "initial_score": eval_result.get("score", 0.0),
            "initial_gaps": eval_result.get("gaps", []),
            "hops": [],
            "final_score": eval_result.get("score", 0.0),
            "memory_hits": eval_result.get("memory_hits", 0),
            "graph_hits": eval_result.get("graph_hits", 0),
        }

        if eval_result.get("sufficient"):
            return summary

        # Decide: ask user or auto-research
        if mode == "ask":
            self._broadcast_fn("task:context_check", {
                "task_id": run_id, "goal": goal,
                "score": eval_result["score"], "gaps": eval_result["gaps"],
                "memory_hits": eval_result.get("memory_hits", 0),
                "graph_hits": eval_result.get("graph_hits", 0),
            })
            timeout_s = float(os.getenv("CONTEXT_CHECK_TIMEOUT_S", "60"))
            choice = self._await_user_choice(run_id, timeout=timeout_s)
            if choice != "research":
                summary["user_choice"] = "continue"
                return summary

        # Run up to 3 research hops, re-evaluating after each
        max_hops = int(os.getenv("RESEARCH_MAX_HOPS", "3"))
        for hop in range(max_hops):
            try:
                research_result = asyncio.run(self._auto_researcher.research(
                    gaps=eval_result["gaps"], goal=goal, hop=hop, task_id=run_id,
                ))
            except Exception as e:
                logging.getLogger(__name__).warning("research hop %d failed: %s", hop, e)
                research_result = {"hop": hop, "findings_count": 0, "sources": []}
            summary["hops"].append(research_result)
            if research_result.get("budget_exhausted") or not research_result.get("findings_count"):
                break
            try:
                eval_result = self._context_evaluator.evaluate(goal)
            except Exception:
                break
            summary["final_score"] = eval_result.get("score", summary["final_score"])
            if eval_result.get("sufficient"):
                break
        return summary

    def _emit_action(self, action: str, payload: dict) -> dict:
        from actions.action_bus import get_action_bus

        action_type = f"skill:{payload.get('skill', 'unknown')}"
        bus_payload = {"task_input": payload.get("input", {}), "action": action}
        return get_action_bus().emit(
            action_type=action_type,
            payload=bus_payload,
            actor="agent_controller",
            reason="executor dispatch",
        )


_instance: AgentController | None = None
_instance_lock = threading.Lock()


def get_agent_controller() -> AgentController:
    global _instance
    with _instance_lock:
        if _instance is None:
            _instance = AgentController()
    return _instance
