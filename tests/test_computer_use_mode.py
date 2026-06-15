"""Computer-Use mode: store persistence + broker master-gate over browser caps."""
import os
import sys
import tempfile
from pathlib import Path

_RUNTIME = Path(__file__).resolve().parents[1] / "runtime"
if str(_RUNTIME) not in sys.path:
    sys.path.insert(0, str(_RUNTIME))


def _fresh_state(monkeypatch):
    d = tempfile.mkdtemp()
    monkeypatch.setenv("STATE_DIR", d)
    import importlib
    import companion.computer_use_mode as cum
    importlib.reload(cum)
    return cum


def test_mode_defaults_off_and_persists(monkeypatch):
    cum = _fresh_state(monkeypatch)
    assert cum.computer_use_enabled() is False
    cum.set_mode(True)
    assert cum.computer_use_enabled() is True
    # A reload reads the same persisted file (survives "restart").
    import importlib
    importlib.reload(cum)
    assert cum.computer_use_enabled() is True
    cum.set_mode(False)
    assert cum.computer_use_enabled() is False


def test_broker_refuses_browser_when_mode_off(monkeypatch):
    cum = _fresh_state(monkeypatch)
    cum.set_mode(False)
    from companion.execution_broker import get_execution_broker
    from companion.capability_registry import get_capability_registry
    reg = get_capability_registry()
    broker = get_execution_broker()
    # Route directly at a browser capability.
    intent = {"mode": "execution", "task_type": "browser", "is_command": True}
    resolved = {"resolved_text": "open example.com and read it"}
    out = broker.execute(intent, resolved, {"text": "open example.com"},
                         only_subsystems={"browser"})
    statuses = [r.get("status") for r in out["results"]]
    # Every browser candidate is disabled (not executed, not an approval).
    assert out["executed"] == []
    assert any(s == "disabled" for s in statuses) or out["results"] == [] or \
        all(s == "disabled" for s in statuses if s)
    # No browser cap should have produced an approval card while OFF.
    assert out["approvals_required"] == [] or all(
        not a.get("cap", "").startswith("browser.") for a in out["approvals_required"]
    )


def test_browser_open_runs_when_mode_on(monkeypatch):
    cum = _fresh_state(monkeypatch)
    cum.set_mode(True)
    from companion.execution_broker import get_execution_broker
    broker = get_execution_broker()
    intent = {"mode": "execution", "task_type": "browser", "is_command": True}
    resolved = {"resolved_text": "open a blocked local url"}
    # Use a URL the url_guard refuses → executor returns a structured refusal,
    # proving the gate let it THROUGH to the executor (mode ON) without crashing.
    out = broker.execute(intent, resolved,
                         {"text": "open http://127.0.0.1:1", "url": "http://127.0.0.1:1"},
                         only_subsystems={"browser"})
    statuses = [r.get("status") for r in out["results"]]
    # When ON, browser caps are no longer "disabled" by the master switch.
    assert "disabled" not in statuses


def test_browser_act_is_approval_gated_when_on(monkeypatch):
    """High-risk-only model: browser.act needs approval even with mode ON."""
    cum = _fresh_state(monkeypatch)
    cum.set_mode(True)
    from companion.capability_registry import get_capability_registry
    from companion.safety_gate import get_safety_gate
    reg = get_capability_registry()
    act = reg.get("browser.act")
    assert act is not None and act.requires_approval is True
    decision = get_safety_gate().evaluate(act, {"explicitly_commanded": True})
    assert decision.get("requires_approval") is True
