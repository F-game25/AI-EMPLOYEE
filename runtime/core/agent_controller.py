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
from skills.catalog import SkillCatalog, get_skill_catalog


def _load_security_policy():
    """Import the runtime security *package* policy, resilient to a flat
    ``security.py`` shadowing ``sys.modules['security']`` on the server path.

    `runtime/security/policy.py` is dependency-clean (stdlib only), so loading it
    directly by file path is safe when the normal import resolves to the wrong module.
    """
    try:
        from security.policy import SecurityPolicy, get_security_policy  # type: ignore
        return SecurityPolicy, get_security_policy
    except (ImportError, ModuleNotFoundError):
        import importlib.util
        from pathlib import Path
        policy_path = Path(__file__).resolve().parents[1] / "security" / "policy.py"
        spec = importlib.util.spec_from_file_location("_runtime_security_policy", policy_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        return mod.SecurityPolicy, mod.get_security_policy


SecurityPolicy, get_security_policy = _load_security_policy()


class AgentController:
    """Application-layer orchestrator with deterministic data flow."""

    _agent_caps_cache: dict | None = None
    _agent_caps_lock = __import__('threading').Lock()

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
        self._broadcast_enabled = False
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

    async def _qce_route_agent(self, goal: str, preferred_agent_id: str | None = None) -> str | None:
        try:
            from core.quantum.engine import get_qce
            qce = get_qce()
            timeout_ms = int(os.getenv("AGENT_CONTROLLER_QCE_TIMEOUT_MS", "300"))
            pack = await qce.process(
                goal=goal,
                task_type='execution',
                engine_filter=["agents", "tools", "tasks", "docs"],
                max_results_per_engine=10,
                timeout_ms=timeout_ms,
            )
            agents = qce._router.route_agents(pack, preferred_agent_id=preferred_agent_id)
            return agents[0] if agents else None
        except Exception:
            return None

    @staticmethod
    def _qce_routing_enabled() -> bool:
        return (os.getenv("AGENT_CONTROLLER_QCE_ROUTING") or "0").lower() in {"1", "true", "yes", "on"}

    def _keyword_route_agent(self, goal: str) -> str | None:
        import json, os
        with AgentController._agent_caps_lock:
            if AgentController._agent_caps_cache is None:
                caps_path = os.path.join(os.path.dirname(__file__), '..', 'config', 'agent_capabilities.json')
                try:
                    with open(os.path.normpath(caps_path)) as f:
                        data = json.load(f)
                    AgentController._agent_caps_cache = data.get('agents', data) if isinstance(data, dict) else {}
                except Exception:
                    AgentController._agent_caps_cache = {}
        caps = AgentController._agent_caps_cache
        if not caps:
            return None
        tokens = set(goal.lower().split())
        best_id, best_score = None, 0
        for agent_id, meta in caps.items():
            if not isinstance(meta, dict):
                continue
            corpus = ' '.join([
                meta.get('description', ''),
                meta.get('category', ''),
                ' '.join(meta.get('skills', [])),
                ' '.join(meta.get('commands', [])),
                ' '.join(meta.get('specialties', [])),
            ]).lower()
            score = sum(1 for t in tokens if t in corpus)
            if score > best_score:
                best_score, best_id = score, agent_id
        return best_id if best_score > 0 else None

    def run_goal(
        self,
        goal: str,
        *,
        persist_task: Callable[[str, TaskNode], None] | None = None,
        max_retry: int = 2,
        preferred_agent_id: str | None = None,
    ) -> dict:
        run_id = str(uuid.uuid4())[:8]
        start = time.perf_counter()
        self._learn_from_conversation(goal)

        # ── Compute plan — cheapest model that can handle this goal ──────────
        _compute_plan = None
        try:
            from engine.compute.compute_planner import assess_compute_needs
            _compute_plan = assess_compute_needs(goal, context_len=len(goal))
            self._broadcast_fn("task:compute_plan", {
                "strategy": _compute_plan.strategy,
                "model": _compute_plan.model,
                "estimated_cost_usd": _compute_plan.estimated_cost_usd,
                "vram_needed_mb": _compute_plan.vram_needed_mb,
                "rationale": _compute_plan.rationale,
                "needs_approval": _compute_plan.needs_approval,
            })
        except Exception as _cp_err:
            self._logger.log_event(component="controller", action="compute_plan_skipped",
                                   result="warn", latency_ms=0.0, meta={"err": str(_cp_err)})

        # QCE agent routing — attempt amplitude-based selection, fall back to keyword router
        _qce_agent: str | None = None
        _log = logging.getLogger(__name__)
        if self._qce_routing_enabled():
            try:
                _qce_agent = asyncio.run(self._qce_route_agent(goal, preferred_agent_id))
                if _qce_agent:
                    _log.debug("agent routing: QCE selected '%s'", _qce_agent)
                else:
                    raise ValueError("QCE returned None")
            except Exception:
                _qce_agent = None
        if not _qce_agent:
            _kw_agent = self._keyword_route_agent(goal)
            if _kw_agent:
                _log.debug("agent routing: keyword fallback selected '%s'", _kw_agent)
                _qce_agent = _kw_agent
            else:
                _qce_agent = preferred_agent_id
                _log.debug("agent routing: no match, using preferred_agent_id='%s'", preferred_agent_id)

        if self._research.is_learn_command(goal):
            return self._run_learn_topic_goal(goal=goal, run_id=run_id, start=start, persist_task=persist_task)

        # ── Context sufficiency + autonomous research loop ────────────────
        ctx_summary = self._run_context_research_loop(goal=goal, run_id=run_id)

        # ── Planning with retry on validation failure ──────────────────────
        graph = None
        last_failure: str = ""
        effective_goal = goal
        for attempt in range(max(1, max_retry)):
            try:
                graph = self.build_task_graph(goal=effective_goal, run_id=run_id)
                graph.validate_no_cycles()
                break
            except Exception as exc:
                last_failure = str(exc)
                self._logger.log_event(
                    component="controller",
                    action="plan_retry",
                    result="retrying",
                    latency_ms=0.0,
                    meta={"attempt": attempt + 1, "reason": last_failure},
                )
                # Inject failure context into the goal so the planner gets a richer signal
                effective_goal = f"{goal}\n[previous plan failed: {last_failure}]"
        if graph is None:
            raise RuntimeError(f"Planning failed after {max_retry} attempts: {last_failure}")

        # ── Plan quality scoring ───────────────────────────────────────────
        quality_score, estimated_cost_tokens = self._score_plan_quality(goal, graph)
        self._broadcast_fn("task:plan_quality", {
            "goal": goal,
            "task_count": len(graph.tasks),
            "quality_score": round(quality_score, 3),
            "estimated_cost_tokens": estimated_cost_tokens,
        })

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
        summary["plan_quality_score"] = round(quality_score, 3)
        summary["estimated_cost_tokens"] = estimated_cost_tokens
        self._logger.log_event(
            component="controller",
            action="run_goal",
            result="success",
            latency_ms=(time.perf_counter() - start) * 1000,
            meta={"run_id": run_id, "tasks": len(tasks), "quality_score": quality_score},
        )
        return summary

    @staticmethod
    def _score_plan_quality(goal: str, graph: TaskGraph) -> tuple[float, int]:
        """Return (quality_score 0–1, estimated_token_cost).

        Quality dimensions:
        - task_count_score: moderate task count (2-4) scores highest
        - dependency_completeness: fraction of tasks whose declared deps exist
        - goal_coverage: fraction of goal tokens appearing in task inputs
        """
        tasks = graph.tasks
        n = len(tasks)
        if n == 0:
            return 0.0, 0

        # 1. Task count score — penalise trivially short (0-1) or bloated (>8) plans
        if n == 1:
            task_count_score = 0.5
        elif 2 <= n <= 4:
            task_count_score = 1.0
        elif 5 <= n <= 8:
            task_count_score = 0.7
        else:
            task_count_score = 0.4

        # 2. Dependency completeness
        task_ids = {t.task_id for t in tasks}
        total_deps = sum(len(t.dependencies) for t in tasks)
        valid_deps = sum(1 for t in tasks for d in t.dependencies if d in task_ids)
        dep_score = (valid_deps / total_deps) if total_deps > 0 else 1.0

        # 3. Goal keyword coverage in task inputs
        from core.context_evaluator import _tokens
        goal_tokens = set(_tokens(goal))
        if goal_tokens:
            covered_tokens: set[str] = set()
            for t in tasks:
                inp_text = " ".join(str(v) for v in t.input.values())
                for tok in _tokens(inp_text):
                    if tok in goal_tokens:
                        covered_tokens.add(tok)
            coverage = len(covered_tokens) / len(goal_tokens)
        else:
            coverage = 1.0

        quality = 0.4 * task_count_score + 0.3 * dep_score + 0.3 * coverage

        # Estimated token cost: ~300 tokens per task (system prompt + input + output)
        estimated_cost_tokens = n * 300

        return min(1.0, quality), estimated_cost_tokens

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
        self._broadcast_enabled = bool(fn)
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
            if not self._broadcast_enabled:
                summary["user_choice"] = "continue"
                summary["headless"] = True
                return summary
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
        """Dispatch a skill via the ActionBus with a REAL LLM executor.

        Previously this emitted an unregistered ``skill:<name>`` action with no
        executor → the bus returned ``unknown_action`` but the skill still reported
        success (a fake-success no-op). We now supply an executor that runs the goal
        through the local LLM, so the action genuinely executes and honest status
        propagates (executor raising → bus returns error → task fails).
        """
        from actions.action_bus import get_action_bus

        skill = payload.get("skill", "unknown")
        action_type = f"skill:{skill}"
        task_input = payload.get("input", {}) or {}
        goal = str(task_input.get("goal") or task_input.get("task") or "").strip()
        context = task_input.get("context")

        if not self._llm_provider_available():
            def _unavailable_executor(_p: dict) -> dict:
                raise RuntimeError("llm_provider_unavailable")

            return get_action_bus().emit(
                action_type=action_type,
                payload={"task_input": task_input, "action": action},
                actor="agent_controller",
                reason="executor dispatch",
                executor=_unavailable_executor,
            )

        def _llm_executor(_p: dict) -> dict:
            from engine.api import generate
            role = skill.replace("-", " ").replace("_", " ")
            system = (
                f"You are the '{role}' capability inside an AI operations system. "
                "Complete the user's goal concretely and concisely. If the goal asks "
                "for code or a file, output the full content."
            )
            text = generate(prompt=goal or str(task_input), system=system,
                            context=context if isinstance(context, str) else None)
            text = (text or "").strip()
            if not text:
                raise RuntimeError(f"skill '{skill}' produced no output")
            return {"skill": skill, "goal": goal, "output": text}

        return get_action_bus().emit(
            action_type=action_type,
            payload={"task_input": task_input, "action": action},
            actor="agent_controller",
            reason="executor dispatch",
            executor=_llm_executor,
        )

    @staticmethod
    def _llm_provider_available() -> bool:
        api_keys = (
            "GOOGLE_API_KEY",
            "NVIDIA_API_KEY",
            "ANTHROPIC_API_KEY",
            "OPENAI_API_KEY",
        )
        if any(os.getenv(key) for key in api_keys):
            return True
        try:
            import urllib.request

            host = os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
            timeout = float(os.getenv("AGENT_CONTROLLER_PROVIDER_CHECK_TIMEOUT_S", "0.5"))
            req = urllib.request.Request(f"{host}/api/tags", headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout):
                return True
        except Exception:
            return False


_instance: AgentController | None = None
_instance_lock = threading.Lock()


def get_agent_controller() -> AgentController:
    global _instance
    with _instance_lock:
        if _instance is None:
            _instance = AgentController()
    return _instance
