from __future__ import annotations

import json
import sys
from pathlib import Path


RUNTIME_DIR = Path(__file__).resolve().parents[1] / "runtime"
if str(RUNTIME_DIR) not in sys.path:
    sys.path.insert(0, str(RUNTIME_DIR))

from core.wavefield_provider import get_wavefield_metrics, record_wavefield_event, wavefield_allow_fallback, wavefield_healthcheck


class _FakeResp:
    def __init__(self, *, status: int = 200, body: dict | None = None) -> None:
        self.status = status
        self._body = body or {}

    def read(self) -> bytes:
        return json.dumps(self._body).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_wavefield_allow_fallback_default(monkeypatch) -> None:
    monkeypatch.delenv("WAVEFIELD_ALLOW_FALLBACK", raising=False)
    assert wavefield_allow_fallback() is True


def test_wavefield_allow_fallback_off(monkeypatch) -> None:
    monkeypatch.setenv("WAVEFIELD_ALLOW_FALLBACK", "0")
    assert wavefield_allow_fallback() is False


def test_wavefield_healthcheck_requires_model(monkeypatch) -> None:
    monkeypatch.delenv("WAVEFIELD_MODEL", raising=False)
    ok, reason = wavefield_healthcheck(ollama_host="http://localhost:11434")
    assert ok is False
    assert "WAVEFIELD_MODEL" in reason


def test_wavefield_healthcheck_model_found(monkeypatch) -> None:
    monkeypatch.setenv("WAVEFIELD_MODEL", "wave-1")

    def _fake_urlopen(req, timeout=1.0):  # noqa: ARG001
        return _FakeResp(body={"models": [{"name": "wave-1:latest"}]})

    monkeypatch.setattr("urllib.request.urlopen", _fake_urlopen)
    ok, reason = wavefield_healthcheck(ollama_host="http://localhost:11434")
    assert ok is True
    assert reason == "ok"


def test_wavefield_healthcheck_model_missing(monkeypatch) -> None:
    monkeypatch.setenv("WAVEFIELD_MODEL", "wave-1")

    def _fake_urlopen(req, timeout=1.0):  # noqa: ARG001
        return _FakeResp(body={"models": [{"name": "other:latest"}]})

    monkeypatch.setattr("urllib.request.urlopen", _fake_urlopen)
    ok, reason = wavefield_healthcheck(ollama_host="http://localhost:11434")
    assert ok is False
    assert "not pulled" in reason


def test_wavefield_metrics_increment() -> None:
    before = get_wavefield_metrics()
    record_wavefield_event("route_selected")
    after = get_wavefield_metrics()
    assert after["route_selected"] == before["route_selected"] + 1
