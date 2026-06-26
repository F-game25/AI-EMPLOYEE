"""Sandboxed shell execution tool — allowlist + controlled-pipelines policy.

Risk level 2 — local side-effects only. Hardening (M1):
  * ``shell=False`` — no shell ever interprets the command, so ``; & < > $(...) ` ``
    are inert (passed literally to the program), never executed.
  * Executables are ALLOWLISTED by basename, sourced from ``security.yml``
    (``tools.shell_exec.allowed_commands``) — never hardcoded. Deny-by-default:
    an empty/missing allowlist blocks everything.
  * Only ``|`` pipes between allowlisted commands are permitted (controlled
    pipelines). Any other shell operator (``; & && || < > >> ( )``) is rejected.
  * Host env is stripped to a safe allowlist (no secrets reach the child).
  * cwd is scoped, output truncated, runtime capped.

NOTE: interpreters that may appear in the allowlist (python/node/make/npm) can
themselves run arbitrary code — that residual risk is contained by the surrounding
sandbox (Docker/process isolation), not this tool. See
docs/governance/SECURITY_RISK_REGISTER.md (SR-02, SR-16).
"""
from __future__ import annotations

import logging
import os
import shlex
import subprocess
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger("tools.shell_exec")

# Safe env allowlist — only these host variables reach the child (no secrets).
_ALLOWED_ENVS = {
    "PATH", "HOME", "LANG", "LC_ALL", "VIRTUAL_ENV", "PYTHONPATH",
    "NODE_PATH", "NPM_CONFIG_PREFIX",
}
_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "security.yml"
_OPERATOR_CHARS = "();<>|&"


@lru_cache(maxsize=1)
def _allowed_commands() -> frozenset:
    """Allowlisted executable basenames from ``security.yml``. Deny-by-default:
    any failure to load (missing file, no PyYAML, missing key) yields an empty
    set so nothing runs."""
    try:
        import yaml
        data = yaml.safe_load(_CONFIG_PATH.read_text(encoding="utf-8")) or {}
        raw = (((data.get("tools") or {}).get("shell_exec") or {})
               .get("allowed_commands")) or []
        return frozenset(str(c).strip() for c in raw if str(c).strip())
    except Exception as exc:  # noqa: BLE001 — fail closed
        logger.warning("shell_exec allowlist unavailable (deny-all): %s", exc)
        return frozenset()


def _parse_pipeline(command: str):
    """Quote-aware tokenise and split into argv stages on ``|``. Reject every
    other shell operator and any non-allowlisted executable.

    Returns ``(stages, "")`` on success or ``(None, reason)`` on rejection.
    """
    try:
        lex = shlex.shlex(command, posix=True, punctuation_chars=True)
        lex.whitespace_split = True
        tokens = list(lex)
    except ValueError as exc:
        return None, f"unparseable command: {exc}"

    stages: list[list[str]] = []
    cur: list[str] = []
    for tok in tokens:
        # Operator tokens are built solely from punctuation chars (quoted
        # punctuation stays inside a word, so awk '{...}' is untouched).
        if tok and all(c in _OPERATOR_CHARS for c in tok):
            if tok == "|":
                if not cur:
                    return None, "empty pipeline stage"
                stages.append(cur)
                cur = []
            else:
                return None, f"disallowed shell operator '{tok}' (only '|' pipes permitted)"
        else:
            cur.append(tok)
    if cur:
        stages.append(cur)
    if not stages or any(not s for s in stages):
        return None, "empty command"

    allowed = _allowed_commands()
    if not allowed:
        return None, "no command allowlist configured (deny-by-default)"
    for argv in stages:
        exe = argv[0]
        # Reject path-qualified executables (./echo, /tmp/echo, ..\\bin) so a bare
        # allowlisted name can ONLY resolve via PATH — never a binary planted in
        # the (world-writable) cwd. shell=False already prevents shell resolution.
        if "/" in exe or "\\" in exe or os.sep in exe or (os.altsep and os.altsep in exe):
            return None, f"executable must be a bare command name, not a path: '{exe}'"
        if exe not in allowed:
            return None, f"command '{exe}' is not allowlisted"
    return stages, ""


def shell_exec(command: str, cwd: str = "/tmp", timeout: int = 30, **_) -> dict:
    """Run an allowlisted command (optionally a ``|`` pipeline) without a shell.

    Args:
        command: command string; only allowlisted executables, piped with ``|``.
        cwd:     working directory (defaults to /tmp; non-absolute → /tmp).
        timeout: max seconds (default 30, capped at 120).

    Returns:
        {"stdout": str, "stderr": str, "returncode": int, "ok": bool}
    """
    stages, reason = _parse_pipeline(command or "")
    if stages is None:
        logger.warning("shell_exec blocked (%s): %s", reason, (command or "")[:80])
        return {"stdout": "", "stderr": f"Command blocked: {reason}",
                "returncode": -1, "ok": False}

    timeout = max(1, min(int(timeout), 120))
    env = {k: v for k, v in os.environ.items() if k in _ALLOWED_ENVS}
    env["HOME"] = os.environ.get("HOME", "/tmp")
    if not os.path.isabs(cwd):
        cwd = "/tmp"
    if not os.path.isdir(cwd):
        os.makedirs(cwd, exist_ok=True)

    procs: list = []
    try:
        prev = None
        for i, argv in enumerate(stages):
            is_last = i == len(stages) - 1
            p = subprocess.Popen(
                argv, cwd=cwd, env=env,
                stdin=prev,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE if is_last else subprocess.DEVNULL,
                text=True,
            )
            if prev is not None:
                prev.close()  # let upstream get SIGPIPE if downstream exits
            prev = p.stdout
            procs.append(p)
        last = procs[-1]
        out, err = last.communicate(timeout=timeout)
        for p in procs[:-1]:
            try:
                p.wait(timeout=1)
            except Exception:  # noqa: BLE001
                p.kill()
        return {
            "stdout": (out or "")[:8000],
            "stderr": (err or "")[:2000],
            "returncode": last.returncode,
            "ok": last.returncode == 0,
        }
    except subprocess.TimeoutExpired:
        for p in procs:
            try:
                p.kill()
            except Exception:  # noqa: BLE001
                pass
        return {"stdout": "", "stderr": f"Timed out after {timeout}s",
                "returncode": -1, "ok": False}
    except FileNotFoundError as exc:
        return {"stdout": "", "stderr": f"command not found: {exc}",
                "returncode": -1, "ok": False}
    except Exception as exc:  # noqa: BLE001
        logger.error("shell_exec error: %s", exc)
        return {"stdout": "", "stderr": str(exc), "returncode": -1, "ok": False}
    finally:
        # Never leak processes/fds on any error path (mid-pipeline Popen failure,
        # ValueError, OSError, etc.) — kill anything still running.
        for p in procs:
            try:
                if p.poll() is None:
                    p.kill()
            except Exception:  # noqa: BLE001
                pass
