from __future__ import annotations

import re
import subprocess
import os
from pathlib import Path
from typing import Any


_UNSAFE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?:password|secret|token|api_key)\s*=\s*['\"][^'\"]+['\"]", re.IGNORECASE),
    re.compile(r"eval\s*\("),
    re.compile(r"exec\s*\("),
    re.compile(r"os\.system\s*\("),
)


class PatchValidator:
    """Validation gate for generated patches."""

    def __init__(self, repo_root: Path | None = None) -> None:
        self._repo_root = repo_root or self._detect_repo_root()

    @staticmethod
    def _detect_repo_root() -> Path:
        current = Path(__file__).resolve()
        for parent in current.parents:
            if (parent / "package.json").exists():
                return parent
        return current.parents[3]

    def validate(self, diff_text: str) -> dict[str, Any]:
        lint_cmd = os.environ.get("EVOLUTION_LINT_CMD", "npm run lint")
        type_cmd = os.environ.get("EVOLUTION_TYPECHECK_CMD", "python3 -m compileall runtime")
        test_cmd = os.environ.get("EVOLUTION_TEST_CMD", "python3 -m pytest tests/ -q -x")
        lint = self._run(lint_cmd.split(), timeout=120)
        type_checks = self._run(type_cmd.split(), timeout=120)
        tests = self._run(test_cmd.split(), timeout=240)
        security = self._security_scan(diff_text)
        passed = lint["ok"] and type_checks["ok"] and tests["ok"] and security["ok"]
        return {
            "passed": passed,
            "lint": lint,
            "type_checks": type_checks,
            "pytest": tests,
            "security_scan": security,
        }

    def _run(self, cmd: list[str], timeout: int) -> dict[str, Any]:
        try:
            proc = subprocess.run(
                cmd,
                cwd=str(self._repo_root),
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return {
                "ok": proc.returncode == 0,
                "returncode": proc.returncode,
                "stdout": (proc.stdout or "")[-1200:],
                "stderr": (proc.stderr or "")[-1200:],
            }
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def _security_scan(self, diff_text: str) -> dict[str, Any]:
        issues: list[dict[str, Any]] = []
        if not diff_text:
            return {"ok": True, "issues": []}
        for idx, line in enumerate(diff_text.splitlines(), start=1):
            if not line.startswith("+") or line.startswith("+++"):
                continue
            for pattern in _UNSAFE_PATTERNS:
                if pattern.search(line):
                    issues.append({
                        "line": idx,
                        "pattern": pattern.pattern,
                        "content": line[1:140],
                    })
        return {"ok": not issues, "issues": issues}
