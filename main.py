#!/usr/bin/env python3
"""AI Employee — Single Entrypoint

This is the ONLY file that should be executed to start the AI Employee system.
It initialises the orchestrator, the internal engine, memory router,
self-learning brain, and launches all services.

Usage::

    python main.py              # start everything (UI + agents)
    python main.py --preflight  # run preflight checks only, do not start
    python main.py --help       # show options

The internal engine (formerly OpenClaw) is initialised here and is never started
directly.  All agent and orchestrator access to LLM / memory / input-processing
goes through ``runtime/engine/api.py``.

Data flow::

    INPUT → core/orchestrator.py
              → core/decision_engine.py     (route to best agent)
              → core/self_learning_brain.py (suggest + learn)
              → agent execution
              → memory/memory_router.py     (store outcome)
              → self_learning_brain.record_outcome()  (reinforce)
"""
from __future__ import annotations

import argparse
import logging
import os
import subprocess
import sys
from pathlib import Path

# ── Resolve paths ─────────────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).resolve().parent
RUNTIME_DIR = REPO_ROOT / "runtime"

# Put runtime/ on sys.path so that ``from engine.api import …`` and
# ``from core.orchestrator import …`` resolve without a package install.
if str(RUNTIME_DIR) not in sys.path:
    sys.path.insert(0, str(RUNTIME_DIR))

# ── Logging ───────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=getattr(logging, os.environ.get("LOG_LEVEL", "INFO").upper(), logging.INFO),
    format="%(asctime)s [ai-employee] %(levelname)s — %(message)s",
)
logger = logging.getLogger("main")


# ── Internal engine bootstrap ─────────────────────────────────────────────────

def _init_engine() -> None:
    """Initialise the internal engine (no external binary is started)."""
    try:
        import engine  # noqa: F401 — triggers engine/__init__.py
        logger.info("Internal engine initialised")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Engine init warning (non-fatal): %s", exc)


# ── Self-learning brain ───────────────────────────────────────────────────────

def _init_self_learning_brain() -> None:
    """Initialise the self-learning brain singleton."""
    try:
        from core.self_learning_brain import get_self_learning_brain
        slb = get_self_learning_brain()
        metrics = slb.metrics()
        logger.info(
            "Self-learning brain ready — avg_reward=%.3f, outcomes=%d",
            metrics.get("avg_reward_recent", 0.0),
            metrics.get("total_outcomes_recorded", 0),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Self-learning brain init warning (non-fatal): %s", exc)


# ── Memory router ─────────────────────────────────────────────────────────────

def _init_memory_router() -> None:
    """Initialise the memory router (short-term cache + vector store)."""
    try:
        from memory.memory_router import get_memory_router
        router = get_memory_router()
        health = router.health()
        logger.info(
            "Memory router ready — cache=%d, vector=%d",
            health.get("cache_live_entries", 0),
            health.get("vector_entries", {}).get("total", 0),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Memory router init warning (non-fatal): %s", exc)


# ── UI API server ─────────────────────────────────────────────────────────────

def _start_ui_api_server() -> None:
    """Start the UI API server in a background daemon thread."""
    try:
        from ui.api_server import start_api_server_thread
        start_api_server_thread()
    except ImportError:
        logger.debug("FastAPI/uvicorn not installed — UI API server skipped.")
    except Exception as exc:  # noqa: BLE001
        logger.warning("UI API server start warning (non-fatal): %s", exc)


# ── Version control ───────────────────────────────────────────────────────────

def _init_version_control() -> None:
    """Initialise the version control singleton."""
    try:
        from runtime.version_control import get_version_control
        vc = get_version_control()
        summary = vc.summary()
        logger.info(
            "Version control ready — %d snapshots (%d deployed, %d rolled back)",
            summary.get("total_snapshots", 0),
            summary.get("deployed", 0),
            summary.get("rolled_back", 0),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Version control init warning (non-fatal): %s", exc)


# ── Forge controller ──────────────────────────────────────────────────────────

def _init_forge_controller() -> None:
    """Initialise the Forge Controller (safe-modification gateway)."""
    try:
        from core.forge_controller import get_forge_controller
        get_forge_controller()
        logger.info("Forge controller ready")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Forge controller init warning (non-fatal): %s", exc)


# ── V4: Economy engine ────────────────────────────────────────────────────────

def _init_economy_engine() -> None:
    """Initialise the internal economy engine."""
    try:
        from core.economy_engine import get_economy_engine
        eco = get_economy_engine()
        summary = eco.system_summary()
        logger.info(
            "Economy engine ready — agents=%d, global_profit=%.2f, global_roi=%.4f",
            summary.get("total_agents", 0),
            summary.get("global_profit", 0.0),
            summary.get("global_roi", 0.0),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Economy engine init warning (non-fatal): %s", exc)


# ── V4: Agent competition engine ──────────────────────────────────────────────

def _init_competition_engine() -> None:
    """Initialise the agent competition engine."""
    try:
        from core.agent_competition_engine import get_competition_engine
        get_competition_engine()
        logger.info("Agent competition engine ready")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Competition engine init warning (non-fatal): %s", exc)


# ── V4: Optimizer agent background loop ───────────────────────────────────────

def _start_optimizer_agent() -> None:
    """Start the optimizer agent background scan loop."""
    try:
        from agents.optimizer_agent import get_optimizer_agent
        get_optimizer_agent().start_background_loop()
        logger.info("Optimizer agent background loop started")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Optimizer agent start warning (non-fatal): %s", exc)


# ── Preflight checks ──────────────────────────────────────────────────────────

def _run_preflight() -> int:
    """Run the runtime preflight script and return its exit code."""
    preflight = RUNTIME_DIR / "core" / "startup.py"
    if not preflight.exists():
        logger.error("Preflight script not found: %s", preflight)
        return 1
    result = subprocess.run(
        [sys.executable, str(preflight), "--preflight"],
        cwd=str(REPO_ROOT),
    )
    return result.returncode


# ── Service launcher ──────────────────────────────────────────────────────────

def _start_services() -> int:
    """Launch UI + agents via the runtime start script.

    The start script is the orchestrated launcher for all Python agents.
    It does NOT start any external gateway binary — that dependency has been
    removed.  The internal engine provides all gateway functionality.
    """
    start_sh = RUNTIME_DIR / "start.sh"
    if not start_sh.exists():
        logger.error("Runtime start script not found: %s", start_sh)
        return 1
    try:
        result = subprocess.run(
            ["bash", str(start_sh)],
            cwd=str(REPO_ROOT),
            env={**os.environ, "AI_EMPLOYEE_REPO_DIR": str(REPO_ROOT)},
        )
        return result.returncode
    except KeyboardInterrupt:
        logger.info("Interrupted — shutting down.")
        return 0


# ── CLI ───────────────────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="AI Employee — autonomous AI operating system",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Run without flags to start the full system (UI + all agents).",
    )
    parser.add_argument(
        "--preflight",
        action="store_true",
        help="Run preflight checks only; do not start services.",
    )
    parser.add_argument(
        "--no-preflight",
        action="store_true",
        help="Skip preflight checks and start immediately.",
    )
    return parser.parse_args()


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    args = _parse_args()

    logger.info("AI Employee starting (engine: internal)")

    # Initialise subsystems in dependency order
    _init_engine()
    _init_memory_router()
    _init_self_learning_brain()
    _init_version_control()
    _init_forge_controller()
    _init_economy_engine()
    _init_competition_engine()
    _start_optimizer_agent()
    _start_ui_api_server()

    if args.preflight:
        return _run_preflight()

    if not args.no_preflight:
        rc = _run_preflight()
        if rc != 0:
            logger.error("Preflight failed (exit %d) — aborting startup.", rc)
            return rc

    return _start_services()


if __name__ == "__main__":
    sys.exit(main())
