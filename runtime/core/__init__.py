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


def get_skill_registry():
    from core.skill_registry import get_registry as _f
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


__all__ = [
    "get_changelog",
    "get_roi_tracker",
    "get_decision_engine",
    "get_mode_manager",
    "get_task_engine",
    "get_skill_registry",
    "get_brain",
    "get_intelligence",
    "get_hybrid_mode",
]
