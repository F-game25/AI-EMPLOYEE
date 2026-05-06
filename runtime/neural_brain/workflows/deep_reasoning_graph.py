"""LangGraph StateGraph for multi-step reasoning."""
from langgraph.graph import StateGraph, END

from runtime.neural_brain.core.brain_state import BrainState
from runtime.neural_brain.workflows.nodes import (
    classify_node,
    retrieve_node,
    plan_node,
    act_node,
    synthesize_node,
)


def build_reasoning_graph():
    """Construct the complete reasoning workflow.

    Flow: classify → retrieve → plan → act? → synthesize → END
    """
    graph = StateGraph(BrainState)

    # Add nodes
    graph.add_node("classify", classify_node)
    graph.add_node("retrieve", retrieve_node)
    graph.add_node("plan", plan_node)
    graph.add_node("act", act_node)
    graph.add_node("synthesize", synthesize_node)

    # Wire edges
    graph.add_edge("classify", "retrieve")
    graph.add_edge("retrieve", "plan")

    # Conditional: act only if plan has steps
    def should_act(state: BrainState) -> str:
        plan = state.get("plan", [])
        cursor = state.get("cursor", 0)
        if cursor < len(plan):
            return "act"
        return "synthesize"

    graph.add_conditional_edges("plan", should_act, {"act": "act", "synthesize": "synthesize"})

    # After act, loop back to plan to check next step
    def next_after_act(state: BrainState) -> str:
        cursor = state.get("cursor", 0)
        plan = state.get("plan", [])
        # Increment cursor and check if more actions remain
        new_cursor = cursor + 1
        if new_cursor < len(plan) and new_cursor < 5:  # Max 5 actions per session
            state["cursor"] = new_cursor
            return "act"
        return "synthesize"

    graph.add_conditional_edges("act", next_after_act, {"act": "act", "synthesize": "synthesize"})

    graph.add_edge("synthesize", END)

    # Set entry point
    graph.set_entry_point("classify")

    return graph.compile()
