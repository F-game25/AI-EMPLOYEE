"""Evolution Engine — self-improvement control plane (MASTER_PLAN_V3 phase P7).

Hard constraints (enforced throughout the package):
  - NON-BLOCKING on the live path. Trace hooks append to an in-memory deque and
    return in <5ms; all disk I/O happens on a background flush thread.
  - ASYNC/OFFLINE for heavy work (scoring, classification, reflection,
    distillation feed building, replay). None of it runs on the request path.
  - SECRET-REDACTING. Everything is scrubbed via `scrub()` before any persist,
    mirroring `backend/services/forge_learning.js::scrubSecretsFromLearningData`.
  - DOES NOT DUPLICATE DISTILLATION. The existing distiller in
    `backend/services/forge_learning.js` (scoreTrajectory / buildDistillationRecord
    / createPreferencePairs / ...) is the single owner of distillation execution.
    `distillation_adapter.py` only produces clean feed rows and hands them off.

State lives under ``~/.ai-employee/evolution/`` with subdirs:
  traces/ lessons/ candidates/ benchmarks/ metrics/ distillation_feeds/

When EVOLUTION_ENABLED is false, all collectors no-op cheaply.
"""
from __future__ import annotations

import os
from pathlib import Path

EVOLUTION_ENABLED: bool = os.environ.get("EVOLUTION_ENABLED", "true").lower() != "false"

# Root state dir, matching the project pattern (deep_research_engine.py lines 30-32).
EVOLUTION_DIR = Path(os.path.expanduser("~")) / ".ai-employee" / "evolution"
TRACES_DIR = EVOLUTION_DIR / "traces"
LESSONS_DIR = EVOLUTION_DIR / "lessons"
CANDIDATES_DIR = EVOLUTION_DIR / "candidates"
BENCHMARKS_DIR = EVOLUTION_DIR / "benchmarks"
METRICS_DIR = EVOLUTION_DIR / "metrics"
DISTILL_FEED_DIR = EVOLUTION_DIR / "distillation_feeds"

_SUBDIRS = (
    TRACES_DIR, LESSONS_DIR, CANDIDATES_DIR,
    BENCHMARKS_DIR, METRICS_DIR, DISTILL_FEED_DIR,
)


def ensure_dirs() -> None:
    """Create the evolution state directory tree (idempotent, lazy)."""
    for d in _SUBDIRS:
        d.mkdir(parents=True, exist_ok=True, mode=0o700)


__all__ = [
    "EVOLUTION_ENABLED",
    "EVOLUTION_DIR",
    "TRACES_DIR",
    "LESSONS_DIR",
    "CANDIDATES_DIR",
    "BENCHMARKS_DIR",
    "METRICS_DIR",
    "DISTILL_FEED_DIR",
    "ensure_dirs",
]
