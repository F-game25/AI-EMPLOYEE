from __future__ import annotations

import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from core.self_improvement.contracts import PatchArtifact
from core.self_improvement.diff_policy import DiffPolicy

_SMOKE_TEST_TIMEOUT_S = 60   # max seconds for post-deploy smoke test


class SafeDeployer:
    """Policy-aware deployer with backup, rollback, and post-deploy verification."""

    def __init__(self, repo_root: Path | None = None) -> None:
        self._repo_root = repo_root or self._detect_repo_root()
        self._backup_root = self._repo_root / "state" / "evolution_backups"
        self._backup_root.mkdir(parents=True, exist_ok=True)
        self._policy = DiffPolicy()

    @staticmethod
    def _detect_repo_root() -> Path:
        current = Path(__file__).resolve()
        for parent in current.parents:
            if (parent / "package.json").exists():
                return parent
        return current.parents[3]

    def deploy(
        self,
        *,
        diff_text: str,
        risk_level: str,
        evolution_mode: str,
        tester_gate_passed: bool,
        manual_approved: bool = False,
    ) -> dict[str, Any]:
        if not diff_text:
            return {"deployed": False, "reason": "empty_diff"}
        mode = (evolution_mode or "OFF").upper()
        if mode == "OFF":
            return {"deployed": False, "reason": "evolution_mode_off"}
        if mode == "SAFE" and not manual_approved:
            return {"deployed": False, "reason": "manual_approval_required"}
        if not tester_gate_passed:
            return {"deployed": False, "reason": "tester_gate_failed"}

        files = self._extract_files(diff_text)
        patch = PatchArtifact(
            diff=diff_text,
            files_changed=files,
            lines_added=sum(1 for line in diff_text.splitlines() if line.startswith("+") and not line.startswith("+++")),
            lines_removed=sum(1 for line in diff_text.splitlines() if line.startswith("-") and not line.startswith("---")),
            risk_level=risk_level if risk_level in {"low", "medium", "high", "critical"} else "medium",
        )
        policy_result = self._policy.validate(patch)
        if not policy_result.allowed:
            return {
                "deployed": False,
                "reason": "diff_policy_failed",
                "violations": [v.to_dict() for v in policy_result.violations],
            }

        backup_id = self._create_backup(files)
        patch_file = self._backup_root / f"{backup_id}.patch"
        patch_file.write_text(diff_text, encoding="utf-8")

        apply_cmd = ["git", "apply", "--whitespace=nowarn", str(patch_file)]
        proc = subprocess.run(apply_cmd, cwd=str(self._repo_root), capture_output=True, text=True)
        if proc.returncode != 0:
            self.rollback(backup_id)
            return {
                "deployed": False,
                "reason": "git_apply_failed",
                "stderr": (proc.stderr or "")[-1000:],
            }

        # Post-deploy smoke test: lint + compileall on the patched files.
        smoke = self._smoke_test(files)
        if not smoke["ok"]:
            self.rollback(backup_id)
            return {
                "deployed": False,
                "reason": "post_deploy_smoke_failed",
                "smoke": smoke,
                "backup_id": backup_id,
            }

        return {
            "deployed": True,
            "backup_id": backup_id,
            "files": files,
            "smoke": smoke,
        }

    def rollback(self, backup_id: str) -> dict[str, Any]:
        backup_dir = self._backup_root / backup_id
        if not backup_dir.exists():
            return {"rolled_back": False, "reason": "backup_not_found"}
        restored = []
        for file in backup_dir.rglob("*"):
            if file.is_dir():
                continue
            rel = file.relative_to(backup_dir)
            dest = self._repo_root / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(file, dest)
            restored.append(str(rel))
        return {"rolled_back": True, "backup_id": backup_id, "files": restored}

    def _create_backup(self, files: list[str]) -> str:
        backup_id = f"bk-{int(time.time() * 1000)}"
        target = self._backup_root / backup_id
        target.mkdir(parents=True, exist_ok=True)
        for rel in files:
            src = self._repo_root / rel
            if not src.exists() or not src.is_file():
                continue
            dest = target / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
        return backup_id

    def _smoke_test(self, files: list[str]) -> dict[str, Any]:
        """Run a quick post-deploy health check on *files*.

        Runs ``python3 -m compileall`` on any patched Python files and
        ``npm run lint`` for the whole project.  Returns ``{"ok": True}`` only
        if all checks pass.
        """
        py_files = [f for f in files if f.endswith(".py")]
        if py_files:
            compile_result = self._run(
                ["python3", "-m", "py_compile"] + [
                    str(self._repo_root / f) for f in py_files
                ],
                timeout=_SMOKE_TEST_TIMEOUT_S,
            )
            if not compile_result["ok"]:
                return {"ok": False, "stage": "py_compile", "detail": compile_result}

        lint_result = self._run(["npm", "run", "lint"], timeout=_SMOKE_TEST_TIMEOUT_S)
        if not lint_result["ok"]:
            return {"ok": False, "stage": "lint", "detail": lint_result}

        return {"ok": True}

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
                "stdout": (proc.stdout or "")[-800:],
                "stderr": (proc.stderr or "")[-800:],
            }
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    @staticmethod
    def _extract_files(diff_text: str) -> list[str]:
        files = re.findall(r"\+\+\+ b/(.+)", diff_text)
        if not files:
            files = re.findall(r"diff --git a/(.+?) b/", diff_text)
        return sorted(set(files))
