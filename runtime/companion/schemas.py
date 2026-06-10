"""Typed contracts for the Companion Gateway.

Stdlib-only dataclasses (no pydantic) so they serialize cleanly across the
Node<->Python worker boundary. Every dataclass exposes ``to_dict()`` and a
classmethod ``from_dict()`` for JSON transport.

Risk model (from MASTER_PLAN_V3, phase P4):
    L0 read-only (free)
    L1 low
    L2 medium      — ask if not clearly commanded
    L3 high        — file edits / commands / deploy -> approval required
    L4 critical    — delete / credentials / payments -> approval + explicit confirm + audit
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any


# ── Risk levels ──────────────────────────────────────────────────────────────

L0 = "L0"  # read-only — free to run
L1 = "L1"  # low — free to run
L2 = "L2"  # medium — ask unless explicitly commanded
L3 = "L3"  # high — approval required
L4 = "L4"  # critical — approval + explicit confirm + audit

#: Ordered low -> high. Index in this tuple is the comparable rank.
RISK_ORDER: tuple[str, ...] = (L0, L1, L2, L3, L4)


class RiskLevel:
    """Namespace of risk-level constants + the ordered tuple."""

    L0 = L0
    L1 = L1
    L2 = L2
    L3 = L3
    L4 = L4
    ORDER: tuple[str, ...] = RISK_ORDER


def risk_rank(level: str) -> int:
    """Comparable rank for a risk level. Unknown levels sort below L0 (-1)."""
    try:
        return RISK_ORDER.index(level)
    except ValueError:
        return -1


def risk_at_least(a: str, b: str) -> bool:
    """True when risk level ``a`` is at least as severe as ``b``."""
    return risk_rank(a) >= risk_rank(b)


# ── Capability descriptor ────────────────────────────────────────────────────

@dataclass
class Capability:
    """A typed descriptor of something the companion can route to.

    Descriptor only — it carries no execution logic. The execution broker
    (later phase) is responsible for actually invoking the subsystem.
    """

    id: str
    subsystem: str
    name: str
    description: str
    input_schema: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] = field(default_factory=dict)
    risk_level: str = L0
    requires_approval: bool = False
    side_effects: list[str] = field(default_factory=list)
    timeout_ms: int = 30000
    examples: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Capability":
        return cls(
            id=data["id"],
            subsystem=data["subsystem"],
            name=data["name"],
            description=data["description"],
            input_schema=dict(data.get("input_schema") or {}),
            output_schema=dict(data.get("output_schema") or {}),
            risk_level=data.get("risk_level", L0),
            requires_approval=bool(data.get("requires_approval", False)),
            side_effects=list(data.get("side_effects") or []),
            timeout_ms=int(data.get("timeout_ms", 30000)),
            examples=list(data.get("examples") or []),
        )


# ── Request / response envelope ──────────────────────────────────────────────

@dataclass
class CompanionRequest:
    """A single turn coming in from any channel."""

    text: str
    session_id: str
    channel: str = "chat"  # 'chat' | 'voice' | 'dashboard' | 'api'
    context: dict[str, Any] = field(default_factory=dict)  # page/selection/recent events
    tenant_id: str = "default"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CompanionRequest":
        return cls(
            text=data.get("text", ""),
            session_id=data.get("session_id", ""),
            channel=data.get("channel", "chat"),
            context=dict(data.get("context") or {}),
            tenant_id=data.get("tenant_id", "default"),
        )


@dataclass
class CompanionResponse:
    """The companion's reply for a turn."""

    ok: bool
    mode: str
    reply: str
    actions: list[dict[str, Any]] = field(default_factory=list)
    approvals_required: list[dict[str, Any]] = field(default_factory=list)
    avatar_state: str = "idle"
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CompanionResponse":
        return cls(
            ok=bool(data.get("ok", False)),
            mode=data.get("mode", ""),
            reply=data.get("reply", ""),
            actions=list(data.get("actions") or []),
            approvals_required=list(data.get("approvals_required") or []),
            avatar_state=data.get("avatar_state", "idle"),
            meta=dict(data.get("meta") or {}),
        )
