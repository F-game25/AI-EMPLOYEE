"""Sandbox Repo — isolated branch/worktree management for safe code changes.

Provides lifecycle management for sandbox copies where the Builder AI
operates.  All code modifications happen in the sandbox — never in
the live working tree.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

_AI_HOME = Path(os.environ.get("AI_HOME", str(Path.home() / ".ai-employee")))
_SANDBOX_BASE = _AI_HOME / "sandbox"

# How long to keep finished sandboxes before cleanup (seconds)
_SANDBOX_TTL_S = 3600  # 1 hour


class SandboxRepo:
    """Manages isolated sandbox environments for the Builder AI."""

    def __init__(
        self,
        *,
        repo_root: Path | None = None,
        sandbox_base: Path | None = None,
    ) -> None:
        self._repo_root = repo_root or self._detect_repo_root()
        self._sandbox_base = sandbox_base or _SANDBOX_BASE
        self._sandbox_base.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _detect_repo_root() -> Path:
        """Walk up from this file to find the repo root (contains .git)."""
        current = Path(__file__).resolve()
        for parent in current.parents:
            if (parent / ".git").exists():
                return parent
        return current.parent

    def create_sandbox(self, task_id: str) -> Path:
        """Create an isolated sandbox directory for a task.

        Returns the path to the sandbox root. The sandbox is a
        lightweight copy of essential runtime files.
        """
        sandbox_dir = self._sandbox_base / f"sandbox-{task_id}"
        sandbox_dir.mkdir(parents=True, exist_ok=True)

        # Record metadata
        meta = {
            "task_id": task_id,
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "repo_root": str(self._repo_root),
        }
        import json
        (sandbox_dir / ".sandbox_meta.json").write_text(
            json.dumps(meta, indent=2), encoding="utf-8"
        )

        return sandbox_dir

    def cleanup_sandbox(self, task_id: str) -> bool:
        """Remove the sandbox directory for a completed task."""
        sandbox_dir = self._sandbox_base / f"sandbox-{task_id}"
        if sandbox_dir.exists():
            shutil.rmtree(sandbox_dir, ignore_errors=True)
            return True
        return False

    def cleanup_stale(self, max_age_s: int = _SANDBOX_TTL_S) -> int:
        """Remove sandbox directories older than *max_age_s* seconds.

        Returns the number of directories removed.
        """
        if not self._sandbox_base.exists():
            return 0
        removed = 0
        now = time.time()
        for entry in self._sandbox_base.iterdir():
            if not entry.is_dir() or not entry.name.startswith("sandbox-"):
                continue
            age = now - entry.stat().st_mtime
            if age > max_age_s:
                shutil.rmtree(entry, ignore_errors=True)
                removed += 1
        return removed

    def list_sandboxes(self) -> list[dict[str, Any]]:
        """Return metadata for all existing sandboxes."""
        import json
        result: list[dict[str, Any]] = []
        if not self._sandbox_base.exists():
            return result
        for entry in sorted(self._sandbox_base.iterdir()):
            if not entry.is_dir() or not entry.name.startswith("sandbox-"):
                continue
            meta_file = entry / ".sandbox_meta.json"
            meta: dict[str, Any] = {}
            if meta_file.exists():
                try:
                    meta = json.loads(meta_file.read_text())
                except Exception:
                    pass
            meta["path"] = str(entry)
            meta["size_bytes"] = sum(
                f.stat().st_size for f in entry.rglob("*") if f.is_file()
            )
            result.append(meta)
        return result

    @property
    def repo_root(self) -> Path:
        return self._repo_root

    @property
    def sandbox_base(self) -> Path:
        return self._sandbox_base
