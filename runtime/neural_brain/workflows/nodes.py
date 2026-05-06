"""Individual workflow nodes for deep reasoning."""
import logging
import time
from typing import Any

from runtime.neural_brain.core.brain_state import BrainState
from runtime.neural_brain.core.intent_classifier import classify_intent
from runtime.neural_brain.api.node_bridge import emit
from runtime.neural_brain.core.reasoning_trace import ReasoningTrace

logger = logging.getLogger(__name__)


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
    from runtime.neural_brain.memory.neural_memory_manager import NeuralMemoryManager
    from runtime.neural_brain.graph.brain_graph import BrainGraph

    input_text = state.get("input", "")
    traces = state.get("trace", [])

    try:
        mem = NeuralMemoryManager()
        result = mem.recall(input_text, k=5)
        retrieved = result.get("results", [])

        graph = BrainGraph()
        neighbors = graph.neighborhood(limit=20)
        retrieved.extend([
            {"id": n.get("id"), "content": n.get("label"), "type": "concept", "score": 0.8}
            for n in neighbors.get("nodes", [])[:5]
        ])

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

    except Exception as e:
        latency_ms = (time.time() - start) * 1000
        logger.warning(f"retrieve_node failed: {e}")
        trace = ReasoningTrace(
            node="retrieve",
            input={"query": input_text},
            output={},
            latency_ms=latency_ms,
            status="error",
            error=str(e),
        )
        return {**state, "retrieved": [], "trace": traces + [trace]}


def plan_node(state: BrainState) -> BrainState:
    """Generate execution plan from context."""
    start = time.time()
    from runtime.core.orchestrator import get_llm_client

    input_text = state.get("input", "")
    retrieved = state.get("retrieved", [])
    intent = state.get("intent", "short")
    traces = state.get("trace", [])

    context = "\n".join([f"- {r.get('content', '')}" for r in retrieved[:5]])
    prompt = f"""Given this context:
{context}

Plan {intent} steps to accomplish: {input_text}

Respond with JSON: {{"steps": [{{"step": 1, "action": "...", "args": {{}}}}]}}"""

    try:
        client = get_llm_client()
        response = client.invoke(prompt)
        plan_text = response.get("output", "{}") if isinstance(response, dict) else response

        import json
        plan_data = json.loads(plan_text) if isinstance(plan_text, str) else plan_text
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
        logger.warning(f"plan_node failed: {e}")
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
    """Execute a skill or action."""
    start = time.time()
    plan = state.get("plan", [])
    cursor = state.get("cursor", 0)
    traces = state.get("trace", [])

    if cursor >= len(plan):
        return state  # No more actions

    current_step = plan[cursor]
    action = {"skill": current_step.get("action"), "args": current_step.get("args", {})}

    try:
        from runtime.skills.catalog import get_skill

        skill_name = action.get("skill")
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
        logger.warning(f"act_node failed: {e}")
        trace = ReasoningTrace(
            node="act",
            input=action,
            output={},
            latency_ms=latency_ms,
            status="error",
            error=str(e),
        )

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
    """Generate final output and save to memory."""
    start = time.time()
    from runtime.neural_brain.memory.neural_memory_manager import NeuralMemoryManager
    from runtime.core.orchestrator import get_llm_client

    input_text = state.get("input", "")
    retrieved = state.get("retrieved", [])
    action_results = state.get("action_result")
    traces = state.get("trace", [])
    user_id = state.get("user_id", "unknown")

    context = "\n".join([f"- {r.get('content', '')}" for r in retrieved[:3]])
    action_summary = f"Action result: {action_results}" if action_results else "No actions taken."

    prompt = f"""Summarize the answer to: {input_text}

Context: {context}
{action_summary}

Provide a concise, actionable summary (100-200 words)."""

    try:
        client = get_llm_client()
        response = client.invoke(prompt)
        output = response.get("output", response) if isinstance(response, dict) else response

        # Save to memory
        mem = NeuralMemoryManager()
        mem.remember(
            content=f"Q: {input_text}\nA: {output}",
            type="episodic",
            user_id=user_id,
            metadata={"intent": state.get("intent"), "source": "reasoning"},
        )

        latency_ms = (time.time() - start) * 1000
        trace = ReasoningTrace(
            node="synthesize",
            input={},
            output={"output_length": len(output)},
            latency_ms=latency_ms,
            status="success",
        )

        emit("nb:reasoning_step", {
            "trace_id": state.get("thread_id"),
            "node": "synthesize",
            "output_length": len(output),
            "latency_ms": latency_ms,
        })

        return {**state, "output": output, "trace": traces + [trace]}

    except Exception as e:
        latency_ms = (time.time() - start) * 1000
        logger.warning(f"synthesize_node failed: {e}")
        trace = ReasoningTrace(
            node="synthesize",
            input={},
            output={},
            latency_ms=latency_ms,
            status="error",
            error=str(e),
        )
        return {**state, "output": "Unable to synthesize response.", "trace": traces + [trace]}
