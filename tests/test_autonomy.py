"""Tests for runtime/core/system_mode.py and runtime/core/autonomy_daemon.py."""
import json
import sys
import time
import threading
from pathlib import Path

import pytest

# Ensure runtime/ is importable
_RUNTIME = Path(__file__).resolve().parent.parent / "runtime"
if str(_RUNTIME) not in sys.path:
    sys.path.insert(0, str(_RUNTIME))


# ── SystemMode tests ──────────────────────────────────────────────────────────

class TestSystemMode:
    """Test the SystemMode singleton."""

    def _make(self, tmp_path):
        # Reset singleton for test isolation
        import core.system_mode as sm_mod
        sm_mod._instance = None
        path = tmp_path / "system_mode.json"
        return sm_mod.SystemMode(path=path)

    def test_default_mode_is_off(self, tmp_path):
        sm = self._make(tmp_path)
        assert sm.current_mode == "OFF"

    def test_set_mode_valid(self, tmp_path):
        sm = self._make(tmp_path)
        result = sm.set_mode("AUTO")
        assert result == "AUTO"
        assert sm.current_mode == "AUTO"
        assert sm.is_auto()
        assert sm.is_active()
        assert not sm.is_off()

    def test_set_mode_on(self, tmp_path):
        sm = self._make(tmp_path)
        sm.set_mode("ON")
        assert sm.is_on()
        assert sm.is_active()

    def test_set_mode_invalid_raises(self, tmp_path):
        sm = self._make(tmp_path)
        with pytest.raises(ValueError, match="Unknown mode"):
            sm.set_mode("TURBO")

    def test_emergency_stop(self, tmp_path):
        sm = self._make(tmp_path)
        sm.set_mode("AUTO")
        sm.emergency_stop()
        assert sm.current_mode == "OFF"
        assert sm.emergency_stopped

    def test_set_mode_clears_emergency(self, tmp_path):
        sm = self._make(tmp_path)
        sm.emergency_stop()
        assert sm.emergency_stopped
        sm.set_mode("ON")
        assert not sm.emergency_stopped

    def test_persistence(self, tmp_path):
        import core.system_mode as sm_mod
        sm_mod._instance = None
        path = tmp_path / "system_mode.json"
        sm1 = sm_mod.SystemMode(path=path)
        sm1.set_mode("AUTO")

        sm_mod._instance = None
        sm2 = sm_mod.SystemMode(path=path)
        assert sm2.current_mode == "AUTO"

    def test_status_dict(self, tmp_path):
        sm = self._make(tmp_path)
        sm.set_mode("AUTO")
        s = sm.status()
        assert s["mode"] == "AUTO"
        assert s["active"] is True
        assert s["auto"] is True
        assert s["paused"] is False

    def test_case_insensitive(self, tmp_path):
        sm = self._make(tmp_path)
        sm.set_mode("auto")
        assert sm.current_mode == "AUTO"

    def test_listener_called(self, tmp_path):
        sm = self._make(tmp_path)
        results = []
        sm.on_change(lambda m: results.append(m))
        sm.set_mode("ON")
        assert results == ["ON"]


# ── AutonomyDaemon tests ─────────────────────────────────────────────────────

class TestAutonomyDaemon:
    """Test the AutonomyDaemon lifecycle."""

    def _make(self, tmp_path):
        # Reset singletons
        import core.system_mode as sm_mod
        import core.autonomy_daemon as ad_mod
        import core.self_improvement.queue as q_mod
        import core.self_improvement.controller as c_mod
        import core.self_improvement.telemetry as t_mod

        sm_mod._instance = None
        ad_mod._instance = None
        q_mod._instance = None
        c_mod._instance = None
        t_mod._instance = None

        sm = sm_mod.SystemMode(path=tmp_path / "mode.json")
        sm_mod._instance = sm

        q = q_mod.ImprovementQueue(path=tmp_path / "queue.json")
        q_mod._instance = q

        daemon = ad_mod.AutonomyDaemon()
        ad_mod._instance = daemon
        return sm, daemon

    def test_start_stop(self, tmp_path):
        sm, daemon = self._make(tmp_path)
        assert not daemon.running
        daemon.start()
        assert daemon.running
        daemon.stop()
        assert not daemon.running

    def test_double_start_idempotent(self, tmp_path):
        sm, daemon = self._make(tmp_path)
        daemon.start()
        daemon.start()  # should not error
        assert daemon.running
        daemon.stop()

    def test_status_structure(self, tmp_path):
        sm, daemon = self._make(tmp_path)
        s = daemon.status()
        assert "daemon" in s
        assert "mode" in s
        assert "queue" in s
        assert s["daemon"]["running"] is False

    def test_off_mode_no_processing(self, tmp_path):
        sm, daemon = self._make(tmp_path)
        sm.set_mode("OFF")
        daemon.start()
        time.sleep(0.3)
        assert daemon.status()["daemon"]["tasks_processed"] == 0
        daemon.stop()

    def test_auto_mode_empty_queue(self, tmp_path):
        sm, daemon = self._make(tmp_path)
        sm.set_mode("AUTO")
        daemon.start()
        time.sleep(0.3)
        # No tasks queued, so nothing processed
        assert daemon.status()["daemon"]["tasks_processed"] == 0
        daemon.stop()
