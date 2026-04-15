"""AI Employee core package — shared infrastructure for AI Employee.

Re-exports the key singletons so callers can do::

    from core import get_brain, get_intelligence, get_hybrid_mode
    from core import get_changelog, get_roi_tracker, get_decision_engine
    from core import get_mode_manager, get_task_engine, get_skill_registry

Modules
-------
skill_registry  Unified manifest of all agents + skills, Decision Engine,
                ROI Tracker, and Change Log.
change_log      Cross-session JSONL audit trail.
roi_tracker     Per-action revenue/cost tracker (SQLite).
decision_engine Profit/speed/complexity scorer with auto-tunable weights.
mode_manager    AUTO / MANUAL / BLACKLIGHT global mode (persisted).
task_engine     3-layer Planner / Executor / Validator pipeline.
money_mode      Content pipeline orchestration + affiliate drafting.
"""
from __future__ import annotations

# ── Lazy re-exports — only import what's actually available ───────────────────


def get_changelog():
    from core.change_log import get_changelog as _f
    return _f()


def get_roi_tracker():
    from core.roi_tracker import get_roi_tracker as _f
    return _f()


def get_decision_engine():
    from core.decision_engine import get_decision_engine as _f
    return _f()


def get_mode_manager():
    from core.mode_manager import get_mode_manager as _f
    return _f()


def get_task_engine():
    from core.task_engine import get_task_engine as _f
    return _f()


def get_agent_controller():
    from core.agent_controller import get_agent_controller as _f
    return _f()


def get_skill_registry():
    from core.skill_registry import get_registry as _f
    return _f()


def get_pipeline_store():
    from core.pipeline_store import get_pipeline_store as _f
    return _f()


# Optional — only available when runtime/brain is on sys.path
def get_brain():
    from brain.brain import get_brain as _f
    return _f()


def get_intelligence():
    from brain.intelligence import get_intelligence as _f
    return _f()


def get_hybrid_mode():
    from agents.ai_router.hybrid_mode import get_hybrid_mode as _f
    return _f()


def get_brain_registry():
    from core.brain_registry import brain as _brain
    return _brain


def get_improvement_queue():
    from core.self_improvement.queue import get_queue as _f
    return _f()


def get_improvement_controller():
    from core.self_improvement.controller import get_controller as _f
    return _f()


def get_improvement_telemetry():
    from core.self_improvement.telemetry import get_telemetry as _f
    return _f()


def get_objective_store():
    from core.objectives import get_objective_store as _f
    return _f()


def get_ascend_forge_executor():
    from core.ascend_forge import get_ascend_forge_executor as _f
    return _f()


def get_evolution_controller():
    from core.self_evolution.evolution_controller import get_evolution_controller as _f
    return _f()


def get_evolution_memory():
    from core.self_evolution.evolution_memory import get_evolution_memory as _f
    return _f()


def get_observability_event_stream():
    from core.observability.event_stream import get_event_stream as _f
    return _f()


def get_metrics_collector():
    from core.observability.metrics_collector import get_metrics_collector as _f
    return _f()


__all__ = [
    "get_changelog",
    "get_roi_tracker",
    "get_decision_engine",
    "get_mode_manager",
    "get_task_engine",
    "get_agent_controller",
    "get_skill_registry",
    "get_pipeline_store",
    "get_brain",
    "get_intelligence",
    "get_hybrid_mode",
    "get_brain_registry",
    "get_improvement_queue",
    "get_improvement_controller",
    "get_improvement_telemetry",
    "get_objective_store",
    "get_ascend_forge_executor",
    "get_evolution_controller",
    "get_evolution_memory",
    "get_observability_event_stream",
    "get_metrics_collector",
]
