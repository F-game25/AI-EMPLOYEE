#!/usr/bin/env python3
"""AI Employee — Single Entrypoint

This is the ONLY file that should be executed to start the AI Employee system.
It initialises the orchestrator, the internal engine, and launches all services.

Usage::

    python main.py              # start everything (UI + agents)
    python main.py --preflight  # run preflight checks only, do not start
    python main.py --help       # show options

The internal engine (formerly OpenClaw) is initialised here and is never started
directly.  All agent and orchestrator access to LLM / memory / input-processing
goes through ``runtime/engine/api.py``.
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
    _init_engine()

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
