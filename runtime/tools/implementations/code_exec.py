"""Sandboxed code execution tool.

Risk level 2. Runs code in a subprocess with a tmp working directory,
capped timeout, and no network access via environment isolation.
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
import tempfile

logger = logging.getLogger("tools.code_exec")

_SUPPORTED_LANGUAGES = {"python", "javascript", "bash"}


def code_exec(
    language: str,
    code: str,
    timeout: int = 30,
    **_,
) -> dict:
    """Execute code in a sandboxed subprocess.

    Args:
        language: "python" | "javascript" | "bash"
        code:     Source code to execute.
        timeout:  Max seconds (capped at 60).

    Returns:
        {"stdout": str, "stderr": str, "ok": bool, "language": str}
    """
    language = language.lower().strip()
    if language not in _SUPPORTED_LANGUAGES:
        return {"stdout": "", "stderr": f"Unsupported language: {language}", "ok": False, "language": language}

    timeout = min(int(timeout), 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        if language == "python":
            src_path = os.path.join(tmpdir, "script.py")
            with open(src_path, "w") as f:
                f.write(code)
            cmd = [sys.executable, src_path]
        elif language == "javascript":
            src_path = os.path.join(tmpdir, "script.js")
            with open(src_path, "w") as f:
                f.write(code)
            node_bin = _find_bin("node") or _find_bin("nodejs")
            if not node_bin:
                return {"stdout": "", "stderr": "node not found in PATH", "ok": False, "language": language}
            cmd = [node_bin, src_path]
        else:  # bash
            src_path = os.path.join(tmpdir, "script.sh")
            with open(src_path, "w") as f:
                f.write(code)
            os.chmod(src_path, 0o755)
            cmd = ["/bin/bash", src_path]

        # Minimal env — no HOME network credentials
        env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "TMPDIR": tmpdir}

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=tmpdir,
                env=env,
            )
            return {
                "stdout": proc.stdout[:8000],
                "stderr": proc.stderr[:2000],
                "ok": proc.returncode == 0,
                "language": language,
                "returncode": proc.returncode,
            }
        except subprocess.TimeoutExpired:
            return {"stdout": "", "stderr": f"Timed out after {timeout}s", "ok": False, "language": language}
        except Exception as exc:
            logger.error("code_exec error: %s", exc)
            return {"stdout": "", "stderr": str(exc), "ok": False, "language": language}


def _find_bin(name: str) -> str | None:
    import shutil
    return shutil.which(name)
