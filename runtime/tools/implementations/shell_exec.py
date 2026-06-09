"""Sandboxed shell execution tool.

Risk level 2 — local side-effects only. Blocked command patterns prevent
destructive operations and exfiltration.
"""
from __future__ import annotations

import logging
import os
import re
import shlex
import subprocess

logger = logging.getLogger("tools.shell_exec")

_BLOCKED_PATTERNS = [
    r"\brm\s+-[rf]",
    r"\bdd\b",
    r"\bmkfs\b",
    r"\bformat\b",
    r">\s*/dev/",
    r"\bchmod\s+777\b",
    r"\bsudo\b",
    r"\bsu\s+",
    r"\bcurl\s+.*\s*\|",        # curl | bash
    r"\bwget\s+.*\s*\|",
    r"\beval\b",
    r"&\s*>/dev/null\s*&",      # background disown pattern
]
_BLOCKED_RE = re.compile("|".join(_BLOCKED_PATTERNS), re.IGNORECASE)

_ALLOWED_ENVS = {
    "PATH", "HOME", "LANG", "LC_ALL", "VIRTUAL_ENV", "PYTHONPATH",
    "NODE_PATH", "NPM_CONFIG_PREFIX",
}


def shell_exec(command: str, cwd: str = "/tmp", timeout: int = 30, **_) -> dict:
    """Run a shell command in a restricted environment.

    Args:
        command: Shell command string.
        cwd:     Working directory (defaults to /tmp).
        timeout: Max seconds (default 30, capped at 120).

    Returns:
        {"stdout": str, "stderr": str, "returncode": int, "ok": bool}
    """
    if _BLOCKED_RE.search(command):
        logger.warning("shell_exec blocked dangerous command: %s", command[:80])
        return {"stdout": "", "stderr": "Command blocked by safety filter.", "returncode": -1, "ok": False}

    timeout = min(int(timeout), 120)

    # Sanitized env — only safe variables
    env = {k: v for k, v in os.environ.items() if k in _ALLOWED_ENVS}
    env["HOME"] = os.environ.get("HOME", "/tmp")

    # Resolve cwd safely
    if not os.path.isabs(cwd):
        cwd = "/tmp"
    if not os.path.isdir(cwd):
        os.makedirs(cwd, exist_ok=True)

    try:
        proc = subprocess.run(
            command,
            shell=True,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
        return {
            "stdout": proc.stdout[:8000],
            "stderr": proc.stderr[:2000],
            "returncode": proc.returncode,
            "ok": proc.returncode == 0,
        }
    except subprocess.TimeoutExpired:
        return {"stdout": "", "stderr": f"Timed out after {timeout}s", "returncode": -1, "ok": False}
    except Exception as exc:
        logger.error("shell_exec error: %s", exc)
        return {"stdout": "", "stderr": str(exc), "returncode": -1, "ok": False}
