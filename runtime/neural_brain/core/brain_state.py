"""Unified state schema for LangGraph workflows."""
from typing import TypedDict, Any


class BrainState(TypedDict, total=False):
    """Complete state passed through the reasoning graph.

    total=False means all fields are optional, allowing gradual state construction.
    """
    # Input/context
    input: str
    user_id: str
    thread_id: str
    force: bool

    # Classification
    intent: str  # short, deep, multimodal, agent, embed_only

    # Retrieval results
    retrieved: list[dict[str, Any]]  # [{id, content, score, type}]

    # Planning
    plan: list[dict[str, Any]]  # [{step, action, args}]

    # Execution state
    cursor: int  # Current step in plan
    action: dict[str, Any] | None  # {skill, args}
    action_result: dict[str, Any] | None  # {status, output, error?}
    verification: dict[str, Any] | None  # {passed, issues}

    # Output
    output: str | None
    trace: list[dict[str, Any]]  # [{node, intent, status, latency_ms, metadata}]
