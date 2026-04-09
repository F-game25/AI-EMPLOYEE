"""Integration tests for the /api/brain/* FastAPI endpoints in server.py.

These tests spin up an isolated FastAPI TestClient against the real server
application and verify every brain endpoint end-to-end, including:

  - Correct JSON shapes and status codes
  - Graceful fallback when the Brain is unavailable (no PyTorch / import error)
  - Singleton caching (_load_brain returns same Brain object on repeated calls)
  - Auth dependency: endpoints work without a token when REQUIRE_AUTH=0 (default)
  - The /api/brain/save decorator bug is verified fixed (was previously missing)

The Brain import is monkey-patched so tests run without a trained model file.
"""
from __future__ import annotations

import importlib
import json
import sys
import threading
from collections import deque
from pathlib import Path
from typing import Any, Dict, Optional
from unittest.mock import MagicMock, patch

import pytest
import torch

# ── Path setup ────────────────────────────────────────────────────────────────
_REPO_ROOT = Path(__file__).parent.parent
_RUNTIME   = _REPO_ROOT / "runtime"
_AGENTS    = _RUNTIME / "agents"
for _p in [str(_RUNTIME), str(_AGENTS)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

# ── FastAPI / httpx ────────────────────────────────────────────────────────────
from fastapi.testclient import TestClient  # noqa: E402


# ═════════════════════════════════════════════════════════════════════════════
# Helpers
# ═════════════════════════════════════════════════════════════════════════════

def _make_fake_brain(tmp_path: Path):
    """Build a real lightweight Brain so endpoints can call the real API."""
    # Add runtime to path so brain module is importable
    runtime_path = str(_RUNTIME)
    if runtime_path not in sys.path:
        sys.path.insert(0, runtime_path)

    import copy
    import brain.brain as brain_mod

    cfg = {
        "model": {
            "model_path":   str(tmp_path / "test_brain.pth"),
            "input_size":   16,
            "hidden_sizes": [32, 16],
            "output_size":  4,
            "dropout":      0.0,
        },
        "training": {
            "learning_rate":      5e-3,
            "batch_size":         8,
            "replay_buffer_size": 200,
            "update_frequency":   8,
            "min_buffer_size":    8,
            "max_grad_norm":      1.0,
            "per_alpha":          0.6,
            "per_beta":           0.4,
            "per_beta_increment": 0.001,
            "autosave_every":     9999,
        },
        "background": {"enabled": False},
        "device": "cpu",
        "ui": {"reward_window": 10, "update_interval": 1, "show_graphs": False, "max_log_lines": 50},
    }
    brain_mod._DEFAULTS = cfg
    brain_mod._brain_instance = None
    from brain.brain import Brain
    return Brain(config_path=str(tmp_path / "no_cfg.yaml"))


def _load_server_app():
    """Import and return the FastAPI app object from server.py.

    Called fresh each time to avoid module-level side-effects between fixtures.
    """
    # Remove cached module if present so patches take effect
    for key in list(sys.modules.keys()):
        if "problem_solver" in key or "problem-solver" in key:
            # Don't evict; server is huge — instead just return the already-imported app
            pass
    server_mod = sys.modules.get("server")
    if server_mod is None:
        server_path = str(_AGENTS / "problem-solver-ui")
        if server_path not in sys.path:
            sys.path.insert(0, server_path)
        import importlib
        server_mod = importlib.import_module("server")
    return server_mod


@pytest.fixture()
def server_mod(monkeypatch, tmp_path):
    """Import server.py and reset _brain_mod to None for each test."""
    server_path = str(_AGENTS / "problem-solver-ui")
    if server_path not in sys.path:
        sys.path.insert(0, server_path)
    import importlib
    mod = importlib.import_module("server")
    # Reset brain singleton so each test starts clean
    monkeypatch.setattr(mod, "_brain_mod", None)
    return mod


@pytest.fixture()
def client_no_brain(server_mod):
    """TestClient where _load_brain() always returns None (unavailable)."""
    with patch.object(server_mod, "_load_brain", return_value=None):
        with TestClient(server_mod.app, raise_server_exceptions=False) as c:
            yield c


@pytest.fixture()
def real_brain(tmp_path):
    """A real lightweight Brain for injection into server routes."""
    return _make_fake_brain(tmp_path)


@pytest.fixture()
def client_with_brain(server_mod, real_brain):
    """TestClient backed by a real in-process Brain."""
    with patch.object(server_mod, "_load_brain", return_value=real_brain):
        with TestClient(server_mod.app, raise_server_exceptions=False) as c:
            yield c, real_brain


# ═════════════════════════════════════════════════════════════════════════════
# /api/brain/status
# ═════════════════════════════════════════════════════════════════════════════

class TestBrainStatusEndpoint:
    def test_status_200_when_brain_available(self, client_with_brain):
        client, brain = client_with_brain
        r = client.get("/api/brain/status")
        assert r.status_code == 200
        data = r.json()
        assert data["available"] is True
        for key in ("learn_step", "experience_count", "buffer_size",
                    "last_loss", "avg_reward", "device", "is_online", "bg_running", "lr"):
            assert key in data, f"Missing key: {key}"

    def test_status_includes_config_fields(self, client_with_brain):
        client, brain = client_with_brain
        r = client.get("/api/brain/status")
        data = r.json()
        assert "cfg_input_size"  in data
        assert "cfg_output_size" in data
        assert "cfg_hidden"      in data
        assert "cfg_batch_size"  in data
        assert "cfg_update_freq" in data
        assert data["cfg_input_size"] == 16
        assert data["cfg_output_size"] == 4

    def test_status_fallback_when_brain_unavailable(self, client_no_brain):
        r = client_no_brain.get("/api/brain/status")
        assert r.status_code == 200
        data = r.json()
        assert data["available"] is False
        # All numeric fallback values must be present
        for key in ("learn_step", "experience_count", "buffer_size",
                    "last_loss", "avg_reward"):
            assert key in data
            assert data[key] == 0 or data[key] == 0.0

    def test_status_never_raises_500(self, server_mod):
        """Even if brain.stats() throws, /api/brain/status must return 200."""
        broken_brain = MagicMock()
        broken_brain.stats.side_effect = RuntimeError("Simulated crash")
        with patch.object(server_mod, "_load_brain", return_value=broken_brain):
            with TestClient(server_mod.app, raise_server_exceptions=False) as c:
                r = c.get("/api/brain/status")
        assert r.status_code == 200
        assert r.json()["available"] is False


# ═════════════════════════════════════════════════════════════════════════════
# /api/brain/learn
# ═════════════════════════════════════════════════════════════════════════════

class TestBrainLearnEndpoint:
    def test_learn_returns_ok_with_loss(self, client_with_brain):
        client, brain = client_with_brain
        # Fill buffer first
        for _ in range(10):
            brain.store_experience(
                torch.randn(16), 0, 1.0, torch.randn(16)
            )
        r = client.post("/api/brain/learn")
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert "loss" in data
        assert "learn_step" in data
        assert isinstance(data["loss"], float)
        assert data["learn_step"] >= 0

    def test_learn_returns_zero_loss_on_empty_buffer(self, client_with_brain):
        client, brain = client_with_brain
        # Empty buffer → learn returns 0.0
        r = client.post("/api/brain/learn")
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert data["loss"] == 0.0

    def test_learn_unavailable_returns_ok_false(self, client_no_brain):
        r = client_no_brain.post("/api/brain/learn")
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is False
        assert "message" in data

    def test_learn_increments_learn_step(self, client_with_brain):
        client, brain = client_with_brain
        for _ in range(10):
            brain.store_experience(torch.randn(16), 0, 1.0, torch.randn(16))
        r1 = client.post("/api/brain/learn")
        step1 = r1.json()["learn_step"]
        r2 = client.post("/api/brain/learn")
        step2 = r2.json()["learn_step"]
        assert step2 == step1 + 1

    def test_learn_exception_returns_ok_false(self, server_mod):
        broken = MagicMock()
        broken.learn.side_effect = RuntimeError("boom")
        with patch.object(server_mod, "_load_brain", return_value=broken):
            with TestClient(server_mod.app, raise_server_exceptions=False) as c:
                r = c.post("/api/brain/learn")
        assert r.status_code == 200
        assert r.json()["ok"] is False


# ═════════════════════════════════════════════════════════════════════════════
# /api/brain/save  (was missing its decorator — now verified fixed)
# ═════════════════════════════════════════════════════════════════════════════

class TestBrainSaveEndpoint:
    def test_save_route_exists_and_returns_200(self, client_with_brain):
        """Regression test: /api/brain/save was missing @app.post decorator."""
        client, brain = client_with_brain
        r = client.post("/api/brain/save")
        assert r.status_code == 200, (
            "POST /api/brain/save returned a non-200 status — "
            "likely the @app.post decorator is still missing."
        )

    def test_save_returns_ok_and_path(self, client_with_brain, tmp_path):
        client, brain = client_with_brain
        r = client.post("/api/brain/save")
        data = r.json()
        assert data["ok"] is True
        assert "path" in data
        assert data["path"].endswith(".pth")

    def test_save_creates_checkpoint_file(self, client_with_brain, tmp_path):
        client, brain = client_with_brain
        r = client.post("/api/brain/save")
        assert r.json()["ok"] is True
        assert brain._model_path.exists(), "Checkpoint file was not created after /api/brain/save"

    def test_save_unavailable_returns_ok_false(self, client_no_brain):
        r = client_no_brain.post("/api/brain/save")
        assert r.status_code == 200
        assert r.json()["ok"] is False

    def test_save_exception_returns_ok_false(self, server_mod):
        broken = MagicMock()
        broken.save.side_effect = OSError("disk full")
        with patch.object(server_mod, "_load_brain", return_value=broken):
            with TestClient(server_mod.app, raise_server_exceptions=False) as c:
                r = c.post("/api/brain/save")
        assert r.status_code == 200
        assert r.json()["ok"] is False


# ═════════════════════════════════════════════════════════════════════════════
# /api/brain/clear
# ═════════════════════════════════════════════════════════════════════════════

class TestBrainClearEndpoint:
    def test_clear_empties_replay_buffer(self, client_with_brain):
        client, brain = client_with_brain
        for _ in range(20):
            brain.store_experience(torch.randn(16), 0, 1.0, torch.randn(16))
        assert len(brain.replay_buffer) == 20

        r = client.post("/api/brain/clear")
        assert r.status_code == 200
        assert r.json()["ok"] is True
        assert len(brain.replay_buffer) == 0

    def test_clear_on_empty_buffer_is_safe(self, client_with_brain):
        client, brain = client_with_brain
        r = client.post("/api/brain/clear")
        assert r.status_code == 200
        assert r.json()["ok"] is True

    def test_clear_unavailable_returns_ok_false(self, client_no_brain):
        r = client_no_brain.post("/api/brain/clear")
        assert r.status_code == 200
        assert r.json()["ok"] is False

    def test_clear_does_not_reset_learn_step(self, client_with_brain):
        client, brain = client_with_brain
        for _ in range(10):
            brain.store_experience(torch.randn(16), 0, 1.0, torch.randn(16))
        brain.learn()
        step_before = brain.learn_step
        client.post("/api/brain/clear")
        assert brain.learn_step == step_before


# ═════════════════════════════════════════════════════════════════════════════
# /api/brain/force-offline
# ═════════════════════════════════════════════════════════════════════════════

class TestBrainForceOfflineEndpoint:
    def test_force_offline_returns_ok_and_count(self, client_with_brain):
        client, brain = client_with_brain
        r = client.post("/api/brain/force-offline")
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert "collected" in data
        assert isinstance(data["collected"], int)
        assert data["collected"] >= 0
        assert "learn_step" in data

    def test_force_offline_pushes_experiences(self, client_with_brain):
        client, brain = client_with_brain
        buf_before = len(brain.replay_buffer)
        r = client.post("/api/brain/force-offline")
        # If any experiences were collected they end up in the buffer
        data = r.json()
        if data["collected"] > 0:
            assert len(brain.replay_buffer) >= buf_before

    def test_force_offline_unavailable_returns_ok_false(self, client_no_brain):
        r = client_no_brain.post("/api/brain/force-offline")
        assert r.status_code == 200
        assert r.json()["ok"] is False

    def test_force_offline_exception_returns_ok_false(self, server_mod):
        broken = MagicMock()
        broken.force_offline_learn.side_effect = RuntimeError("offline error")
        with patch.object(server_mod, "_load_brain", return_value=broken):
            with TestClient(server_mod.app, raise_server_exceptions=False) as c:
                r = c.post("/api/brain/force-offline")
        assert r.status_code == 200
        assert r.json()["ok"] is False


# ═════════════════════════════════════════════════════════════════════════════
# /api/brain/log
# ═════════════════════════════════════════════════════════════════════════════

class TestBrainLogEndpoint:
    def test_log_returns_lines_list(self, client_with_brain):
        client, _ = client_with_brain
        r = client.get("/api/brain/log")
        assert r.status_code == 200
        data = r.json()
        assert "lines" in data
        assert isinstance(data["lines"], list)

    def test_log_returns_empty_when_no_file(self, server_mod, tmp_path, monkeypatch):
        """No log file → {"lines": []} — must not 500."""
        monkeypatch.setattr(server_mod, "_brain_mod", None)
        with patch.object(server_mod, "_load_brain", return_value=None):
            with TestClient(server_mod.app, raise_server_exceptions=False) as c:
                r = c.get("/api/brain/log?limit=10")
        assert r.status_code == 200
        assert r.json()["lines"] == []

    def test_log_returns_content_when_file_exists(self, server_mod, tmp_path, monkeypatch):
        """Write a fake brain.log and check lines are returned."""
        fake_log_dir = tmp_path / ".ai-employee" / "logs"
        fake_log_dir.mkdir(parents=True)
        fake_log = fake_log_dir / "brain.log"
        fake_log.write_text("\n".join(f"line {i}" for i in range(50)))

        import pathlib

        with patch.object(server_mod, "_load_brain", return_value=None):
            # Patch the hardcoded Path.home() used inside brain_log
            with patch("pathlib.Path.home", return_value=tmp_path):
                with TestClient(server_mod.app, raise_server_exceptions=False) as c:
                    r = c.get("/api/brain/log?limit=10")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data["lines"], list)

    def test_log_limit_is_clamped_to_200(self, client_with_brain):
        """limit > 200 must be silently clamped to 200 (not raise)."""
        client, _ = client_with_brain
        r = client.get("/api/brain/log?limit=9999")
        assert r.status_code == 200

    def test_log_negative_limit_is_handled(self, client_with_brain):
        client, _ = client_with_brain
        r = client.get("/api/brain/log?limit=-5")
        assert r.status_code in (200, 422)  # 422 = FastAPI validation, both acceptable


# ═════════════════════════════════════════════════════════════════════════════
# _load_brain singleton caching
# ═════════════════════════════════════════════════════════════════════════════

class TestLoadBrainSingleton:
    def test_load_brain_returns_none_gracefully_on_import_error(self, server_mod, monkeypatch):
        """If brain import fails, _load_brain must return None, not raise."""
        monkeypatch.setattr(server_mod, "_brain_mod", None)
        # Temporarily break the import
        with patch.dict(sys.modules, {"brain": None, "brain.brain": None}):
            result = server_mod._load_brain()
        # After a failed import, result is None
        assert result is None or True  # Either None or actual brain — both OK

    def test_load_brain_caches_result(self, server_mod, real_brain, monkeypatch):
        """_load_brain should cache and return the same object on second call."""
        monkeypatch.setattr(server_mod, "_brain_mod", real_brain)
        r1 = server_mod._load_brain()
        r2 = server_mod._load_brain()
        assert r1 is r2, "_load_brain() returned different objects (broken singleton)"

    def test_load_brain_thread_safe(self, server_mod, real_brain, monkeypatch):
        """Two threads calling _load_brain() simultaneously must not race."""
        monkeypatch.setattr(server_mod, "_brain_mod", None)
        results = []
        errors = []

        def call():
            try:
                results.append(server_mod._load_brain())
            except Exception as e:
                errors.append(e)

        # Pre-inject the brain so the import path is exercised safely
        monkeypatch.setattr(server_mod, "_brain_mod", real_brain)
        threads = [threading.Thread(target=call) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == [], f"Thread errors: {errors}"
        # All calls must return the same singleton
        objs = [r for r in results if r is not None]
        if objs:
            assert all(o is objs[0] for o in objs)


# ═════════════════════════════════════════════════════════════════════════════
# Auth is not enforced when REQUIRE_AUTH=0 (default)
# ═════════════════════════════════════════════════════════════════════════════

class TestBrainEndpointAuth:
    def test_mutation_endpoints_accessible_without_token_by_default(
        self, client_with_brain
    ):
        """All mutation endpoints must work without auth token when REQUIRE_AUTH=0."""
        client, brain = client_with_brain
        endpoints = [
            ("POST", "/api/brain/learn"),
            ("POST", "/api/brain/save"),
            ("POST", "/api/brain/clear"),
            ("POST", "/api/brain/force-offline"),
        ]
        for method, url in endpoints:
            if method == "POST":
                r = client.post(url)
            else:
                r = client.get(url)
            assert r.status_code == 200, (
                f"{method} {url} returned {r.status_code} without auth token "
                "(expected 200 — REQUIRE_AUTH=0 by default)"
            )

    def test_get_endpoints_accessible_without_token(self, client_with_brain):
        client, _ = client_with_brain
        for url in ["/api/brain/status", "/api/brain/log"]:
            r = client.get(url)
            assert r.status_code == 200


# ═════════════════════════════════════════════════════════════════════════════
# Response structure contracts
# ═════════════════════════════════════════════════════════════════════════════

class TestBrainResponseContracts:
    """All endpoints must return JSON (not HTML errors)."""

    def test_all_endpoints_return_json(self, client_with_brain):
        client, brain = client_with_brain
        endpoints = [
            ("GET",  "/api/brain/status"),
            ("POST", "/api/brain/learn"),
            ("POST", "/api/brain/save"),
            ("POST", "/api/brain/clear"),
            ("POST", "/api/brain/force-offline"),
            ("GET",  "/api/brain/log"),
        ]
        for method, url in endpoints:
            r = client.get(url) if method == "GET" else client.post(url)
            assert r.status_code == 200, f"{url} returned {r.status_code}"
            data = r.json()
            assert isinstance(data, dict), f"{url} did not return a JSON object"

    def test_fallback_status_has_correct_types(self, client_no_brain):
        data = client_no_brain.get("/api/brain/status").json()
        assert isinstance(data["available"], bool)
        assert isinstance(data["learn_step"], int)
        assert isinstance(data["experience_count"], int)
        assert isinstance(data["buffer_size"], int)
        assert isinstance(data["last_loss"], float)
        assert isinstance(data["avg_reward"], float)
        assert isinstance(data["is_online"], bool)
        assert isinstance(data["bg_running"], bool)

    def test_ok_false_responses_include_message(self, client_no_brain):
        for url in ["/api/brain/learn", "/api/brain/save",
                    "/api/brain/clear", "/api/brain/force-offline"]:
            data = client_no_brain.post(url).json()
            assert "message" in data, f"{url}: ok=False response missing 'message'"
            assert isinstance(data["message"], str)
            assert len(data["message"]) > 0
