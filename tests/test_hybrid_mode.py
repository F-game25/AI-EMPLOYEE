"""Unit tests for runtime/agents/ai-router/hybrid_mode.py

Covers:
  - Mode constants and accessors (get_hybrid_mode, set_hybrid_mode)
  - Connectivity probe (check_connectivity — mocked at socket/urllib level)
  - is_online() with caching, failsafe, manual override
  - record_provider_failure / failsafe lifecycle
  - Status reporting (get_status)
  - offline_unavailable_response and offline_search_notice helpers
  - on_mode_change callbacks and transition detection
  - invalidate_connectivity_cache
  - Integration with ai_router convenience functions
"""
from __future__ import annotations

import importlib
import os
import sys
import time
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ── Path setup ────────────────────────────────────────────────────────────────
_ROUTER_DIR = Path(__file__).parent.parent / "runtime" / "agents" / "ai-router"
if str(_ROUTER_DIR) not in sys.path:
    sys.path.insert(0, str(_ROUTER_DIR))


# ── Reload helpers ────────────────────────────────────────────────────────────

def _fresh_hybrid_mode(env_overrides: dict | None = None):
    """Import a freshly-reset hybrid_mode module with optional env overrides."""
    import importlib
    env = env_overrides or {}
    with patch.dict(os.environ, env, clear=False):
        if "hybrid_mode" in sys.modules:
            del sys.modules["hybrid_mode"]
        import hybrid_mode as hm
        # Reset all internal state
        with hm._lock:
            hm._runtime_mode = None
            hm._last_probe_time = 0.0
            hm._last_probe_result = None
            hm._failsafe_active = False
            hm._failsafe_triggered_at = 0.0
            hm._mode_change_callbacks.clear()
            hm._last_effective_mode = None
    return hm


@pytest.fixture(autouse=True)
def reset_hybrid_module(monkeypatch):
    """Ensure hybrid_mode internal state is clean before every test.

    Also mocks check_connectivity to avoid real network calls in the test
    suite.  Individual tests that exercise connectivity probing patch it
    themselves with more specific behaviour.
    """
    import hybrid_mode as hm
    with hm._lock:
        hm._runtime_mode = None
        hm._last_probe_time = 0.0
        hm._last_probe_result = None
        hm._failsafe_active = False
        hm._failsafe_triggered_at = 0.0
        hm._mode_change_callbacks.clear()
        hm._last_effective_mode = None
    # Default: mock check_connectivity to return True so tests don't hit network
    monkeypatch.setattr(hm, "check_connectivity", lambda: True)
    yield


import hybrid_mode as hm


# Save reference to real check_connectivity before any patching
_real_check_connectivity = hm.check_connectivity


# ══════════════════════════════════════════════════════════════════════════════
# Constants
# ══════════════════════════════════════════════════════════════════════════════

class TestModeConstants:
    def test_mode_values(self):
        assert hm.MODE_ONLINE == "online"
        assert hm.MODE_OFFLINE == "offline"
        assert hm.MODE_AUTO == "auto"

    def test_valid_modes_set(self):
        assert hm._VALID_MODES == {"online", "offline", "auto"}


# ══════════════════════════════════════════════════════════════════════════════
# get_hybrid_mode / set_hybrid_mode
# ══════════════════════════════════════════════════════════════════════════════

class TestGetSetHybridMode:
    def test_default_is_auto(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("HYBRID_MODE", None)
            assert hm.get_hybrid_mode() == hm.MODE_AUTO

    def test_env_var_online(self):
        with patch.dict(os.environ, {"HYBRID_MODE": "online"}):
            hm._runtime_mode = None
            assert hm.get_hybrid_mode() == hm.MODE_ONLINE

    def test_env_var_offline(self):
        with patch.dict(os.environ, {"HYBRID_MODE": "offline"}):
            hm._runtime_mode = None
            assert hm.get_hybrid_mode() == hm.MODE_OFFLINE

    def test_env_var_invalid_falls_back_to_auto(self):
        with patch.dict(os.environ, {"HYBRID_MODE": "bogus"}):
            hm._runtime_mode = None
            assert hm.get_hybrid_mode() == hm.MODE_AUTO

    def test_set_mode_online(self):
        hm.set_hybrid_mode("online")
        assert hm.get_hybrid_mode() == hm.MODE_ONLINE

    def test_set_mode_offline(self):
        hm.set_hybrid_mode("offline")
        assert hm.get_hybrid_mode() == hm.MODE_OFFLINE

    def test_set_mode_auto(self):
        hm.set_hybrid_mode("auto")
        assert hm.get_hybrid_mode() == hm.MODE_AUTO

    def test_set_mode_case_insensitive(self):
        hm.set_hybrid_mode("OFFLINE")
        assert hm.get_hybrid_mode() == hm.MODE_OFFLINE

    def test_set_mode_invalid_raises(self):
        with pytest.raises(ValueError, match="Invalid hybrid mode"):
            hm.set_hybrid_mode("turbo")

    def test_runtime_override_takes_priority_over_env(self):
        with patch.dict(os.environ, {"HYBRID_MODE": "online"}):
            hm.set_hybrid_mode("offline")
            assert hm.get_hybrid_mode() == hm.MODE_OFFLINE

    def test_set_mode_clears_failsafe(self):
        with hm._lock:
            hm._failsafe_active = True
            hm._failsafe_triggered_at = time.monotonic()
        hm.set_hybrid_mode("offline")
        assert not hm._failsafe_active


# ══════════════════════════════════════════════════════════════════════════════
# check_connectivity (mocked)
# ══════════════════════════════════════════════════════════════════════════════

class TestCheckConnectivity:
    """Tests for the real check_connectivity function (not the autouse mock)."""

    def test_dns_success(self, monkeypatch):
        """DNS socket probe succeeds → True."""
        mock_sock = MagicMock()
        monkeypatch.setattr("socket.create_connection", lambda *a, **kw: mock_sock)
        # Call the real function (not the autouse-mocked module attribute)
        result = _real_check_connectivity()
        assert result is True
        mock_sock.close.assert_called_once()

    def test_dns_fails_https_fallback_success(self, monkeypatch):
        """DNS fails → HTTPS probe succeeds → True."""
        monkeypatch.setattr(
            "socket.create_connection",
            lambda *a, **kw: (_ for _ in ()).throw(OSError("refused")),
        )
        mock_resp = MagicMock()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        monkeypatch.setattr("urllib.request.urlopen", lambda *a, **kw: mock_resp)
        result = _real_check_connectivity()
        assert result is True

    def test_all_probes_fail(self, monkeypatch):
        """All probes fail → False."""
        monkeypatch.setattr(
            "socket.create_connection",
            lambda *a, **kw: (_ for _ in ()).throw(OSError("refused")),
        )
        monkeypatch.setattr(
            "urllib.request.urlopen",
            lambda *a, **kw: (_ for _ in ()).throw(Exception("timeout")),
        )
        result = _real_check_connectivity()
        assert result is False


# ══════════════════════════════════════════════════════════════════════════════
# is_online — mode overrides
# ══════════════════════════════════════════════════════════════════════════════

class TestIsOnlineModeOverrides:
    def test_forced_online_skips_probe(self):
        hm.set_hybrid_mode("online")
        with patch.object(hm, "check_connectivity", side_effect=AssertionError("should not probe")):
            assert hm.is_online() is True

    def test_forced_offline_skips_probe(self):
        hm.set_hybrid_mode("offline")
        with patch.object(hm, "check_connectivity", side_effect=AssertionError("should not probe")):
            assert hm.is_online() is False

    def test_auto_probes_and_returns_true(self):
        hm.set_hybrid_mode("auto")
        with patch.object(hm, "check_connectivity", return_value=True):
            assert hm.is_online() is True

    def test_auto_probes_and_returns_false(self):
        hm.set_hybrid_mode("auto")
        with patch.object(hm, "check_connectivity", return_value=False):
            assert hm.is_online() is False


# ══════════════════════════════════════════════════════════════════════════════
# is_online — caching
# ══════════════════════════════════════════════════════════════════════════════

class TestIsOnlineCaching:
    def test_result_is_cached(self):
        """Second call should not trigger a new probe within TTL."""
        hm.set_hybrid_mode("auto")
        call_count = {"n": 0}

        def _probe():
            call_count["n"] += 1
            return True

        with patch.object(hm, "check_connectivity", side_effect=_probe):
            hm.is_online()
            hm.is_online()
        assert call_count["n"] == 1, "Cache should prevent second probe"

    def test_invalidate_cache_forces_reprobe(self):
        hm.set_hybrid_mode("auto")
        call_count = {"n": 0}

        def _probe():
            call_count["n"] += 1
            return True

        with patch.object(hm, "check_connectivity", side_effect=_probe):
            hm.is_online()
            hm.invalidate_connectivity_cache()
            hm.is_online()
        assert call_count["n"] == 2

    def test_cache_expires_after_ttl(self):
        hm.set_hybrid_mode("auto")
        # Manually expire the cache
        with hm._lock:
            hm._last_probe_time = time.monotonic() - hm.CONNECTIVITY_CACHE_TTL - 1
            hm._last_probe_result = True

        call_count = {"n": 0}

        def _probe():
            call_count["n"] += 1
            return False

        with patch.object(hm, "check_connectivity", side_effect=_probe):
            result = hm.is_online()
        assert call_count["n"] == 1
        assert result is False


# ══════════════════════════════════════════════════════════════════════════════
# Failsafe
# ══════════════════════════════════════════════════════════════════════════════

class TestFailsafe:
    def test_record_failure_activates_failsafe(self):
        hm.set_hybrid_mode("auto")
        with patch.object(hm, "check_connectivity", return_value=True):
            hm.is_online()  # prime cache
        hm.record_provider_failure("anthropic")
        assert hm.is_failsafe_active() is True

    def test_failsafe_forces_offline(self):
        hm.set_hybrid_mode("auto")
        hm.record_provider_failure("openai")
        with patch.object(hm, "check_connectivity", side_effect=AssertionError("no probe during failsafe")):
            assert hm.is_online() is False

    def test_failsafe_inactive_after_cooldown(self):
        hm.set_hybrid_mode("auto")
        hm.record_provider_failure("nvidia_nim")
        # Expire the cooldown
        with hm._lock:
            hm._failsafe_triggered_at = time.monotonic() - hm.FAILSAFE_COOLDOWN - 1
        assert hm.is_failsafe_active() is False

    def test_failsafe_auto_reset_after_cooldown(self):
        """After cooldown expires, is_online() re-probes and can return True."""
        hm.set_hybrid_mode("auto")
        hm.record_provider_failure("openai")
        with hm._lock:
            hm._failsafe_triggered_at = time.monotonic() - hm.FAILSAFE_COOLDOWN - 1

        with patch.object(hm, "check_connectivity", return_value=True):
            assert hm.is_online() is True

    def test_record_failure_ignored_in_online_mode(self):
        hm.set_hybrid_mode("online")
        hm.record_provider_failure("anthropic")
        assert hm.is_failsafe_active() is False

    def test_record_failure_ignored_in_offline_mode(self):
        hm.set_hybrid_mode("offline")
        hm.record_provider_failure("openai")
        assert hm.is_failsafe_active() is False

    def test_set_mode_clears_failsafe_flag(self):
        hm.set_hybrid_mode("auto")
        hm.record_provider_failure("openai")
        assert hm.is_failsafe_active()
        hm.set_hybrid_mode("online")
        assert not hm.is_failsafe_active()


# ══════════════════════════════════════════════════════════════════════════════
# get_status
# ══════════════════════════════════════════════════════════════════════════════

class TestGetStatus:
    def test_status_keys_present(self):
        with patch.object(hm, "check_connectivity", return_value=True):
            status = hm.get_status()
        expected_keys = {
            "configured_mode", "effective_online", "failsafe_active",
            "failsafe_remaining_s", "cache_age_s", "probe_result",
        }
        assert expected_keys.issubset(status.keys())

    def test_status_online_mode(self):
        hm.set_hybrid_mode("online")
        status = hm.get_status()
        assert status["configured_mode"] == "online"
        assert status["effective_online"] is True
        assert status["failsafe_active"] is False

    def test_status_offline_mode(self):
        hm.set_hybrid_mode("offline")
        status = hm.get_status()
        assert status["configured_mode"] == "offline"
        assert status["effective_online"] is False

    def test_status_failsafe_remaining(self):
        hm.set_hybrid_mode("auto")
        hm.record_provider_failure("openai")
        status = hm.get_status()
        assert status["failsafe_active"] is True
        assert isinstance(status["failsafe_remaining_s"], int)
        assert 0 < status["failsafe_remaining_s"] <= hm.FAILSAFE_COOLDOWN


# ══════════════════════════════════════════════════════════════════════════════
# offline_unavailable_response
# ══════════════════════════════════════════════════════════════════════════════

class TestOfflineUnavailableResponse:
    def test_returns_dict_with_required_keys(self):
        resp = hm.offline_unavailable_response("Web search")
        assert isinstance(resp, dict)
        for k in ("answer", "provider", "model", "error", "usage"):
            assert k in resp

    def test_provider_is_offline(self):
        resp = hm.offline_unavailable_response()
        assert resp["provider"] == "offline"

    def test_error_is_offline_mode(self):
        resp = hm.offline_unavailable_response()
        assert resp["error"] == "offline_mode"

    def test_answer_contains_feature_name(self):
        resp = hm.offline_unavailable_response("Real-time stock data")
        assert "Real-time stock data" in resp["answer"]

    def test_answer_mentions_offline(self):
        resp = hm.offline_unavailable_response()
        assert "offline" in resp["answer"].lower()


# ══════════════════════════════════════════════════════════════════════════════
# offline_search_notice
# ══════════════════════════════════════════════════════════════════════════════

class TestOfflineSearchNotice:
    def test_returns_list(self):
        results = hm.offline_search_notice("AI news")
        assert isinstance(results, list)
        assert len(results) == 1

    def test_result_has_required_keys(self):
        result = hm.offline_search_notice("test query")[0]
        for k in ("title", "url", "snippet", "source"):
            assert k in result

    def test_query_in_snippet(self):
        result = hm.offline_search_notice("quantum computing")[0]
        assert "quantum computing" in result["snippet"]

    def test_source_is_hybrid_mode(self):
        result = hm.offline_search_notice("anything")[0]
        assert result["source"] == "hybrid_mode"


# ══════════════════════════════════════════════════════════════════════════════
# on_mode_change callbacks
# ══════════════════════════════════════════════════════════════════════════════

class TestModeChangeCallbacks:
    def test_callback_called_on_set_mode(self):
        fired = []
        hm.on_mode_change(lambda online: fired.append(online))
        hm.set_hybrid_mode("offline")
        # set_hybrid_mode calls _notify_mode_change("offline") which maps to False
        assert False in fired or True in fired  # at least one call

    def test_callback_receives_bool(self):
        received = []
        hm.on_mode_change(lambda online: received.append(online))
        hm.set_hybrid_mode("online")
        assert all(isinstance(v, bool) for v in received)

    def test_transition_callback_fires_once_per_state_change(self):
        fired = []
        hm.on_mode_change(lambda online: fired.append(online))
        hm.set_hybrid_mode("online")
        with patch.object(hm, "check_connectivity", return_value=True):
            # Force a transition to online
            hm._last_effective_mode = None
            hm.is_online()
        # Calling is_online() again with same result should NOT fire callback again
        initial_count = len(fired)
        with patch.object(hm, "check_connectivity", return_value=True):
            hm.invalidate_connectivity_cache()
            hm.is_online()
        assert len(fired) == initial_count, "Callback should not fire again for same mode"

    def test_broken_callback_does_not_crash(self):
        def _bad_callback(online):
            raise RuntimeError("callback error")

        hm.on_mode_change(_bad_callback)
        # Should not raise
        hm.set_hybrid_mode("offline")


# ══════════════════════════════════════════════════════════════════════════════
# invalidate_connectivity_cache
# ══════════════════════════════════════════════════════════════════════════════

class TestInvalidateCache:
    def test_invalidate_resets_probe_time(self):
        with hm._lock:
            hm._last_probe_time = time.monotonic()
            hm._last_probe_result = True
        hm.invalidate_connectivity_cache()
        with hm._lock:
            assert hm._last_probe_time == 0.0
            assert hm._last_probe_result is None


# ══════════════════════════════════════════════════════════════════════════════
# ai_router integration (hybrid convenience functions)
# ══════════════════════════════════════════════════════════════════════════════

class TestAiRouterIntegration:
    """Ensure the re-exported functions in ai_router delegate to hybrid_mode."""

    @pytest.fixture(autouse=True)
    def import_router(self):
        _ai_router_dir = Path(__file__).parent.parent / "runtime" / "agents" / "ai-router"
        if str(_ai_router_dir) not in sys.path:
            sys.path.insert(0, str(_ai_router_dir))
        import ai_router as ar
        self.ar = ar

    def test_get_hybrid_mode_returns_string(self):
        result = self.ar.get_hybrid_mode()
        assert isinstance(result, str)
        assert result in ("auto", "online", "offline")

    def test_set_hybrid_mode_online(self):
        self.ar.set_hybrid_mode("online")
        assert self.ar.get_hybrid_mode() == "online"
        # Clean up
        self.ar.set_hybrid_mode("auto")

    def test_set_hybrid_mode_offline(self):
        self.ar.set_hybrid_mode("offline")
        assert self.ar.get_hybrid_mode() == "offline"
        # Clean up
        self.ar.set_hybrid_mode("auto")

    def test_hybrid_status_returns_dict(self, monkeypatch):
        monkeypatch.setattr(hm, "check_connectivity", lambda: True)
        status = self.ar.hybrid_status()
        assert isinstance(status, dict)
        assert "configured_mode" in status
        assert "effective_online" in status
        assert "hybrid_module" in status
        assert status["hybrid_module"] is True

    def test_search_web_offline_returns_notice(self):
        """search_web returns offline notice when mode is offline."""
        self.ar.set_hybrid_mode("offline")
        try:
            results = self.ar.search_web("latest AI news")
            assert len(results) >= 1
            assert results[0]["source"] == "hybrid_mode"
            assert "offline" in results[0]["title"].lower() or "OFFLINE" in results[0]["title"]
        finally:
            self.ar.set_hybrid_mode("auto")

    def test_cloud_providers_skipped_when_offline(self):
        """With HYBRID_MODE=offline, NIM/Anthropic/OpenAI _try_* functions return None."""
        self.ar.set_hybrid_mode("offline")
        try:
            # Inject fake API keys so the key-check guard doesn't short-circuit
            import os
            original_nvidia = os.environ.get("NVIDIA_API_KEY", "")
            original_anthropic = os.environ.get("ANTHROPIC_API_KEY", "")
            original_openai = os.environ.get("OPENAI_API_KEY", "")
            os.environ["NVIDIA_API_KEY"] = "fake"
            os.environ["ANTHROPIC_API_KEY"] = "fake"
            os.environ["OPENAI_API_KEY"] = "fake"
            try:
                assert self.ar._try_nvidia_nim("hello", "", []) is None
                assert self.ar._try_anthropic("hello", "", []) is None
                assert self.ar._try_openai("hello", "", []) is None
            finally:
                if original_nvidia:
                    os.environ["NVIDIA_API_KEY"] = original_nvidia
                else:
                    os.environ.pop("NVIDIA_API_KEY", None)
                if original_anthropic:
                    os.environ["ANTHROPIC_API_KEY"] = original_anthropic
                else:
                    os.environ.pop("ANTHROPIC_API_KEY", None)
                if original_openai:
                    os.environ["OPENAI_API_KEY"] = original_openai
                else:
                    os.environ.pop("OPENAI_API_KEY", None)
        finally:
            self.ar.set_hybrid_mode("auto")
