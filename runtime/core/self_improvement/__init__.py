"""Self-Improvement Loop — closed-loop system for safe, controlled code improvement.

Architecture
────────────
    Analyze → Plan → Build → Test → Approve → Deploy → Learn

Every improvement flows through hard gates:
  1. **Planner AI** — analyses the system and produces a read-only plan.
  2. **Builder AI** — generates unified diffs in a sandbox (never full rewrites).
  3. **Diff Policy** — enforces size limits, protected paths, and format rules.
  4. **Tester Gate** — runs lint, tests, and security checks. One fail = reject.
  5. **Controller**  — manual or semi-auto approval; deploys or rolls back.
  6. **Learning**    — feeds outcomes back to strategy_store and neural brain.

All modules are importable individually or via this package::

    from core.self_improvement import get_improvement_queue
    from core.self_improvement import get_improvement_controller
"""
from __future__ import annotations


def get_improvement_queue():
    from core.self_improvement.queue import get_queue
    return get_queue()


def get_improvement_controller():
    from core.self_improvement.controller import get_controller
    return get_controller()


def get_improvement_telemetry():
    from core.self_improvement.telemetry import get_telemetry
    return get_telemetry()


__all__ = [
    "get_improvement_queue",
    "get_improvement_controller",
    "get_improvement_telemetry",
]
