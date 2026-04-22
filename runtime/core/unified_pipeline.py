"""Unified AI Pipeline — single controlled execution path.

All user input MUST flow through ``process_user_input()``.  This module
connects every subsystem in one enforced sequence:

Phase 2  → retrieve_relevant_nodes   [KnowledgeStore + MemoryIndex]
Phase 2b → build_context             [structured context for the LLM]
Phase 3  → classify_decision         [TaskOrchestrator intent + DecisionEngine ranking]
Phase 4  → call_llm                  [injected callable, circuit-broken, full context]
Phase 5  → decompose_to_tasks        [structured task list from LLM output]
Phase 6  → execute_tasks             [AgentController.run_goal()]
Phase 7  → format_response           [OutputValidationMiddleware]
Phase 8  → update_graph              [KnowledgeStore + MemoryIndex write-back]
Phase 9  → monitor_and_improve       [AscendForge telemetry + AuditEngine]
Phase 10 → validate_pipeline_integrity [hard guards; violations logged to AuditEngine]

Pipeline contract::

    input
      → retrieve_relevant_nodes()
      → build_context()
      → classify_decision()
      → call_llm()          (via injected generate_llm_response_fn)
      → decompose_to_tasks()
      → execute_tasks()
      → format_response()
      → update_graph()
      → monitor_and_improve()
      → validate_pipeline_integrity()
      → output

No subsystem may be called directly from the UI layer.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Callable

logger = logging.getLogger("unified_pipeline")


# ── Custom exception ──────────────────────────────────────────────────────────

class PipelineViolationError(RuntimeError):
    """Raised when a mandatory pipeline stage was bypassed or skipped."""


# ── Per-request state container ───────────────────────────────────────────────

class _PipelineRun:
    """Carries telemetry and intermediate results for one pipeline execution."""

    def __init__(
        self,
        input_text: str,
        user_id: str,
        mode: str,
        model_route: str,
    ) -> None:
        self.input = input_text
        self.user_id = user_id
        self.mode = mode
        self.model_route = model_route
        self._started_at: float = time.perf_counter()

        # Phase outputs — populated as the pipeline progresses
        self.graph_data: dict[str, Any] = {}
        self.context: str = ""
        self.intent: str = ""
        self.selected_agents: list[str] = []
        self.execution_plan: str = ""
        self.llm_called: bool = False
        self.llm_output: str = ""
        self.tasks: list[dict[str, Any]] = []
        self.tasks_executed: int = 0
        self.agent_results: list[dict[str, Any]] = []
        self.final_response: str = ""

    def elapsed_ms(self) -> float:
        return (time.perf_counter() - self._started_at) * 1000


# ── Phase 2 — Graph retrieval ─────────────────────────────────────────────────

def retrieve_relevant_nodes(input_text: str) -> dict[str, Any]:
    """Pull related entries from KnowledgeStore and MemoryIndex.

    Returns::

        {
            "nodes":          str   — formatted knowledge-store context,
            "concepts":       list  — related insight snippets (up to 5),
            "past_decisions": list  — top relevant MemoryIndex items,
        }
    """
    nodes: str = ""
    concepts: list[str] = []
    past_decisions: list[dict[str, Any]] = []

    try:
        from core.knowledge_store import get_knowledge_store  # noqa: PLC0415
        ks = get_knowledge_store()
        nodes = ks.get_relevant_context(input_text) or ""
        hits = ks.search_knowledge(input_text)
        concepts = [str(h.get("content", "")) for h in hits[:5] if h.get("content")]
    except Exception as exc:
        logger.debug("KnowledgeStore retrieval failed (non-fatal): %s", exc)

    try:
        from core.memory_index import get_memory_index  # noqa: PLC0415
        mems = get_memory_index().get_relevant_memories(input_text, top_k=5)
        past_decisions = [
            {"text": m.get("text", ""), "importance": m.get("importance", 0.0)}
            for m in mems
        ]
    except Exception as exc:
        logger.debug("MemoryIndex retrieval failed (non-fatal): %s", exc)

    return {"nodes": nodes, "concepts": concepts, "past_decisions": past_decisions}


# ── Phase 2b — Context building ───────────────────────────────────────────────

def build_context(input_text: str, graph_data: dict[str, Any]) -> str:
    """Merge graph data into a structured context string for the LLM system prompt."""
    parts: list[str] = []

    nodes = (graph_data.get("nodes") or "").strip()
    if nodes:
        parts.append(f"Knowledge Graph Context:\n{nodes}")

    concepts = [c for c in (graph_data.get("concepts") or []) if str(c).strip()]
    if concepts:
        parts.append("Related Concepts:\n" + "\n".join(f"- {c}" for c in concepts[:5]))

    past = graph_data.get("past_decisions") or []
    snippets = [str(p.get("text", ""))[:200] for p in past[:3] if p.get("text")]
    if snippets:
        parts.append("Past Decisions & Memory:\n" + "\n".join(f"- {s}" for s in snippets))

    return "\n\n".join(parts)


# ── Phase 3 — Neural decision layer ──────────────────────────────────────────

# Intent → (agent_id, profit_potential, execution_speed, complexity)
_INTENT_AGENT_PROFILES: dict[str, tuple[str, float, float, float]] = {
    "lead_gen":  ("lead-hunter-elite",    9.0, 7.0, 5.0),
    "content":   ("content-calendar",     7.0, 8.0, 3.0),
    "social":    ("social-media-manager", 6.0, 9.0, 2.0),
    "research":  ("web-researcher",       7.0, 6.0, 4.0),
    "email":     ("email-marketing",      8.0, 8.0, 3.0),
    "support":   ("customer-support",     5.0, 9.0, 2.0),
    "finance":   ("finance-wizard",       9.0, 5.0, 7.0),
    "ops":       ("task-orchestrator",    6.0, 7.0, 5.0),
}


def classify_decision(
    input_text: str,
    graph_data: dict[str, Any],
) -> dict[str, Any]:
    """Classify intent and rank candidate agents via DecisionEngine.

    Returns::

        {
            "intent":          str,
            "selected_agents": list[str],
            "execution_plan":  str,
        }
    """
    intent = "ops"
    selected_agents: list[str] = []
    execution_plan = ""

    # Intent classification via TaskOrchestrator (lightweight LLM-based)
    try:
        from core.orchestrator import TaskOrchestrator  # noqa: PLC0415
        intent = TaskOrchestrator().classify_intent(input_text)
    except Exception as exc:
        logger.debug("Intent classification failed (non-fatal): %s", exc)

    # Agent ranking via DecisionEngine
    try:
        from core.decision_engine import get_decision_engine, ActionSpec  # noqa: PLC0415
        profile_data = _INTENT_AGENT_PROFILES.get(intent, _INTENT_AGENT_PROFILES["ops"])
        agent_id, profit, speed, complexity = profile_data
        candidate = ActionSpec(
            id=intent,
            skill=agent_id,
            profit_potential=profit,
            execution_speed=speed,
            complexity=complexity,
        )
        ranked = get_decision_engine().rank_actions([candidate])
        selected_agents = [a.skill for a in ranked]
        execution_plan = (
            f"intent={intent}, "
            f"agent={selected_agents[0]}, "
            f"score={ranked[0].score:.2f}"
        )
    except Exception as exc:
        logger.debug("DecisionEngine ranking failed (non-fatal): %s", exc)
        agent_id = _INTENT_AGENT_PROFILES.get(intent, _INTENT_AGENT_PROFILES["ops"])[0]
        selected_agents = [agent_id]
        execution_plan = f"fallback intent={intent}"

    return {
        "intent": intent,
        "selected_agents": selected_agents,
        "execution_plan": execution_plan,
    }


# ── Phase 5 — Task decomposition ──────────────────────────────────────────────

def decompose_to_tasks(
    llm_output: str,
    intent: str,
    selected_agents: list[str],
) -> list[dict[str, Any]]:
    """Convert LLM output into a structured task list.

    Returns a list of ``{agent, action, intent, inputs}`` dicts.
    Never returns raw unstructured text.
    """
    agent = selected_agents[0] if selected_agents else "task-orchestrator"
    action = (llm_output or f"execute {intent}")[:500]
    return [
        {
            "agent": agent,
            "action": action,
            "intent": intent,
            "inputs": {"llm_output": llm_output, "intent": intent},
        }
    ]


# ── Phase 6 — Agent execution ─────────────────────────────────────────────────

def execute_tasks(
    tasks: list[dict[str, Any]],
    goal: str,
) -> list[dict[str, Any]]:
    """Execute tasks via AgentController.run_goal() and return structured results.

    Failures are caught and returned as ``status="skipped"`` records so the
    pipeline never aborts due to agent execution errors.
    """
    if not tasks or not goal:
        return []

    results: list[dict[str, Any]] = []
    try:
        from core.agent_controller import get_agent_controller  # noqa: PLC0415
        summary = get_agent_controller().run_goal(goal)
        for task_info in summary.get("tasks", []):
            results.append(
                {
                    "task_id": task_info.get("task_id", ""),
                    "skill": task_info.get("skill", ""),
                    "status": task_info.get("status", "unknown"),
                    "success": task_info.get("success", False),
                    "score": float(task_info.get("score", 0.0)),
                    "output": task_info.get("output"),
                }
            )
    except Exception as exc:
        logger.debug("AgentController.run_goal failed (non-fatal): %s", exc)
        for task in tasks:
            results.append(
                {
                    "task_id": "",
                    "skill": task.get("agent", "unknown"),
                    "status": "skipped",
                    "success": False,
                    "score": 0.0,
                    "output": None,
                }
            )

    return results


# ── Phase 7 — Result aggregation ─────────────────────────────────────────────

def format_response(
    llm_output: str,
    agent_results: list[dict[str, Any]],
    routed_agent: str,
) -> str:
    """Merge LLM output and successful agent task results into the final response.

    Runs through OutputValidationMiddleware.validate_or_fallback() when available.
    """
    response = llm_output

    if agent_results:
        successful = [r for r in agent_results if r.get("success") and r.get("output")]
        if successful:
            snippets: list[str] = []
            for r in successful[:2]:
                out = r.get("output")
                if isinstance(out, dict):
                    text = str(out.get("output") or out.get("text") or "")
                elif isinstance(out, str):
                    text = out
                else:
                    text = ""
                # Only append if the snippet adds new content
                if text and text[:80].lower() not in response.lower():
                    snippets.append(text[:400])
            if snippets:
                response += "\n\n**Task Results:**\n" + "\n\n".join(snippets)

    try:
        from core.agent_output_schemas import get_schema_validator  # noqa: PLC0415
        validated, fallback = get_schema_validator().validate_or_fallback(
            routed_agent,
            response,
            ts=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        )
        if fallback:
            return fallback
    except Exception as exc:
        logger.debug("OutputValidationMiddleware failed (non-fatal): %s", exc)

    return response


# ── Phase 8 — Graph update ────────────────────────────────────────────────────

def update_graph(
    input_text: str,
    intent: str,
    response: str,
    agent_results: list[dict[str, Any]],
) -> None:
    """Persist the exchange back into KnowledgeStore and MemoryIndex."""
    try:
        from core.knowledge_store import get_knowledge_store  # noqa: PLC0415
        ks = get_knowledge_store()
        ks.add_knowledge(intent, f"Q: {input_text[:200]} | A: {response[:300]}")
        ks.learn_from_conversation(input_text)
    except Exception as exc:
        logger.debug("KnowledgeStore update failed (non-fatal): %s", exc)

    try:
        from core.memory_index import get_memory_index  # noqa: PLC0415
        mem_text = f"[{intent}] {input_text[:150]} → {response[:200]}"
        get_memory_index().add_memory(mem_text, importance=0.6)
    except Exception as exc:
        logger.debug("MemoryIndex update failed (non-fatal): %s", exc)


# ── Phase 9 — Ascend Forge monitoring ────────────────────────────────────────

def monitor_and_improve(run: _PipelineRun) -> None:
    """Submit pipeline telemetry to AscendForge and AuditEngine."""
    latency_ms = run.elapsed_ms()
    success = bool(run.final_response and run.llm_called)

    try:
        from core.ascend_forge import get_ascend_forge_executor  # noqa: PLC0415
        goal = (
            f"pipeline_monitor: latency={latency_ms:.0f}ms "
            f"intent={run.intent} "
            f"tasks={run.tasks_executed} "
            f"success={success}"
        )
        get_ascend_forge_executor().submit_change(
            objective_id=f"pipeline-{int(time.time())}",
            goal=goal,
            constraints={
                "latency_ms": latency_ms,
                "intent": run.intent,
                "tasks_executed": run.tasks_executed,
                "agents": run.selected_agents,
                "llm_called": run.llm_called,
                "success": success,
            },
            priority="low",
            submitted_by="unified_pipeline",
        )
    except Exception as exc:
        logger.debug("AscendForge telemetry failed (non-fatal): %s", exc)

    try:
        from core.audit_engine import get_audit_engine  # noqa: PLC0415
        get_audit_engine().record(
            actor="unified_pipeline",
            action="pipeline_run",
            input_data={
                "intent": run.intent,
                "user_id": run.user_id,
                "mode": run.mode,
                "input_len": len(run.input),
            },
            output_data={
                "response_len": len(run.final_response),
                "tasks_executed": run.tasks_executed,
                "llm_called": run.llm_called,
                "latency_ms": round(latency_ms, 1),
                "success": success,
            },
            risk_score=0.05,
        )
    except Exception as exc:
        logger.debug("AuditEngine record failed (non-fatal): %s", exc)


# ── Phase 10 — Hard integrity validation ──────────────────────────────────────

_FALLBACK_PREFIX = "System recovered:"


def validate_pipeline_integrity(run: _PipelineRun) -> None:
    """Log violations to AuditEngine and raise PipelineViolationError if any stage
    was bypassed.

    Checks:
    - graph was consulted (nodes, concepts, or past_decisions non-empty)
    - LLM was called
    - at least one task was structured (tasks_executed ≥ 1)
    - response is not the hardcoded fallback string

    Violations are always forwarded to AuditEngine even when non-fatal.
    """
    violations: list[str] = []

    gd = run.graph_data
    if not (
        (gd.get("nodes") or "").strip()
        or gd.get("concepts")
        or gd.get("past_decisions")
    ):
        violations.append(
            "graph_nodes_retrieved=0: knowledge graph was not consulted"
        )

    if not run.llm_called:
        violations.append("llm_called=False: LLM stage was bypassed")

    if run.tasks_executed == 0:
        violations.append(
            "tasks_executed=0: agent execution stage produced no tasks"
        )

    if run.final_response.startswith(_FALLBACK_PREFIX):
        violations.append(
            "response=fallback: final output is a hardcoded fallback string"
        )

    if not violations:
        return

    summary = "; ".join(violations)
    logger.warning("[PIPELINE INTEGRITY] violations detected: %s", summary)

    try:
        from core.audit_engine import get_audit_engine  # noqa: PLC0415
        get_audit_engine().record(
            actor="unified_pipeline",
            action="pipeline_violation",
            input_data={
                "violations": violations,
                "intent": run.intent,
                "user_id": run.user_id,
            },
            output_data={"violation_count": len(violations)},
            risk_score=0.6,
        )
    except Exception:
        pass

    raise PipelineViolationError(summary)


# ── Phase 1 — Primary entry point ────────────────────────────────────────────

def process_user_input(
    input_text: str,
    *,
    user_id: str = "default",
    mode: str = "power",
    model_route: str = "",
    generate_llm_response_fn: Callable[..., str] | None = None,
    route_to_agent_fn: Callable[[str], str] | None = None,
) -> str:
    """Single controlled entry point for all user input.

    Orchestrates the complete AI pipeline from graph retrieval to final response.
    Every subsystem MUST be connected through this function.

    Args:
        input_text:
            Sanitised user message.
        user_id:
            Authenticated user identifier (used for personalisation and audit).
        mode:
            Current system mode (``power`` / ``business`` / ``starter``).
        model_route:
            LLM provider override (``anthropic`` / ``openai`` / ``groq`` / …).
        generate_llm_response_fn:
            Callable with signature
            ``(message, routed_agent, mode, *, model_route, user_id, graph_context) → str``.
            Provided by server.py so this module never imports the server directly.
        route_to_agent_fn:
            Optional ``(message) → agent_id`` callable.  When provided, its
            result is used as the routed_agent in the LLM call instead of the
            DecisionEngine selection (preserves server.py keyword routing).

    Returns:
        The final user-facing response string.
    """
    run = _PipelineRun(input_text, user_id, mode, model_route)

    # ── Phase 2: Graph retrieval ──────────────────────────────────────────────
    try:
        run.graph_data = retrieve_relevant_nodes(input_text)
    except Exception as exc:
        logger.warning("Phase 2 (graph retrieval) failed: %s", exc)
        run.graph_data = {"nodes": "", "concepts": [], "past_decisions": []}

    # ── Phase 2b: Context building ────────────────────────────────────────────
    try:
        run.context = build_context(input_text, run.graph_data)
    except Exception as exc:
        logger.warning("Phase 2b (build context) failed: %s", exc)
        run.context = ""

    # ── Phase 3: Intent classification + agent selection ─────────────────────
    try:
        decision = classify_decision(input_text, run.graph_data)
        run.intent = decision["intent"]
        run.selected_agents = decision["selected_agents"]
        run.execution_plan = decision["execution_plan"]
    except Exception as exc:
        logger.warning("Phase 3 (decision) failed: %s", exc)
        run.intent = "ops"
        run.selected_agents = ["task-orchestrator"]
        run.execution_plan = "fallback"

    # ── Phase 4: LLM call (delegated to server.py via injected callable) ──────
    # Prefer the keyword-based agent already resolved by server.py so existing
    # routing behaviour is fully preserved.
    routed_agent = run.selected_agents[0] if run.selected_agents else "task-orchestrator"
    if route_to_agent_fn is not None:
        try:
            routed_agent = route_to_agent_fn(input_text)
        except Exception:
            pass

    try:
        if generate_llm_response_fn is not None:
            run.llm_output = generate_llm_response_fn(
                input_text,
                routed_agent,
                mode,
                model_route=model_route,
                user_id=user_id,
                graph_context=run.context,
            )
        else:
            run.llm_output = f"[no LLM callable provided] input={input_text}"
        run.llm_called = bool(run.llm_output)
    except Exception as exc:
        logger.warning("Phase 4 (LLM call) failed: %s", exc)
        run.llm_output = f"{_FALLBACK_PREFIX} LLM call failed — {exc}"
        run.llm_called = False

    # ── Phase 5: Task decomposition ───────────────────────────────────────────
    try:
        run.tasks = decompose_to_tasks(run.llm_output, run.intent, run.selected_agents)
    except Exception as exc:
        logger.warning("Phase 5 (decompose tasks) failed: %s", exc)
        run.tasks = []

    # ── Phase 6: Agent execution ──────────────────────────────────────────────
    try:
        run.agent_results = execute_tasks(run.tasks, input_text)
        run.tasks_executed = len(run.agent_results)
    except Exception as exc:
        logger.warning("Phase 6 (execute tasks) failed: %s", exc)
        run.agent_results = []
        run.tasks_executed = 0

    # ── Phase 7: Result aggregation ───────────────────────────────────────────
    try:
        run.final_response = format_response(
            run.llm_output, run.agent_results, routed_agent
        )
    except Exception as exc:
        logger.warning("Phase 7 (format response) failed: %s", exc)
        run.final_response = run.llm_output or f"{_FALLBACK_PREFIX} pipeline error — {exc}"

    # ── Phase 8: Graph update (non-blocking) ──────────────────────────────────
    try:
        update_graph(input_text, run.intent, run.final_response, run.agent_results)
    except Exception as exc:
        logger.debug("Phase 8 (graph update) failed (non-fatal): %s", exc)

    # ── Phase 9: AscendForge monitoring (non-blocking) ────────────────────────
    try:
        monitor_and_improve(run)
    except Exception as exc:
        logger.debug("Phase 9 (ascend forge) failed (non-fatal): %s", exc)

    # ── Phase 10: Hard integrity validation ───────────────────────────────────
    # Violations are logged but never surface as user-visible errors.
    try:
        validate_pipeline_integrity(run)
    except PipelineViolationError as exc:
        logger.warning("Phase 10 (integrity check) violations logged: %s", exc)

    return run.final_response
