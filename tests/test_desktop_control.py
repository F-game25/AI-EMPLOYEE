"""HITL-gated desktop control — the security contract.

Verifies OFF-by-default, deny-when-off, per-action approval required, gates
enforced even when approved, and the desktop sub-switch needs the master switch.
None of these touch a real display (all hit the deny paths before the driver).
"""
import companion.computer_use_mode as cm
import companion.desktop_control as dc


def _isolate(tmp_path, monkeypatch):
    monkeypatch.setenv("STRICT_PIPELINE", "1")
    monkeypatch.setenv("AI_HOME", str(tmp_path))
    monkeypatch.setattr(cm, "_state_dir", lambda: tmp_path)


def test_off_by_default(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    assert cm.desktop_enabled() is False
    assert dc.desktop_ready()["ready"] is False


def test_screenshot_denied_when_off(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    r = dc.screenshot()
    assert r["ok"] is False and r["status"] == "denied"


def test_desktop_sub_switch_requires_master(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    cm.set_desktop(True)               # sub-switch on, master still off
    assert cm.desktop_enabled() is False  # needs BOTH
    cm.set_mode(True)
    assert cm.desktop_enabled() is True


def test_plan_action_flags_approval_and_rejects_unknown(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    assert dc.plan_action("click", x=10, y=20)["plan"]["requires_approval"] is True
    assert dc.plan_action("screenshot")["plan"]["requires_approval"] is False
    assert dc.plan_action("rm_rf_everything")["ok"] is False


def test_actuation_blocked_without_approval(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    cm.set_mode(True)
    cm.set_desktop(True)  # gates fully ON
    r = dc.execute_approved({"action": "click", "params": {"x": 1, "y": 2}}, approved=False)
    assert r["ok"] is False and "not approved" in r["reason"]


def test_execute_blocked_when_gates_off_even_if_approved(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    # gates OFF; approved=True must STILL be denied (gates checked after approval)
    r = dc.execute_approved({"action": "type", "params": {"text": "x"}}, approved=True)
    assert r["ok"] is False and r["status"] == "denied"


def test_non_approvable_action_rejected(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    cm.set_mode(True)
    cm.set_desktop(True)
    r = dc.execute_approved({"action": "screenshot"}, approved=True)
    assert r["ok"] is False  # screenshot isn't an "approvable" actuation route


def test_audit_redacts_command_payload(monkeypatch):
    recorded = {}

    class FakeAudit:
        def record(self, **kwargs):
            recorded.update(kwargs)

    import core.audit_engine as audit_engine

    monkeypatch.setattr(audit_engine, "get_audit_engine", lambda: FakeAudit())
    monkeypatch.setattr(dc, "get_bus", lambda: None, raising=False)
    dc._audit("execute", action="run", command="echo $SECRET", token="abc", x=1)

    assert recorded["input_data"]["command"] == "***"
    assert recorded["input_data"]["token"] == "***"
    assert recorded["input_data"]["x"] == 1


def test_screenshot_save_dir_stays_under_artifacts(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    cm.set_mode(True)
    cm.set_desktop(True)
    saved = {}

    class FakeImage:
        size = (10, 20)

        def save(self, path):
            saved["path"] = path

    class FakePyAutoGui:
        FAILSAFE = False

        @staticmethod
        def screenshot():
            return FakeImage()

    monkeypatch.setattr(dc, "_pyautogui", lambda: FakePyAutoGui())
    monkeypatch.setattr(dc, "_artifacts_dir", lambda: tmp_path / "artifacts")
    monkeypatch.setattr(dc, "_audit", lambda *args, **kwargs: None)

    result = dc.screenshot(save_dir="/tmp/outside")

    assert result["ok"] is True
    assert (tmp_path / "artifacts").resolve() in saved["path"].resolve().parents
