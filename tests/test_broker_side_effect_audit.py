"""C1/R3 — companion ExecutionBroker side-effect audit (lock-in).

The broker auto-runs only capabilities the SafetyGate clears. This pins the
invariants that keep side effects gate-mediated, so a future capability can't
silently become a high-risk auto-running side effect:

  1. No auto-dispatchable capability is also `requires_approval`.
  2. Only free-to-run levels (L0/L1) are auto-dispatchable; L2+ must route
     through the gate's ask/approve logic, never the broker's direct dispatch.
  3. The canonical dangerous caps (forge.apply_patch, browser.act) are
     approval-gated AND absent from dispatch.
  4. Every auto-dispatchable side-effecting cap is bounded to L1 (local state).
  5. When the gate requires approval, the broker blocks — it never executes.

See docs/SYSTEM_COHERENCE_C1_PLAN.md R3 for the full classification table.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "runtime"))

from companion.capability_registry import get_capability_registry  # noqa: E402
from companion.execution_broker import get_execution_broker  # noqa: E402
from companion.schemas import L0, L1, L2, L3, L4  # noqa: E402

_FREE_TO_RUN = {L0, L1}
_GATED_LEVELS = {L2, L3, L4}


def _all_caps():
    reg = get_capability_registry()
    return list(reg._caps.values())


def _dispatch_ids():
    return set(get_execution_broker()._dispatch.keys())


def test_no_dispatchable_cap_requires_approval():
    """An approval-gated cap must never be auto-runnable from the broker."""
    dispatch = _dispatch_ids()
    offenders = [c.id for c in _all_caps()
                 if c.id in dispatch and getattr(c, "requires_approval", False)]
    assert offenders == [], f"approval-gated caps must not be dispatchable: {offenders}"


def test_only_free_to_run_levels_are_dispatchable():
    """L2+ capabilities must go through the gate's ask/approve path, not the
    broker's direct dispatch table."""
    dispatch = _dispatch_ids()
    offenders = [(c.id, c.risk_level) for c in _all_caps()
                 if c.id in dispatch and c.risk_level in _GATED_LEVELS]
    assert offenders == [], f"L2+ caps must not be auto-dispatchable: {offenders}"


def test_dangerous_caps_are_gated_and_not_dispatchable():
    """The two canonical high-risk side effects stay out of dispatch."""
    reg = get_capability_registry()
    dispatch = _dispatch_ids()
    for cap_id in ("forge.apply_patch", "browser.act"):
        cap = reg.get(cap_id)
        assert cap is not None, f"{cap_id} must exist in the registry"
        assert cap.id not in dispatch, f"{cap_id} must NOT be auto-dispatchable"
        assert getattr(cap, "requires_approval", False), f"{cap_id} must require approval"
        assert cap.risk_level in (L3, L4), f"{cap_id} must be high-risk"


def test_dispatchable_side_effecting_caps_are_bounded_to_L1():
    """Any auto-running cap that has side effects must be at most L1 (bounded
    local state) — nothing higher auto-runs."""
    dispatch = _dispatch_ids()
    offenders = [
        (c.id, c.risk_level, c.side_effects)
        for c in _all_caps()
        if c.id in dispatch and (getattr(c, "side_effects", []) or [])
        and c.risk_level not in _FREE_TO_RUN
    ]
    assert offenders == [], f"side-effecting dispatchable caps must be <= L1: {offenders}"


def test_broker_blocks_side_effect_when_gate_requires_approval(monkeypatch):
    """Behavioural: force the gate to require approval — nothing executes."""
    broker = get_execution_broker()
    monkeypatch.setattr(
        broker._gate, "evaluate",
        lambda cap, ctx: {"allowed": True, "requires_approval": True, "reason": "test-gate"},
    )
    out = broker.execute(
        {"mode": "execution", "task_type": "general", "is_command": True},
        {"resolved_text": "write a structured note to memory about the deadline"},
        {"text": "write a structured note to memory about the deadline",
         "tenant_id": "default"},
    )
    assert out["executed"] == [], "no capability may execute when the gate requires approval"
    # The routed caps surface as approvals/blocked, never silent execution.
    assert not (set(out["executed"]) & _dispatch_ids())
