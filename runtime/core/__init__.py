"""AI Employee core package.

Re-exports the key singletons so callers can do::

    from core import get_brain, get_intelligence, get_hybrid_mode
    from core import get_changelog, get_roi_tracker, get_decision_engine
    from core import get_mode_manager, get_task_engine, get_skill_registry
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
