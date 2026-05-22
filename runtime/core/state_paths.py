"""Canonical state-directory resolver.

Single source of truth for where runtime state lives. `start.sh` exports
`STATE_DIR=<AI_HOME>/state` (default `~/.ai-employee/state`) and the Node backend
reads from there. Several modules historically used `AI_EMPLOYEE_STATE_DIR` with a
*relative* `"state"` default, so they wrote into the repo-local `./state` instead —
splitting state across two dirs (e.g. llm_calls.jsonl written repo-local but read
from ~/.ai-employee/state). Everything must resolve through here.
"""
import os
from pathlib import Path


def canonical_state_dir() -> Path:
    explicit = os.environ.get("STATE_DIR") or os.environ.get("AI_EMPLOYEE_STATE_DIR")
    if explicit:
        return Path(explicit).resolve()
    home = Path(
        os.environ.get("AI_EMPLOYEE_HOME")
        or os.environ.get("AI_HOME")
        or Path.home() / ".ai-employee"
    )
    return (home / "state").resolve()
