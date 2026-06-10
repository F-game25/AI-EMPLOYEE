"""Foundation tests for the Companion Gateway (runtime/companion/)."""
import sys
from pathlib import Path

_RUNTIME = Path(__file__).resolve().parents[1] / "runtime"
if str(_RUNTIME) not in sys.path:
    sys.path.insert(0, str(_RUNTIME))

from companion import schemas  # noqa: E402
from companion.schemas import (  # noqa: E402
    Capability,
    CompanionRequest,
    CompanionResponse,
    L0,
    L1,
    L2,
    L3,
    risk_at_least,
)
from companion.capability_registry import get_capability_registry, CapabilityRegistry  # noqa: E402
from companion.safety_gate import SafetyGate, get_safety_gate  # noqa: E402


# ── Registry seeding ──────────────────────────────────────────────────────────

_EXPECTED_READONLY = {
    "system.health.read",
    "system.tasks.active",
    "system.logs.search",
    "memory.search",
    "forge.search_code",
    "security.score_action",
}
_EXPECTED_ALL = _EXPECTED_READONLY | {
    "memory.write_structured",
    "research.deep.start",
    "money.analyze_idea",
    "forge.plan_change",
    "forge.run_tests",
    "forge.apply_patch",
}


def test_registry_seeds_expected_capabilities():
    reg = get_capability_registry()
    ids = {c.id for c in reg.all()}
    assert _EXPECTED_ALL <= ids, f"missing: {_EXPECTED_ALL - ids}"


def test_apply_patch_is_l3_and_requires_approval():
    cap = get_capability_registry().get("forge.apply_patch")
    assert cap is not None
    assert cap.risk_level == L3
    assert cap.requires_approval is True
    assert "modifies source files on disk" in cap.side_effects


def test_readonly_caps_are_l0_no_approval():
    reg = get_capability_registry()
    for cap_id in _EXPECTED_READONLY:
        cap = reg.get(cap_id)
        assert cap is not None, cap_id
        assert cap.risk_level == L0, f"{cap_id} -> {cap.risk_level}"
        assert cap.requires_approval is False, cap_id


def test_by_subsystem_and_find_for_intent():
    reg = get_capability_registry()
    assert {c.id for c in reg.by_subsystem("forge")} >= {
        "forge.search_code",
        "forge.apply_patch",
        "forge.run_tests",
        "forge.plan_change",
    }
    matches = reg.find_for_intent("search the code for auth", task_type="forge")
    assert matches and matches[0].subsystem == "forge"


def test_to_dicts_serializable():
    dicts = get_capability_registry().to_dicts()
    assert isinstance(dicts, list) and dicts
    assert all(isinstance(d, dict) and "id" in d for d in dicts)


# ── Risk helpers ──────────────────────────────────────────────────────────────

def test_risk_at_least_ordering():
    assert risk_at_least(L3, L1)
    assert risk_at_least(L1, L1)
    assert not risk_at_least(L0, L2)
    assert schemas.RISK_ORDER == (L0, L1, L2, L3, schemas.L4)


# ── Safety gate ───────────────────────────────────────────────────────────────

def _cap(level, requires_approval=False, cid="x.test"):
    return Capability(
        id=cid, subsystem="x", name="t", description="d",
        risk_level=level, requires_approval=requires_approval,
    )


def test_gate_l0_allowed_no_approval():
    gate = SafetyGate()
    r = gate.evaluate(_cap(L0), {})
    assert r["allowed"] is True
    assert r["requires_approval"] is False


def test_gate_l3_requires_approval():
    gate = SafetyGate()
    r = gate.evaluate(_cap(L3, requires_approval=True), {})
    assert r["requires_approval"] is True
    # Pending (non-blocking) -> not yet allowed.
    assert r["allowed"] is False


def test_gate_l2_needs_command_unless_explicit():
    gate = SafetyGate()
    not_commanded = gate.evaluate(_cap(L2), {})
    assert not_commanded["requires_approval"] is True
    assert not_commanded["allowed"] is False

    commanded = gate.evaluate(_cap(L2), {"explicitly_commanded": True})
    assert commanded["allowed"] is True
    assert commanded["requires_approval"] is False


def test_gate_fails_closed_when_hitl_raises(monkeypatch):
    """If the HITL backend raises, a risky action must be BLOCKED, not allowed."""
    gate = SafetyGate()

    def _boom(cap, ctx):
        return {"approved": False, "status": "blocked", "error": "hitl down"}

    monkeypatch.setattr(gate, "_submit_for_approval", _boom)
    r = gate.evaluate(_cap(L3, requires_approval=True), {})
    assert r["allowed"] is False
    assert "fail-closed" in r["reason"]


def test_gate_singleton():
    assert get_safety_gate() is get_safety_gate()


# ── Schema round-trips ────────────────────────────────────────────────────────

def test_capability_roundtrip():
    cap = get_capability_registry().get("forge.apply_patch")
    again = Capability.from_dict(cap.to_dict())
    assert again == cap


def test_request_roundtrip():
    req = CompanionRequest(
        text="hi", session_id="s1", channel="voice",
        context={"page": "orders"}, tenant_id="t1",
    )
    assert CompanionRequest.from_dict(req.to_dict()) == req


def test_response_roundtrip():
    resp = CompanionResponse(
        ok=True, mode="act", reply="done",
        actions=[{"id": "a"}], approvals_required=[],
        avatar_state="thinking", meta={"latency_ms": 12},
    )
    assert CompanionResponse.from_dict(resp.to_dict()) == resp
