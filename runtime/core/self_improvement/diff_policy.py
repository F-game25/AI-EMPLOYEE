"""Diff Policy — hard governance rules for self-improvement patches.

Enforces:
  - No full-file rewrites (change ratio cap).
  - Patch size limits per risk level.
  - Protected paths that can never be auto-modified.
  - Only whitelisted directories for self-improvement.
  - No binary file changes.
  - No config/secret file changes without override.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Any

from core.self_improvement.contracts import PatchArtifact, RiskLevel

# ── Protected paths — never auto-apply ────────────────────────────────────────
PROTECTED_PATHS: frozenset[str] = frozenset({
    "runtime/brain/brain.py",
    "runtime/brain/intelligence.py",
    "runtime/brain/model.py",
    "runtime/agents/ollama-agent",
    "runtime/agents/hermes-agent",
    "runtime/agents/ai-router",
    "runtime/config/",
    "runtime/state/",
    ".env",
    ".github/",
    "install.sh",
    "start.sh",
})

# ── Whitelisted directories for self-improvement ──────────────────────────────
WHITELISTED_DIRS: tuple[str, ...] = (
    "runtime/core/",
    "runtime/actions/",
    "runtime/skills/",
    "runtime/memory/",
    "runtime/analytics/",
    "runtime/security/",
    "runtime/agents/",
    "frontend/src/",
    "backend/",
    "tests/",
)

# ── Size limits per risk level ────────────────────────────────────────────────
_MAX_LINES: dict[str, int] = {
    "low": 200,
    "medium": 100,
    "high": 50,
    "critical": 0,  # critical = no auto changes ever
}

_MAX_FILES: dict[str, int] = {
    "low": 10,
    "medium": 5,
    "high": 2,
    "critical": 0,
}

# Maximum fraction of a file that may be changed (prevents full rewrites)
_MAX_CHANGE_RATIO = 0.6

# Binary extensions that are never allowed
_BINARY_EXTENSIONS: frozenset[str] = frozenset({
    ".pth", ".bin", ".pkl", ".so", ".dylib", ".exe",
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".woff", ".woff2",
    ".zip", ".tar", ".gz", ".db", ".sqlite",
})

# Secret/config patterns
_SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\.env$"),
    re.compile(r"secrets?\."),
    re.compile(r"credentials?\."),
    re.compile(r"\.pem$"),
    re.compile(r"\.key$"),
)


@dataclass
class PolicyViolation:
    """A single policy violation found during diff validation."""

    rule: str
    message: str
    file: str = ""
    severity: str = "error"

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule": self.rule,
            "message": self.message,
            "file": self.file,
            "severity": self.severity,
        }


@dataclass
class DiffPolicyResult:
    """Result of diff policy validation."""

    allowed: bool = True
    violations: list[PolicyViolation] = field(default_factory=list)
    risk_level: RiskLevel = "low"

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "violations": [v.to_dict() for v in self.violations],
            "risk_level": self.risk_level,
        }


class DiffPolicy:
    """Enforces governance rules on patch artifacts."""

    def __init__(
        self,
        *,
        protected_paths: frozenset[str] | None = None,
        whitelisted_dirs: tuple[str, ...] | None = None,
        max_change_ratio: float = _MAX_CHANGE_RATIO,
    ) -> None:
        self._protected = protected_paths or PROTECTED_PATHS
        self._whitelisted = whitelisted_dirs or WHITELISTED_DIRS
        self._max_change_ratio = max_change_ratio

    def validate(self, patch: PatchArtifact) -> DiffPolicyResult:
        """Validate a patch against all governance rules.

        Returns a ``DiffPolicyResult`` with ``allowed=True`` only if
        zero violations are found.
        """
        violations: list[PolicyViolation] = []
        risk = patch.risk_level

        # ── Rule 1: No binary files ──────────────────────────────────────
        for f in patch.files_changed:
            ext = PurePosixPath(f).suffix.lower()
            if ext in _BINARY_EXTENSIONS:
                violations.append(PolicyViolation(
                    rule="no_binary_files",
                    message=f"Binary file changes are not allowed: {f}",
                    file=f,
                ))

        # ── Rule 2: Protected paths ──────────────────────────────────────
        for f in patch.files_changed:
            for protected in self._protected:
                if f.startswith(protected) or f == protected:
                    violations.append(PolicyViolation(
                        rule="protected_path",
                        message=f"Protected path cannot be auto-modified: {f}",
                        file=f,
                    ))

        # ── Rule 3: Whitelisted directories only ─────────────────────────
        for f in patch.files_changed:
            if not any(f.startswith(w) for w in self._whitelisted):
                violations.append(PolicyViolation(
                    rule="outside_whitelist",
                    message=f"File is outside whitelisted directories: {f}",
                    file=f,
                ))

        # ── Rule 4: Secret/config files ──────────────────────────────────
        for f in patch.files_changed:
            for pattern in _SECRET_PATTERNS:
                if pattern.search(f):
                    violations.append(PolicyViolation(
                        rule="secret_config_change",
                        message=f"Secret/config file changes require override: {f}",
                        file=f,
                    ))

        # ── Rule 5: Patch size limits ────────────────────────────────────
        max_lines = _MAX_LINES.get(risk, 0)
        total_changed = patch.lines_added + patch.lines_removed
        if total_changed > max_lines:
            violations.append(PolicyViolation(
                rule="patch_too_large",
                message=(
                    f"Patch changes {total_changed} lines, "
                    f"max for {risk} risk is {max_lines}"
                ),
            ))

        max_files = _MAX_FILES.get(risk, 0)
        if len(patch.files_changed) > max_files:
            violations.append(PolicyViolation(
                rule="too_many_files",
                message=(
                    f"Patch touches {len(patch.files_changed)} files, "
                    f"max for {risk} risk is {max_files}"
                ),
            ))

        # ── Rule 6: No full-file rewrites (requires diff content) ────────
        if patch.diff:
            self._check_rewrite_ratio(patch.diff, violations)

        # ── Rule 7: Critical risk = never auto ───────────────────────────
        if risk == "critical":
            violations.append(PolicyViolation(
                rule="critical_risk",
                message="Critical-risk patches cannot be auto-applied",
            ))

        return DiffPolicyResult(
            allowed=len(violations) == 0,
            violations=violations,
            risk_level=risk,
        )

    def _check_rewrite_ratio(
        self,
        diff_text: str,
        violations: list[PolicyViolation],
    ) -> None:
        """Check if any single file has > max_change_ratio lines replaced."""
        # Parse per-file stats from unified diff
        current_file = ""
        added = 0
        removed = 0
        total_original = 0
        for line in diff_text.splitlines():
            if line.startswith("--- a/"):
                # Flush previous file
                if current_file and total_original > 0:
                    ratio = (added + removed) / max(total_original, 1)
                    if ratio > self._max_change_ratio:
                        violations.append(PolicyViolation(
                            rule="full_rewrite",
                            message=(
                                f"File {current_file} has {ratio:.0%} change ratio "
                                f"(max {self._max_change_ratio:.0%}). "
                                "Use targeted diffs, not full rewrites."
                            ),
                            file=current_file,
                        ))
                current_file = line[6:]
                added = 0
                removed = 0
                total_original = 0
            elif line.startswith("@@ "):
                # Parse hunk header for original line count
                m = re.search(r"-\d+(?:,(\d+))?", line)
                if m:
                    total_original += int(m.group(1) or 1)
            elif line.startswith("+") and not line.startswith("+++"):
                added += 1
            elif line.startswith("-") and not line.startswith("---"):
                removed += 1

        # Flush last file
        if current_file and total_original > 0:
            ratio = (added + removed) / max(total_original, 1)
            if ratio > self._max_change_ratio:
                violations.append(PolicyViolation(
                    rule="full_rewrite",
                    message=(
                        f"File {current_file} has {ratio:.0%} change ratio "
                        f"(max {self._max_change_ratio:.0%}). "
                        "Use targeted diffs, not full rewrites."
                    ),
                    file=current_file,
                ))
