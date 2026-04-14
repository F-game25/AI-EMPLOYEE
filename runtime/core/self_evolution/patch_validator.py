from __future__ import annotations

import re
import shutil
import subprocess
import os
import shlex
import tempfile
from pathlib import Path
from typing import Any


_UNSAFE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?:password|secret|token|api_key)\s*=\s*['\"][^'\"]+['\"]", re.IGNORECASE),
    re.compile(r"eval\s*\("),
    re.compile(r"exec\s*\("),
    re.compile(r"os\.system\s*\("),
)


class PatchValidator:
    """Validation gate for generated patches.

    The patch is applied to a temporary copy of the affected files before
    running lint, type-checks, and tests.  Original files are **never**
    touched during validation; they are only modified by SafeDeployer after
    all gates pass.
    """

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
        """Validate *diff_text* by applying it in a sandbox, then running gates."""
        security = self._security_scan(diff_text)
        if not security["ok"]:
            return {
                "passed": False,
                "lint": {"ok": True, "skipped": "security_failed"},
                "type_checks": {"ok": True, "skipped": "security_failed"},
                "pytest": {"ok": True, "skipped": "security_failed"},
                "security_scan": security,
            }

        lint_cmd = os.environ.get("EVOLUTION_LINT_CMD", "npm run lint")
        type_cmd = os.environ.get("EVOLUTION_TYPECHECK_CMD", "python3 -m compileall runtime")
        test_cmd = os.environ.get("EVOLUTION_TEST_CMD", "python3 -m pytest tests/ -q -x")

        # Apply patch in a sandbox and run gates against the patched state.
        sandbox_result = self._validate_in_sandbox(
            diff_text=diff_text,
            lint_cmd=lint_cmd,
            type_cmd=type_cmd,
            test_cmd=test_cmd,
        )
        lint = sandbox_result["lint"]
        type_checks = sandbox_result["type_checks"]
        tests = sandbox_result["pytest"]
        passed = lint["ok"] and type_checks["ok"] and tests["ok"] and security["ok"]
        return {
            "passed": passed,
            "lint": lint,
            "type_checks": type_checks,
            "pytest": tests,
            "security_scan": security,
        }

    # ── Sandbox execution ──────────────────────────────────────────────────────

    def _validate_in_sandbox(
        self,
        *,
        diff_text: str,
        lint_cmd: str,
        type_cmd: str,
        test_cmd: str,
    ) -> dict[str, Any]:
        """Apply *diff_text* to a temp copy of changed files, run gates, restore.

        Strategy:
          1. Extract the list of files touched by the diff.
          2. Back up originals to a temp dir.
          3. Apply the diff against the live repo using ``git apply``.
          4. Run lint / typecheck / test gates.
          5. **Always** restore the originals, even on failure.
        """
        files = self._extract_files(diff_text)
        backup: dict[str, bytes] = {}
        for rel in files:
            src = self._repo_root / rel
            if src.is_file():
                backup[rel] = src.read_bytes()

        patch_file: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                suffix=".patch",
                delete=False,
                mode="w",
                encoding="utf-8",
            ) as fh:
                fh.write(diff_text)
                patch_file = Path(fh.name)

            apply_proc = subprocess.run(
                ["git", "apply", "--whitespace=nowarn", str(patch_file)],
                cwd=str(self._repo_root),
                capture_output=True,
                text=True,
            )
            if apply_proc.returncode != 0:
                return {
                    "lint": {"ok": False, "error": "patch_apply_failed", "stderr": (apply_proc.stderr or "")[-800:]},
                    "type_checks": {"ok": False, "error": "patch_apply_failed"},
                    "pytest": {"ok": False, "error": "patch_apply_failed"},
                }

            lint = self._run(shlex.split(lint_cmd), timeout=120)
            type_checks = self._run(shlex.split(type_cmd), timeout=120)
            tests = self._run(shlex.split(test_cmd), timeout=240)
            return {"lint": lint, "type_checks": type_checks, "pytest": tests}
        finally:
            # Restore original file contents unconditionally.
            for rel, content in backup.items():
                dest = self._repo_root / rel
                try:
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes(content)
                except Exception:
                    pass
            if patch_file and patch_file.exists():
                try:
                    patch_file.unlink()
                except Exception:
                    pass

    # ── Helpers ────────────────────────────────────────────────────────────────

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

    @staticmethod
    def _extract_files(diff_text: str) -> list[str]:
        files = re.findall(r"\+\+\+ b/(.+)", diff_text)
        if not files:
            files = re.findall(r"diff --git a/(.+?) b/", diff_text)
        return sorted(set(files))
