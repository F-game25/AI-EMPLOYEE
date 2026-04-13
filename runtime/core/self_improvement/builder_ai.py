"""Builder AI — generates unified diffs in a sandbox environment.

The Builder AI works exclusively on a sandboxed copy and produces
only unified diff patches — never full file rewrites.  Output is
a ``PatchArtifact`` ready for policy validation and testing.
"""
from __future__ import annotations

import difflib
import time
from pathlib import Path
from typing import Any

from core.self_improvement.contracts import (
    ImprovementPlan,
    ImprovementTask,
    PatchArtifact,
)


class BuilderAI:
    """Generates diff-only patches inside a sandbox."""

    def __init__(self, sandbox_root: Path | None = None) -> None:
        self._sandbox_root = sandbox_root

    def build_patch(
        self,
        task: ImprovementTask,
        plan: ImprovementPlan,
        *,
        sandbox_root: Path | None = None,
    ) -> PatchArtifact:
        """Generate a unified diff patch for the given plan.

        In a production system, this would invoke an LLM or code-generation
        agent.  The current implementation provides the contract and
        infrastructure for future AI integration.

        Parameters
        ----------
        task:
            The improvement task being executed.
        plan:
            The immutable plan produced by the Planner AI.
        sandbox_root:
            Path to the sandboxed repo copy. Falls back to constructor arg.

        Returns
        -------
        PatchArtifact with unified diff and metadata.
        """
        root = sandbox_root or self._sandbox_root
        start = time.perf_counter()

        # Generate the patch (extensible hook for AI code generation)
        diff, files_changed, lines_added, lines_removed = self._generate_diff(
            plan=plan,
            sandbox_root=root,
        )

        parent_commit = self._get_parent_commit(root)
        duration_ms = (time.perf_counter() - start) * 1000

        return PatchArtifact(
            task_id=task.task_id,
            plan_id=plan.plan_id,
            diff=diff,
            files_changed=files_changed,
            lines_added=lines_added,
            lines_removed=lines_removed,
            parent_commit=parent_commit,
            risk_level=plan.risk_level,
            metadata={
                "build_duration_ms": round(duration_ms, 1),
                "plan_hash": plan.plan_hash,
                "target_area": task.target_area,
            },
        )

    def build_patch_from_changes(
        self,
        task: ImprovementTask,
        plan: ImprovementPlan,
        changes: dict[str, tuple[str, str]],
    ) -> PatchArtifact:
        """Build a patch from explicit before/after content pairs.

        Parameters
        ----------
        changes:
            Mapping of ``{filepath: (original_content, new_content)}``.

        This is the primary entry point for AI agents that produce
        concrete code changes.
        """
        all_diff_lines: list[str] = []
        files_changed: list[str] = []
        lines_added = 0
        lines_removed = 0

        for filepath, (original, improved) in sorted(changes.items()):
            diff_lines = list(difflib.unified_diff(
                original.splitlines(keepends=True),
                improved.splitlines(keepends=True),
                fromfile=f"a/{filepath}",
                tofile=f"b/{filepath}",
            ))
            if diff_lines:
                all_diff_lines.extend(diff_lines)
                files_changed.append(filepath)
                lines_added += sum(
                    1 for l in diff_lines
                    if l.startswith("+") and not l.startswith("+++")
                )
                lines_removed += sum(
                    1 for l in diff_lines
                    if l.startswith("-") and not l.startswith("---")
                )

        diff = "".join(all_diff_lines)

        return PatchArtifact(
            task_id=task.task_id,
            plan_id=plan.plan_id,
            diff=diff,
            files_changed=files_changed,
            lines_added=lines_added,
            lines_removed=lines_removed,
            risk_level=plan.risk_level,
            metadata={
                "plan_hash": plan.plan_hash,
                "target_area": task.target_area,
                "source": "explicit_changes",
            },
        )

    def _generate_diff(
        self,
        *,
        plan: ImprovementPlan,
        sandbox_root: Path | None,
    ) -> tuple[str, list[str], int, int]:
        """Internal diff generation hook.

        Returns (diff_text, files_changed, lines_added, lines_removed).
        In a full implementation this invokes an AI code generator.
        Currently returns an empty diff (plan-only mode).
        """
        return ("", [], 0, 0)

    @staticmethod
    def _get_parent_commit(sandbox_root: Path | None) -> str:
        """Read the current HEAD commit from the sandbox."""
        if sandbox_root is None:
            return ""
        head_file = sandbox_root / ".git" / "HEAD"
        try:
            ref = head_file.read_text().strip()
            if ref.startswith("ref: "):
                ref_path = sandbox_root / ".git" / ref[5:]
                return ref_path.read_text().strip()[:12]
            return ref[:12]
        except Exception:
            return ""
