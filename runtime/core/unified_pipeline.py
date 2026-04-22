"""Unified AI Pipeline — single controlled execution path.

All user input MUST flow through ``process_user_input()``.  This module
connects every subsystem in one enforced sequence:

Phase 2  → retrieve_relevant_nodes   [KnowledgeStore + MemoryIndex + neighbor expansion]
Phase 2b → build_context             [structured context for the LLM]
Phase 3  → classify_decision         [TaskOrchestrator intent + DecisionEngine ranking]
Phase 4  → call_llm                  [injected callable, circuit-broken, full context]
Phase 5  → decompose_to_tasks        [structured task list + schema validation]
Phase 6  → execute_tasks             [AgentController.run_goal() + real-execution check]
Phase 7  → format_response           [OutputValidationMiddleware + trace annotation]
Phase 8  → update_graph              [KnowledgeStore + MemoryIndex + edge creation]
Phase 9  → monitor_and_improve       [AscendForge telemetry + AuditEngine]
Phase 10 → validate_pipeline_integrity [hard guards; degraded flag; AuditEngine]

Pipeline contract::

    input
      → retrieve_relevant_nodes()  [+ neighbor expansion + ranking]
      → build_context()
      → classify_decision()
      → call_llm()                 (via injected generate_llm_response_fn)
      → validate_tasks()           [schema enforcement before execution]
      → execute_tasks()            [+ real-execution verification]
      → format_response()          [+ trace annotation]
      → connect_nodes()            [graph edge builder]
      → update_graph()
      → monitor_and_improve()
      → validate_pipeline_integrity()  [degraded flag + DEGRADED marker]
      → output

No subsystem may be called directly from the UI layer.

Environment variables
---------------------
STRICT_PIPELINE=1   — Disable all fallbacks; raise loudly on any phase failure.
                      Use in staging/testing to surface real issues.
                      Default: 0 (graceful degradation in production).
"""
from __future__ import annotations

import collections
import logging
import os
import time
from typing import Any, Callable

logger = logging.getLogger("unified_pipeline")

# ── Runtime mode ──────────────────────────────────────────────────────────────

# When True: no fallback, no silent swallowing — phases raise on failure.
# Set STRICT_PIPELINE=1 to enable in staging/CI.
STRICT_PIPELINE: bool = os.environ.get("STRICT_PIPELINE", "0") == "1"

# ── Pipeline trace store (capped ring buffer) ─────────────────────────────────

_TRACE_STORE: collections.deque[dict[str, Any]] = collections.deque(maxlen=100)


def get_pipeline_traces(*, limit: int = 20) -> list[dict[str, Any]]:
    """Return the most recent pipeline execution traces (newest first)."""
    items = list(_TRACE_STORE)
    items.reverse()
    return items[:max(1, limit)]


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

        # Fix 6 — pipeline trace
        self.trace: dict[str, Any] = {
            "input": input_text,
            "user_id": user_id,
            "mode": mode,
            "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "retrieved_nodes": {},
            "decision": {},
            "validated_tasks": [],
            "agent_results": [],
            "final_output": "",
            "degraded": False,
            "violations": [],
        }

        # Fix 7 — degraded flag
        self.degraded: bool = False

    def elapsed_ms(self) -> float:
        return (time.perf_counter() - self._started_at) * 1000


# ── Fix 2 — Graph neighbor expansion helper ──────────────────────────────────

def _expand_graph_neighbors(
    seed_concepts: list[str],
    input_text: str,
) -> list[str]:
    """Perform 1-hop neighbor expansion from seed concepts.

    Queries KnowledgeStore for topics related to each seed concept and
    returns a de-duplicated, relevance-ranked list of expanded concept texts.
    """
    if not seed_concepts:
        return []

    expanded: list[tuple[float, str]] = []  # (score, text)
    seen: set[str] = set(seed_concepts)

    try:
        from core.knowledge_store import get_knowledge_store  # noqa: PLC0415
        from core.memory_index import embed_text, cosine_similarity  # noqa: PLC0415

        ks = get_knowledge_store()
        query_vec = embed_text(input_text)

        for concept in seed_concepts[:5]:  # limit seeds to avoid explosion
            # find other entries that share a common topic token with this concept
            for token in (concept or "").lower().split()[:4]:
                if not token or len(token) < 3:
                    continue
                neighbors = ks.search_knowledge(token)
                for n in neighbors[:3]:
                    text = str(n.get("content", "")).strip()
                    if not text or text in seen:
                        continue
                    seen.add(text)
                    # score by vector similarity to original query
                    neighbor_vec = embed_text(text)
                    sim = cosine_similarity(query_vec, neighbor_vec)
                    expanded.append((sim, text))
    except Exception as exc:
        logger.debug("Graph neighbor expansion failed (non-fatal): %s", exc)

    # Sort by relevance descending, return top-8 texts
    expanded.sort(key=lambda x: x[0], reverse=True)
    return [text for _, text in expanded[:8]]


# ── Phase 2 — Graph retrieval ─────────────────────────────────────────────────

def retrieve_relevant_nodes(input_text: str) -> dict[str, Any]:
    """Pull related entries from KnowledgeStore and MemoryIndex.

    Performs 1-hop neighbor expansion and ranks results by relevance +
    connection strength before returning.

    Returns::

        {
            "nodes":          str   — formatted knowledge-store context,
            "concepts":       list  — related insight snippets (up to 8, ranked),
            "past_decisions": list  — top relevant MemoryIndex items,
            "expanded":       list  — 1-hop neighbor concept texts,
        }
    """
    nodes: str = ""
    concepts: list[str] = []
    past_decisions: list[dict[str, Any]] = []
    expanded: list[str] = []

    try:
        from core.knowledge_store import get_knowledge_store  # noqa: PLC0415
        from core.memory_index import embed_text, cosine_similarity  # noqa: PLC0415

        ks = get_knowledge_store()
        nodes = ks.get_relevant_context(input_text) or ""
        hits = ks.search_knowledge(input_text)

        # Rank raw hits by cosine similarity to input query
        query_vec = embed_text(input_text)
        scored_hits: list[tuple[float, str]] = []
        for h in hits:
            text = str(h.get("content", ""))
            if not text:
                continue
            sim = cosine_similarity(query_vec, embed_text(text))
            # Boost by connection count (number of tokens matched in blob)
            connection_bonus = min(0.1, len(text.split()) * 0.002)
            scored_hits.append((sim + connection_bonus, text))
        scored_hits.sort(key=lambda x: x[0], reverse=True)
        concepts = [text for _, text in scored_hits[:8]]

        # 1-hop neighbor expansion
        expanded = _expand_graph_neighbors(concepts[:5], input_text)
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

    return {
        "nodes": nodes,
        "concepts": concepts,
        "past_decisions": past_decisions,
        "expanded": expanded,
    }


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

    expanded = [c for c in (graph_data.get("expanded") or []) if str(c).strip()]
    if expanded:
        parts.append("Neighbor Concepts (1-hop):\n" + "\n".join(f"- {c}" for c in expanded[:5]))

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

    Separates intent classification (what the user wants) from execution
    planning (which agent/action best achieves it), preventing the LLM
    from conflating the two.

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

    # Step A — Intent classification via TaskOrchestrator (lightweight LLM-based)
    try:
        from core.orchestrator import TaskOrchestrator  # noqa: PLC0415
        intent = TaskOrchestrator().classify_intent(input_text)
    except Exception as exc:
        logger.debug("Intent classification failed (non-fatal): %s", exc)

    # Step B — Execution plan: rank candidate agents via DecisionEngine
    # Intent and context-derived scores are kept separate from LLM reasoning.
    try:
        from core.decision_engine import get_decision_engine, ActionSpec  # noqa: PLC0415
        profile_data = _INTENT_AGENT_PROFILES.get(intent, _INTENT_AGENT_PROFILES["ops"])
        agent_id, profit, speed, complexity = profile_data

        # Boost profit_potential if graph data shows relevant past decisions
        past_len = len(graph_data.get("past_decisions") or [])
        adjusted_profit = min(10.0, profit + past_len * 0.2)

        candidate = ActionSpec(
            id=intent,
            skill=agent_id,
            profit_potential=adjusted_profit,
            execution_speed=speed,
            complexity=complexity,
        )
        ranked = get_decision_engine().rank_actions([candidate])
        selected_agents = [a.skill for a in ranked]
        execution_plan = (
            f"intent={intent}, "
            f"agent={selected_agents[0]}, "
            f"score={ranked[0].score:.2f}, "
            f"context_boost={past_len}"
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


# ── Fix 3 — Task schema validation ───────────────────────────────────────────

_REQUIRED_TASK_FIELDS = ("agent", "action", "inputs")

_DEGRADED_MARKER = "\n\n---\n⚠ **[DEGRADED PIPELINE]** One or more pipeline stages failed or were bypassed. This response may be incomplete. Check `/api/pipeline-trace` for details."


def validate_tasks(tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Validate that every task has the required fields.

    Tasks missing ``agent``, ``action``, or ``inputs`` are dropped.
    Returns the filtered list of valid tasks.

    Raises ``PipelineViolationError`` when ``STRICT_PIPELINE=1`` and any task
    is invalid.
    """
    valid: list[dict[str, Any]] = []
    for i, task in enumerate(tasks):
        missing = [f for f in _REQUIRED_TASK_FIELDS if f not in task or task[f] is None]
        if missing:
            msg = f"Task[{i}] missing required fields: {missing} — task dropped"
            logger.warning("[TASK VALIDATION] %s", msg)
            if STRICT_PIPELINE:
                raise PipelineViolationError(msg)
        else:
            valid.append(task)
    return valid


# ── Phase 5 — Task decomposition ──────────────────────────────────────────────

def decompose_to_tasks(
    llm_output: str,
    intent: str,
    selected_agents: list[str],
) -> list[dict[str, Any]]:
    """Convert LLM output into a validated structured task list.

    Returns a list of ``{agent, action, intent, inputs}`` dicts.
    Never returns raw unstructured text.  All tasks pass schema validation
    before being returned.
    """
    agent = selected_agents[0] if selected_agents else "task-orchestrator"
    action = (llm_output or f"execute {intent}")[:500]
    raw_tasks = [
        {
            "agent": agent,
            "action": action,
            "intent": intent,
            "inputs": {"llm_output": llm_output, "intent": intent},
        }
    ]
    return validate_tasks(raw_tasks)


# ── Fix 4 — Real execution verification ──────────────────────────────────────

# Patterns that indicate a placeholder/simulated result rather than real execution
_SIMULATED_OUTPUT_PATTERNS = frozenset({
    "task completed",
    "successfully completed",
    "done",
    "ok",
    "success",
    "",
})


def _is_real_execution(result: dict[str, Any]) -> bool:
    """Return True when a task result appears to be a genuine execution.

    Checks:
    - task_id is non-empty
    - status is "success"
    - output is non-None and non-trivial (not a known placeholder string)
    """
    if not result.get("task_id"):
        return False
    if result.get("status") != "success":
        return False
    out = result.get("output")
    if out is None:
        return False
    # Normalise output to a short string for pattern matching
    if isinstance(out, dict):
        out_text = str(out.get("output") or out.get("text") or "").strip().lower()
    else:
        out_text = str(out).strip().lower()
    return out_text not in _SIMULATED_OUTPUT_PATTERNS and len(out_text) > 10


# ── Phase 6 — Agent execution ─────────────────────────────────────────────────

def execute_tasks(
    tasks: list[dict[str, Any]],
    goal: str,
) -> list[dict[str, Any]]:
    """Execute tasks via AgentController.run_goal() and return structured results.

    Each result is verified to be a real execution (not a placeholder) and
    annotated with a ``real_execution`` boolean flag.

    Failures are caught and returned as ``status="skipped"`` records so the
    pipeline never aborts due to agent execution errors (unless STRICT_PIPELINE).
    """
    if not tasks or not goal:
        return []

    results: list[dict[str, Any]] = []
    try:
        from core.agent_controller import get_agent_controller  # noqa: PLC0415
        summary = get_agent_controller().run_goal(goal)
        for task_info in summary.get("tasks", []):
            result = {
                "task_id": task_info.get("task_id", ""),
                "skill": task_info.get("skill", ""),
                "status": task_info.get("status", "unknown"),
                "success": task_info.get("success", False),
                "score": float(task_info.get("score", 0.0)),
                "output": task_info.get("output"),
            }
            result["real_execution"] = _is_real_execution(result)
            if not result["real_execution"]:
                logger.debug(
                    "[EXECUTION CHECK] task_id=%s skill=%s appears simulated",
                    result["task_id"],
                    result["skill"],
                )
            results.append(result)
    except Exception as exc:
        if STRICT_PIPELINE:
            raise
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
                    "real_execution": False,
                }
            )

    return results


# ── Phase 7 — Result aggregation ─────────────────────────────────────────────

def format_response(
    llm_output: str,
    agent_results: list[dict[str, Any]],
    routed_agent: str,
    *,
    degraded: bool = False,
) -> str:
    """Merge LLM output and successful agent task results into the final response.

    Runs through OutputValidationMiddleware.validate_or_fallback() when available.
    Appends traceability block showing what actually executed.
    When ``degraded=True`` appends the DEGRADED marker for internal debug visibility.
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

        # Traceability block — show what actually ran
        trace_lines = [
            f"- {r.get('skill','?')} [{r.get('status','?')}]"
            + (" ✓ real" if r.get("real_execution") else " ⚠ simulated")
            for r in agent_results[:5]
        ]
        if trace_lines:
            response += "\n\n**Execution Trace:**\n" + "\n".join(trace_lines)

    try:
        from core.agent_output_schemas import get_schema_validator  # noqa: PLC0415
        validated, fallback = get_schema_validator().validate_or_fallback(
            routed_agent,
            response,
            ts=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        )
        if fallback:
            response = fallback
    except Exception as exc:
        logger.debug("OutputValidationMiddleware failed (non-fatal): %s", exc)

    # Fix 7 — surface degraded status in response for internal debug panel
    if degraded:
        response += _DEGRADED_MARKER

    return response


# ── Fix 5 — Graph edge builder ────────────────────────────────────────────────

def connect_nodes(
    source_topic: str,
    target_topic: str,
    relationship_type: str,
) -> bool:
    """Create a directed edge between two knowledge graph nodes.

    Edges are stored as ``_edges`` entries in KnowledgeStore so they are
    persistent and queryable.  Returns True on success.

    Args:
        source_topic:    Source node / topic label.
        target_topic:    Target node / topic label.
        relationship_type: Semantic label for the edge (e.g. "informs",
                          "follows_from", "contradicts").
    """
    if not source_topic or not target_topic or source_topic == target_topic:
        return False
    try:
        from core.knowledge_store import get_knowledge_store  # noqa: PLC0415
        ks = get_knowledge_store()
        edge_record = {
            "source": source_topic,
            "target": target_topic,
            "relationship": relationship_type,
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        ks.add_knowledge("_edges", edge_record)
        return True
    except Exception as exc:
        logger.debug("connect_nodes failed (non-fatal): %s", exc)
        return False


# ── Phase 8 — Graph update ────────────────────────────────────────────────────

def update_graph(
    input_text: str,
    intent: str,
    response: str,
    agent_results: list[dict[str, Any]],
    *,
    prev_intent: str = "",
) -> None:
    """Persist the exchange back into KnowledgeStore and MemoryIndex.

    Also builds edges between the current intent node and past nodes so the
    graph grows structured relationships rather than isolated entries.
    """
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

    # Fix 5 — create edges so the graph accumulates structure
    if prev_intent and prev_intent != intent:
        connect_nodes(prev_intent, intent, "precedes")
    for result in agent_results[:3]:
        skill = result.get("skill", "")
        if skill:
            connect_nodes(intent, skill, "executed_via")


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
            f"success={success} "
            f"degraded={run.degraded}"
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
                "degraded": run.degraded,
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
                "degraded": run.degraded,
            },
            risk_score=0.05,
        )
    except Exception as exc:
        logger.debug("AuditEngine record failed (non-fatal): %s", exc)


# ── Phase 10 — Hard integrity validation ──────────────────────────────────────

_FALLBACK_PREFIX = "System recovered:"


def validate_pipeline_integrity(run: _PipelineRun) -> None:
    """Check that all mandatory pipeline stages ran.

    When violations are found:
    - Sets ``run.degraded = True``
    - Logs a WARNING
    - Records to AuditEngine
    - Updates ``run.trace["violations"]``
    - Raises ``PipelineViolationError`` (caught by process_user_input which
      then appends the DEGRADED marker to the response — Fix 7)

    Checks:
    - graph was consulted (nodes, concepts, expanded, or past_decisions non-empty)
    - LLM was called
    - at least one task was structured (tasks_executed ≥ 1)
    - response is not the hardcoded fallback string
    """
    violations: list[str] = []

    gd = run.graph_data
    if not (
        (gd.get("nodes") or "").strip()
        or gd.get("concepts")
        or gd.get("past_decisions")
        or gd.get("expanded")
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

    # Fix 7 — mark run as degraded so caller can surface it
    run.degraded = True
    run.trace["degraded"] = True
    run.trace["violations"] = violations

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

    Raises:
        Any phase exception when ``STRICT_PIPELINE=1``.
    """
    run = _PipelineRun(input_text, user_id, mode, model_route)
    # Track previous intent for edge creation (see Phase 8)
    _prev_intent: str = ""

    def _phase(name: str, fn: Callable[[], Any], fallback: Callable[[], Any]) -> Any:
        """Run *fn()*, fall back to *fallback()* unless STRICT_PIPELINE."""
        try:
            return fn()
        except Exception as exc:
            if STRICT_PIPELINE:
                logger.error("Phase %s failed in STRICT_PIPELINE mode: %s", name, exc)
                raise
            logger.warning("Phase %s failed (degraded): %s", name, exc)
            run.degraded = True
            return fallback()

    # ── Phase 2: Graph retrieval ──────────────────────────────────────────────
    run.graph_data = _phase(
        "2 (graph retrieval)",
        lambda: retrieve_relevant_nodes(input_text),
        lambda: {"nodes": "", "concepts": [], "past_decisions": [], "expanded": []},
    )
    run.trace["retrieved_nodes"] = {
        "nodes_len": len(run.graph_data.get("nodes") or ""),
        "concepts": len(run.graph_data.get("concepts") or []),
        "past_decisions": len(run.graph_data.get("past_decisions") or []),
        "expanded": len(run.graph_data.get("expanded") or []),
    }

    # ── Phase 2b: Context building ────────────────────────────────────────────
    run.context = _phase(
        "2b (build context)",
        lambda: build_context(input_text, run.graph_data),
        lambda: "",
    )

    # ── Phase 3: Intent classification + agent selection ─────────────────────
    decision = _phase(
        "3 (decision)",
        lambda: classify_decision(input_text, run.graph_data),
        lambda: {
            "intent": "ops",
            "selected_agents": ["task-orchestrator"],
            "execution_plan": "fallback",
        },
    )
    run.intent = decision["intent"]
    run.selected_agents = decision["selected_agents"]
    run.execution_plan = decision["execution_plan"]
    run.trace["decision"] = {
        "intent": run.intent,
        "selected_agents": run.selected_agents,
        "execution_plan": run.execution_plan,
    }

    # ── Phase 4: LLM call (delegated to server.py via injected callable) ──────
    routed_agent = run.selected_agents[0] if run.selected_agents else "task-orchestrator"
    if route_to_agent_fn is not None:
        try:
            routed_agent = route_to_agent_fn(input_text)
        except Exception:
            pass

    def _call_llm() -> str:
        if generate_llm_response_fn is None:
            return f"[no LLM callable provided] input={input_text}"
        return generate_llm_response_fn(
            input_text,
            routed_agent,
            mode,
            model_route=model_route,
            user_id=user_id,
            graph_context=run.context,
        )

    run.llm_output = _phase(
        "4 (LLM call)",
        _call_llm,
        lambda: f"{_FALLBACK_PREFIX} LLM call failed",
    )
    run.llm_called = bool(run.llm_output) and not run.llm_output.startswith(_FALLBACK_PREFIX)

    # ── Phase 5: Task decomposition + schema validation ───────────────────────
    raw_tasks = _phase(
        "5 (decompose tasks)",
        lambda: decompose_to_tasks(run.llm_output, run.intent, run.selected_agents),
        lambda: [],
    )
    # Fix 3 — validate task schema (separate from decompose so it always runs)
    run.tasks = _phase(
        "5v (validate tasks)",
        lambda: validate_tasks(raw_tasks),
        lambda: [],
    )
    run.trace["validated_tasks"] = [
        {"agent": t.get("agent"), "intent": t.get("intent")} for t in run.tasks
    ]

    # ── Phase 6: Agent execution ──────────────────────────────────────────────
    run.agent_results = _phase(
        "6 (execute tasks)",
        lambda: execute_tasks(run.tasks, input_text),
        lambda: [],
    )
    run.tasks_executed = len(run.agent_results)
    run.trace["agent_results"] = [
        {
            "skill": r.get("skill"),
            "status": r.get("status"),
            "real_execution": r.get("real_execution", False),
        }
        for r in run.agent_results
    ]

    # ── Phase 7: Result aggregation ───────────────────────────────────────────
    run.final_response = _phase(
        "7 (format response)",
        lambda: format_response(
            run.llm_output, run.agent_results, routed_agent, degraded=run.degraded
        ),
        lambda: run.llm_output or f"{_FALLBACK_PREFIX} pipeline error",
    )

    # ── Phase 8: Graph update (non-blocking) ──────────────────────────────────
    _phase(
        "8 (graph update)",
        lambda: update_graph(
            input_text,
            run.intent,
            run.final_response,
            run.agent_results,
            prev_intent=_prev_intent,
        ),
        lambda: None,
    )

    # ── Phase 9: AscendForge monitoring (non-blocking) ────────────────────────
    _phase(
        "9 (ascend forge)",
        lambda: monitor_and_improve(run),
        lambda: None,
    )

    # ── Phase 10: Integrity validation ────────────────────────────────────────
    # When violations are found, run.degraded=True and DEGRADED marker is added
    # to the response so the UI debug panel can surface it.
    try:
        validate_pipeline_integrity(run)
    except PipelineViolationError as exc:
        logger.warning("Phase 10 (integrity check) violations: %s", exc)
        # Fix 7 — append DEGRADED marker if not already present
        if _DEGRADED_MARKER not in run.final_response:
            run.final_response += _DEGRADED_MARKER
        if STRICT_PIPELINE:
            raise

    # Fix 6 — finalise and store trace
    run.trace["final_output"] = run.final_response[:500]
    run.trace["latency_ms"] = round(run.elapsed_ms(), 1)
    run.trace["degraded"] = run.degraded
    _TRACE_STORE.append(run.trace)

    return run.final_response
