"""Run pytest against a NAMED target. Honest, bounded, never raises.

With no target it returns ``status='target_required'`` instead of running the
whole suite unprompted (mirrors the execution broker's forge.run_tests
contract). Timeout + capped output; containment check keeps targets in-repo.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_TIMEOUT_S = int(os.environ.get("FORGE_TEST_TIMEOUT_S", "120"))
_TAIL_CHARS = int(os.environ.get("FORGE_TEST_OUTPUT_TAIL", "4000"))


def run_tests(target: str | None = None) -> dict:
    """-> {status: 'passed'|'failed'|'target_required'|'error', summary, output_tail}"""
    target = str(target or "").strip()
    if not target:
        return {"status": "target_required",
                "summary": "name a test target (e.g. tests/test_x.py) — "
                           "the lifecycle will not run the full suite unprompted",
                "output_tail": ""}

    # Containment + existence guard: only run targets inside the repo.
    node_id, _, _ = target.partition("::")
    candidate = (_REPO_ROOT / node_id).resolve()
    try:
        candidate.relative_to(_REPO_ROOT)
    except ValueError:
        return {"status": "error", "summary": f"target escapes repo root: {target}", "output_tail": ""}
    if not candidate.exists():
        return {"status": "error", "summary": f"target not found: {target}", "output_tail": ""}

    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        p for p in (str(_REPO_ROOT), str(_REPO_ROOT / "runtime"), env.get("PYTHONPATH", "")) if p)
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", target, "-q"],
            cwd=str(_REPO_ROOT), env=env, capture_output=True, text=True, timeout=_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        return {"status": "failed", "summary": f"timeout after {_TIMEOUT_S}s", "output_tail": ""}
    except Exception as exc:  # missing pytest, broken interpreter, ...
        return {"status": "error", "summary": f"could not run pytest: {exc}", "output_tail": ""}

    output = (proc.stdout or "") + (proc.stderr or "")
    lines = [ln for ln in output.strip().splitlines() if ln.strip()]
    return {
        "status": "passed" if proc.returncode == 0 else "failed",
        "summary": lines[-1] if lines else f"exit code {proc.returncode}",
        "output_tail": output[-_TAIL_CHARS:],
    }
