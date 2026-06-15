"""Typed agent contracts for the Business Swarm Layer (Master Plan V3 — Module 7).

A contract formalizes an existing catalog agent: what it can do, which tools it may
touch, what memory it may read, how risky it is, which actions need a human, and
what it must deliver. NO fake autonomy — every consequential action is declared as
`requires_approval_for`, which the executor honors by returning `pending_approval`
instead of executing.

Reference patterns only (openclaw-2 capability profiles / I/O contracts / tool
permissions / success metrics / escalation / memory scope) — rebuilt natively.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

# Risk ladder (mirrors safety_gate / HITL L0-L4 used across the codebase).
RISK_L0 = "L0"  # read-only / analysis — free
RISK_L1 = "L1"  # drafts, local writes — low
RISK_L2 = "L2"  # local consequential (state writes) — gated
RISK_L3 = "L3"  # external send/publish/spend/deploy — approval required
RISK_L4 = "L4"  # high-impact / security / financial execution — strict approval
ALL_RISK_LEVELS = (RISK_L0, RISK_L1, RISK_L2, RISK_L3, RISK_L4)

# Output contract vocabulary.
OUTPUT_CONTRACTS = (
    "structured_report",
    "draft",
    "analysis",
    "plan",
    "dataset",
    "code_change",
    "advisory",
    "notification",
)

# Canonical consequential-action vocabulary used in requires_approval_for.
ACTION_PUBLISH = "publish"
ACTION_OUTREACH = "outreach"
ACTION_SPEND = "spend"
ACTION_DEPLOY = "deploy"
ACTION_TRADE = "trade"
ACTION_SEND_EMAIL = "send_email"
ACTION_SCAN = "scan"
ACTION_DATA_WRITE = "data_write"
ACTION_HIRE = "hire"


@dataclass
class AgentContract:
    """A single agent's formal capability + governance contract."""

    id: str
    role: str
    capabilities: list[str] = field(default_factory=list)
    tools_allowed: list[str] = field(default_factory=list)
    memory_scope: list[str] = field(default_factory=list)
    risk_level: str = RISK_L1
    requires_approval_for: list[str] = field(default_factory=list)
    output_contract: str = "analysis"
    success_metrics: list[str] = field(default_factory=list)
    escalation_rules: list[str] = field(default_factory=list)
    # Provenance from the real catalog (never invented).
    category: str = "general"
    model: str | None = None

    def needs_approval(self, action: str) -> bool:
        """True when `action` is a consequential action this agent may not auto-run."""
        return action in self.requires_approval_for

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AgentContract":
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in data.items() if k in known})
