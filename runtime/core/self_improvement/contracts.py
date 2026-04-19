"""Data contracts and state machine for the self-improvement loop.

Every improvement task progresses through a strict state machine::

    queued → analyzing → planned → building → testing
           → awaiting_approval → approved | rejected
           → deploying → deployed | rolled_back

Transitions are enforced; illegal jumps raise ``ValueError``.
"""
from __future__ import annotations

import hashlib
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Literal

# ── State machine ─────────────────────────────────────────────────────────────

ImprovementStatus = Literal[
    "queued",
    "analyzing",
    "planned",
    "building",
    "testing",
    "awaiting_approval",
    "approved",
    "rejected",
    "deploying",
    "deployed",
    "rolled_back",
    "failed",
]

_ALLOWED_TRANSITIONS: dict[str, tuple[str, ...]] = {
    "queued":             ("analyzing", "failed"),
    "analyzing":          ("planned", "failed"),
    "planned":            ("building", "failed"),
    "building":           ("testing", "failed"),
    "testing":            ("awaiting_approval", "failed"),
    "awaiting_approval":  ("approved", "rejected"),
    "approved":           ("deploying", "failed"),
    "deploying":          ("deployed", "rolled_back", "failed"),
    # Terminal states — no further transitions allowed.
    "deployed":           (),
    "rolled_back":        (),
    "rejected":           (),
    "failed":             (),
}

TERMINAL_STATES: frozenset[str] = frozenset(
    s for s, targets in _ALLOWED_TRANSITIONS.items() if not targets
)

# Risk classifications
RiskLevel = Literal["low", "medium", "high", "critical"]


def validate_transition(current: str, target: str) -> None:
    """Raise ``ValueError`` if *current* → *target* is not allowed."""
    allowed = _ALLOWED_TRANSITIONS.get(current, ())
    if target not in allowed:
        raise ValueError(
            f"Illegal state transition: {current!r} → {target!r}. "
            f"Allowed from {current!r}: {allowed}"
        )


# ── Data models ───────────────────────────────────────────────────────────────

@dataclass
class ImprovementPlan:
    """Immutable plan artifact produced by the Planner AI."""

    plan_id: str = ""
    task_id: str = ""
    what: str = ""
    where: list[str] = field(default_factory=list)
    why: str = ""
    acceptance_criteria: list[str] = field(default_factory=list)
    risk_level: RiskLevel = "medium"
    estimated_lines: int = 0
    created_at: str = ""
    plan_hash: str = ""

    def __post_init__(self) -> None:
        if not self.plan_id:
            self.plan_id = str(uuid.uuid4())[:8]
        if not self.created_at:
            self.created_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        if not self.plan_hash:
            self.plan_hash = self._compute_hash()

    def _compute_hash(self) -> str:
        content = f"{self.what}|{'|'.join(self.where)}|{self.why}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "task_id": self.task_id,
            "what": self.what,
            "where": self.where,
            "why": self.why,
            "acceptance_criteria": self.acceptance_criteria,
            "risk_level": self.risk_level,
            "estimated_lines": self.estimated_lines,
            "created_at": self.created_at,
            "plan_hash": self.plan_hash,
        }


@dataclass
class PatchArtifact:
    """Unified diff output from the Builder AI."""

    patch_id: str = ""
    task_id: str = ""
    plan_id: str = ""
    diff: str = ""
    files_changed: list[str] = field(default_factory=list)
    lines_added: int = 0
    lines_removed: int = 0
    parent_commit: str = ""
    risk_level: RiskLevel = "medium"
    created_at: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.patch_id:
            self.patch_id = str(uuid.uuid4())[:8]
        if not self.created_at:
            self.created_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    def to_dict(self) -> dict[str, Any]:
        return {
            "patch_id": self.patch_id,
            "task_id": self.task_id,
            "plan_id": self.plan_id,
            "files_changed": self.files_changed,
            "lines_added": self.lines_added,
            "lines_removed": self.lines_removed,
            "parent_commit": self.parent_commit,
            "risk_level": self.risk_level,
            "created_at": self.created_at,
            "metadata": self.metadata,
        }


@dataclass
class TestResult:
    """Aggregated test gate results."""

    passed: bool = False
    lint_ok: bool = False
    tests_ok: bool = False
    security_ok: bool = False
    details: dict[str, Any] = field(default_factory=dict)
    duration_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "lint_ok": self.lint_ok,
            "tests_ok": self.tests_ok,
            "security_ok": self.security_ok,
            "details": self.details,
            "duration_ms": self.duration_ms,
        }


@dataclass
class ImprovementTask:
    """Top-level improvement task flowing through the full pipeline."""

    task_id: str = ""
    description: str = ""
    target_area: str = ""
    constraints: list[str] = field(default_factory=list)
    risk_class: RiskLevel = "medium"
    owner: str = "system"
    status: ImprovementStatus = "queued"
    plan: ImprovementPlan | None = None
    patch: PatchArtifact | None = None
    test_result: TestResult | None = None
    approval_policy: str = "manual"
    retry_count: int = 0
    max_retries: int = 2
    error: str = ""
    created_at: str = ""
    updated_at: str = ""
    completed_at: str = ""
    # Neural network + memory trace fields
    brain_strategy: dict[str, Any] = field(default_factory=dict)
    learning_outcome: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.task_id:
            self.task_id = f"imp-{uuid.uuid4().hex[:8]}"
        if not self.created_at:
            self.created_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        if not self.updated_at:
            self.updated_at = self.created_at

    def transition(self, target: ImprovementStatus) -> None:
        """Move to *target* state, enforcing the state machine."""
        validate_transition(self.status, target)
        self.status = target
        self.updated_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        if target in TERMINAL_STATES:
            self.completed_at = self.updated_at

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL_STATES

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "description": self.description,
            "target_area": self.target_area,
            "constraints": self.constraints,
            "risk_class": self.risk_class,
            "owner": self.owner,
            "status": self.status,
            "plan": self.plan.to_dict() if self.plan else None,
            "patch": self.patch.to_dict() if self.patch else None,
            "test_result": self.test_result.to_dict() if self.test_result else None,
            "approval_policy": self.approval_policy,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "error": self.error,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "completed_at": self.completed_at,
            "brain_strategy": self.brain_strategy,
            "learning_outcome": self.learning_outcome,
        }
