"""Individual workflow nodes for deep reasoning.

ARCHITECTURE NOTE: These nodes run inside the LangGraph graph that
ConsciousnessEngine.think() invokes. Direct calls to get_memory() and
ModelArchitectureRouter here are KERNEL-INTERNAL — they are NOT API bypasses.
External code must NEVER import these functions directly; all entry points
flow through ConsciousnessEngine.process_input().
"""
import asyncio
import logging
import time

from neural_brain.core.brain_state import BrainState
from neural_brain.core.intent_classifier import classify_intent
from neural_brain.api.node_bridge import emit
from neural_brain.core.reasoning_trace import ReasoningTrace


def _route(arch: str, request: dict) -> dict:
    """Kernel-internal model dispatch. Always respects privacy gate + performance tracker."""
    from neural_brain.models.model_architecture_router import ModelArchitectureRouter
    return ModelArchitectureRouter.route(arch, request)

logger = logging.getLogger(__name__)


def _run_async(coro):
    """Run an async coroutine from a sync context (LangGraph worker thread)."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Already inside an event loop (e.g. pytest-asyncio) — use thread
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                return pool.submit(asyncio.run, coro).result()
        return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


def classify_node(state: BrainState) -> BrainState:
    """Route input to appropriate reasoning depth."""
    start = time.time()
    input_text = state.get("input", "")
    intent = classify_intent(input_text)
    latency_ms = (time.time() - start) * 1000

    trace = ReasoningTrace(
        node="classify",
        input={"input": input_text},
        output={"intent": intent},
        latency_ms=latency_ms,
        status="success",
    )

    emit("nb:reasoning_step", {
        "trace_id": state.get("thread_id"),
        "node": "classify",
        "intent": intent,
        "latency_ms": latency_ms,
    })

    return {**state, "intent": intent, "trace": [trace]}


def retrieve_node(state: BrainState) -> BrainState:
    """Retrieve relevant context from memory and graph."""
    start = time.time()
    from neural_brain.memory import get_memory
    from neural_brain.graph import get_brain_graph

    input_text = state.get("input", "")
    traces = state.get("trace", [])
    retrieved = []

    try:
        mem = get_memory()
        result = _run_async(mem.recall(input_text, k=5))
        retrieved = result.get("results", [])
    except Exception as e:
        logger.warning("retrieve_node memory recall failed: %s", e)

    try:
        graph = get_brain_graph()
        if graph is not None:
            neighbors = graph.neighborhood(seed_ids=None, limit=20)
            retrieved.extend([
                {"id": n.get("id"), "content": n.get("label"), "type": "concept", "score": 0.8}
                for n in neighbors.get("nodes", [])[:5]
            ])
    except Exception as e:
        logger.warning("retrieve_node graph failed: %s", e)

    latency_ms = (time.time() - start) * 1000
    trace = ReasoningTrace(
        node="retrieve",
        input={"query": input_text},
        output={"count": len(retrieved)},
        latency_ms=latency_ms,
        status="success",
    )

    emit("nb:reasoning_step", {
        "trace_id": state.get("thread_id"),
        "node": "retrieve",
        "count": len(retrieved),
        "latency_ms": latency_ms,
    })

    return {**state, "retrieved": retrieved, "trace": traces + [trace]}


def plan_node(state: BrainState) -> BrainState:
    """Generate execution plan — uses LLM for deep reasoning."""
    start = time.time()

    input_text = state.get("input", "")
    retrieved = state.get("retrieved", [])
    intent = state.get("intent", "short")
    traces = state.get("trace", [])

    context = "\n".join([f"- {r.get('content', '')}" for r in retrieved[:5]])
    prompt = (
        f"Given this context:\n{context}\n\n"
        f"Plan {intent} steps to accomplish: {input_text}\n\n"
        'Respond with JSON: {"steps": [{"step": 1, "action": "...", "args": {}}]}'
    )

    try:
        result = _route("LLM", {"prompt": prompt, "max_tokens": 512})
        plan_text = result.get("output") or result.get("text") or "{}"

        import json
        try:
            plan_data = json.loads(plan_text)
        except Exception:
            plan_data = {}
        plan = plan_data.get("steps", [])

        latency_ms = (time.time() - start) * 1000
        trace = ReasoningTrace(
            node="plan",
            input={"intent": intent},
            output={"steps": len(plan)},
            latency_ms=latency_ms,
            status="success",
        )

        emit("nb:reasoning_step", {
            "trace_id": state.get("thread_id"),
            "node": "plan",
            "steps": len(plan),
            "latency_ms": latency_ms,
        })

        return {**state, "plan": plan, "cursor": 0, "trace": traces + [trace]}

    except Exception as e:
        latency_ms = (time.time() - start) * 1000
        logger.warning("plan_node failed: %s", e)
        trace = ReasoningTrace(
            node="plan",
            input={"intent": intent},
            output={},
            latency_ms=latency_ms,
            status="error",
            error=str(e),
        )
        return {**state, "plan": [], "cursor": 0, "trace": traces + [trace]}


def act_node(state: BrainState) -> BrainState:
    """Execute a skill or action — uses LAM for action calls."""
    start = time.time()
    plan = state.get("plan", [])
    cursor = state.get("cursor", 0)
    traces = state.get("trace", [])

    if cursor >= len(plan):
        return state

    current_step = plan[cursor]
    action = {"skill": current_step.get("action"), "args": current_step.get("args", {})}
    skill_name = action.get("skill", "")

    try:
        from skills.catalog import get_skill
        skill = get_skill(skill_name)
        result = skill.run(**action.get("args", {}))

        latency_ms = (time.time() - start) * 1000
        trace = ReasoningTrace(
            node="act",
            input=action,
            output={"result": str(result)[:200]},
            latency_ms=latency_ms,
            status="success",
        )

        emit("nb:action_call", {
            "skill": skill_name,
            "args_preview": str(action.get("args", {}))[:80],
            "status": "success",
            "latency_ms": latency_ms,
        })
        emit("nb:reasoning_step", {
            "trace_id": state.get("thread_id"),
            "node": "act",
            "skill": skill_name,
            "status": "success",
            "latency_ms": latency_ms,
        })

        return {
            **state,
            "action": action,
            "action_result": {"status": "success", "output": result},
            "trace": traces + [trace],
        }

    except Exception as e:
        latency_ms = (time.time() - start) * 1000
        logger.warning("act_node failed: %s", e)
        trace = ReasoningTrace(
            node="act",
            input=action,
            output={},
            latency_ms=latency_ms,
            status="error",
            error=str(e),
        )

        # LAM fallback — ask LLM to synthesize an action result
        try:
            lam_result = _route("LAM", {
                "skill": skill_name,
                "args": action.get("args", {}),
                "context": state.get("input", ""),
            })
            fallback_output = lam_result.get("output") or f"Simulated execution of {skill_name}"
            return {
                **state,
                "action": action,
                "action_result": {"status": "fallback", "output": fallback_output},
                "trace": traces + [trace],
            }
        except Exception:
            pass

        emit("nb:reasoning_step", {
            "trace_id": state.get("thread_id"),
            "node": "act",
            "status": "error",
            "error": str(e)[:100],
            "latency_ms": latency_ms,
        })

        return {
            **state,
            "action": action,
            "action_result": {"status": "error", "error": str(e)},
            "trace": traces + [trace],
        }


def synthesize_node(state: BrainState) -> BrainState:
    """Generate final output (SLM for speed), save to memory."""
    start = time.time()
    from neural_brain.memory import get_memory

    input_text = state.get("input", "")
    retrieved = state.get("retrieved", [])
    action_results = state.get("action_result")
    traces = state.get("trace", [])
    user_id = state.get("user_id", "unknown")

    context = "\n".join([f"- {r.get('content', '')}" for r in retrieved[:3]])
    action_summary = f"Action result: {action_results}" if action_results else "No actions taken."

    prompt = (
        f"Summarize the answer to: {input_text}\n\n"
        f"Context: {context}\n{action_summary}\n\n"
        "Provide a concise, actionable summary (100-200 words)."
    )

    output = "Unable to synthesize response."
    status = "error"
    error_msg = None

    try:
        result = _route("SLM", {"prompt": prompt, "max_tokens": 300})
        output = result.get("output") or result.get("text") or output
        status = "success"
    except Exception as e:
        logger.warning("synthesize_node SLM failed, falling back to LLM: %s", e)
        try:
            result = _route("LLM", {"prompt": prompt, "max_tokens": 300})
            output = result.get("output") or result.get("text") or output
            status = "success"
        except Exception as e2:
            error_msg = str(e2)
            logger.warning("synthesize_node LLM fallback also failed: %s", e2)

    # Async memory write — fire and don't block if it fails
    try:
        mem = get_memory()
        _run_async(mem.remember(
            content=f"Q: {input_text}\nA: {output}",
            type="episodic",
            user_id=user_id,
            metadata={"intent": state.get("intent"), "source": "reasoning"},
        ))
    except Exception as e:
        logger.warning("synthesize_node memory write failed: %s", e)

    latency_ms = (time.time() - start) * 1000
    trace = ReasoningTrace(
        node="synthesize",
        input={},
        output={"output_length": len(output)},
        latency_ms=latency_ms,
        status=status,
        error=error_msg,
    )

    emit("nb:reasoning_step", {
        "trace_id": state.get("thread_id"),
        "node": "synthesize",
        "output_length": len(output),
        "latency_ms": latency_ms,
    })

    return {**state, "output": output, "trace": traces + [trace]}
