"""Tester Gate — build/test/security gate orchestration.

Every patch must pass ALL gates before it can be approved.
One failure = automatic reject.  No exceptions.

Gates:
  1. Lint check   — ``npm run lint`` (py_compile all agents)
  2. Test suite   — ``npm test`` (pytest + agent selftest)
  3. Security     — basic static checks (no secrets in diff, no unsafe patterns)
"""
from __future__ import annotations

import re
import subprocess
import time
from pathlib import Path
from typing import Any

from core.self_improvement.contracts import PatchArtifact, TestResult

# Patterns that should never appear in a diff
_UNSAFE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?:password|secret|token|api_key)\s*=\s*['\"][^'\"]+['\"]", re.IGNORECASE),
    re.compile(r"eval\s*\("),
    re.compile(r"exec\s*\("),
    re.compile(r"__import__\s*\("),
    re.compile(r"subprocess\.(?:call|run|Popen)\s*\(\s*['\"]"),
    re.compile(r"os\.system\s*\("),
)


class TesterGate:
    """Hard gate: every patch must pass lint, tests, and security checks."""

    def __init__(self, repo_root: Path | None = None) -> None:
        self._repo_root = repo_root or self._detect_repo_root()

    @staticmethod
    def _detect_repo_root() -> Path:
        current = Path(__file__).resolve()
        for parent in current.parents:
            if (parent / "package.json").exists():
                return parent
        return current.parent

    def run_all_gates(self, patch: PatchArtifact) -> TestResult:
        """Run all gates and return an aggregated TestResult.

        ALL gates must pass for ``TestResult.passed`` to be True.
        """
        start = time.perf_counter()

        lint_ok, lint_details = self._gate_lint()
        tests_ok, test_details = self._gate_tests()
        security_ok, security_details = self._gate_security(patch)

        duration_ms = (time.perf_counter() - start) * 1000
        all_ok = lint_ok and tests_ok and security_ok

        return TestResult(
            passed=all_ok,
            lint_ok=lint_ok,
            tests_ok=tests_ok,
            security_ok=security_ok,
            details={
                "lint": lint_details,
                "tests": test_details,
                "security": security_details,
            },
            duration_ms=round(duration_ms, 1),
        )

    def run_lint_only(self) -> tuple[bool, dict[str, Any]]:
        """Run only the lint gate (fast check)."""
        return self._gate_lint()

    def run_tests_only(self) -> tuple[bool, dict[str, Any]]:
        """Run only the test suite gate."""
        return self._gate_tests()

    def run_security_only(self, patch: PatchArtifact) -> tuple[bool, dict[str, Any]]:
        """Run only the security gate."""
        return self._gate_security(patch)

    # ── Gate implementations ──────────────────────────────────────────────────

    def _gate_lint(self) -> tuple[bool, dict[str, Any]]:
        """Gate 1: npm run lint."""
        try:
            result = subprocess.run(
                ["npm", "run", "lint"],
                capture_output=True,
                text=True,
                cwd=str(self._repo_root),
                timeout=60,
            )
            return (
                result.returncode == 0,
                {
                    "returncode": result.returncode,
                    "stdout": result.stdout[-500:] if result.stdout else "",
                    "stderr": result.stderr[-500:] if result.stderr else "",
                },
            )
        except Exception as exc:
            return False, {"error": str(exc)}

    def _gate_tests(self) -> tuple[bool, dict[str, Any]]:
        """Gate 2: npm test (pytest + agent selftest)."""
        try:
            result = subprocess.run(
                ["python3", "-m", "pytest", "tests/", "-x", "--no-header", "-q"],
                capture_output=True,
                text=True,
                cwd=str(self._repo_root),
                timeout=120,
            )
            return (
                result.returncode == 0,
                {
                    "returncode": result.returncode,
                    "stdout": result.stdout[-1000:] if result.stdout else "",
                    "stderr": result.stderr[-500:] if result.stderr else "",
                },
            )
        except Exception as exc:
            return False, {"error": str(exc)}

    def _gate_security(
        self, patch: PatchArtifact
    ) -> tuple[bool, dict[str, Any]]:
        """Gate 3: Static security checks on the diff content."""
        issues: list[dict[str, str]] = []

        if not patch.diff:
            # Empty diff = nothing to check
            return True, {"issues": [], "note": "empty_diff"}

        # Check each added line for unsafe patterns
        for line_num, line in enumerate(patch.diff.splitlines(), 1):
            if not line.startswith("+") or line.startswith("+++"):
                continue
            for pattern in _UNSAFE_PATTERNS:
                if pattern.search(line):
                    issues.append({
                        "line": line_num,
                        "pattern": pattern.pattern[:50],
                        "content": line[1:80],
                    })

        return (
            len(issues) == 0,
            {"issues": issues, "checked_patterns": len(_UNSAFE_PATTERNS)},
        )
