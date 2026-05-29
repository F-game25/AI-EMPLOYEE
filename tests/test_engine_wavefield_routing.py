from __future__ import annotations

import sys
from pathlib import Path


RUNTIME_DIR = Path(__file__).resolve().parents[1] / "runtime"
if str(RUNTIME_DIR) not in sys.path:
    sys.path.insert(0, str(RUNTIME_DIR))

from engine.api import classify_request_tier
from core.model_routing import select_model_route
from engine.inference.llm import _route_model


def test_classify_request_tier_short(monkeypatch) -> None:
    monkeypatch.setenv("WAVEFIELD_ROUTE_MIN_TOKENS", "100")
    out = classify_request_tier(prompt="short prompt")
    assert out["tier"] == "short"
    assert out["estimated_tokens"] < out["threshold"]


def test_classify_request_tier_long(monkeypatch) -> None:
    monkeypatch.setenv("WAVEFIELD_ROUTE_MIN_TOKENS", "10")
    out = classify_request_tier(prompt="x" * 200)
    assert out["tier"] == "long"
    assert out["estimated_tokens"] >= out["threshold"]


def test_route_model_short_keeps_default(monkeypatch) -> None:
    monkeypatch.setenv("WAVEFIELD_ENABLED", "1")
    monkeypatch.setenv("WAVEFIELD_ROUTE_MIN_TOKENS", "500")
    monkeypatch.setenv("WAVEFIELD_MODEL", "wave-field-model")
    decision = _route_model(prompt="tiny", context=None, requested_model="baseline-model")
    assert decision.tier == "short"
    assert decision.chosen_model == "baseline-model"


def test_route_model_long_uses_wavefield_when_enabled(monkeypatch) -> None:
    monkeypatch.setenv("WAVEFIELD_ENABLED", "1")
    monkeypatch.setenv("WAVEFIELD_ROUTE_MIN_TOKENS", "10")
    monkeypatch.setenv("WAVEFIELD_MODEL", "wave-field-model")
    decision = _route_model(prompt="x" * 400, context=None, requested_model="baseline-model")
    assert decision.tier == "long"
    assert decision.chosen_model == "wave-field-model"


def test_route_model_long_without_wavefield_stays_default(monkeypatch) -> None:
    monkeypatch.setenv("WAVEFIELD_ENABLED", "0")
    monkeypatch.setenv("WAVEFIELD_ROUTE_MIN_TOKENS", "10")
    monkeypatch.setenv("WAVEFIELD_MODEL", "wave-field-model")
    decision = _route_model(prompt="x" * 400, context=None, requested_model="baseline-model")
    assert decision.tier == "short"
    assert decision.chosen_model == "baseline-model"


def test_select_model_route_respects_explicit_route(monkeypatch) -> None:
    monkeypatch.setenv("WAVEFIELD_ENABLED", "1")
    monkeypatch.setenv("WAVEFIELD_ROUTE_MIN_TOKENS", "10")
    out = select_model_route(prompt="x" * 400, requested_route="anthropic")
    assert out.model_route == "anthropic"
    assert out.force_model is None
    assert out.tier == "long"


def test_select_model_route_auto_long_uses_wavefield(monkeypatch) -> None:
    monkeypatch.setenv("WAVEFIELD_ENABLED", "1")
    monkeypatch.setenv("WAVEFIELD_ROUTE_MIN_TOKENS", "10")
    monkeypatch.setenv("WAVEFIELD_MODEL", "wave-field-model")
    out = select_model_route(prompt="x" * 400)
    assert out.model_route == "wavefield"
    assert out.force_model == "wave-field-model"
    assert out.tier == "long"


def test_select_model_route_shadow_mode_keeps_primary(monkeypatch) -> None:
    monkeypatch.setenv("WAVEFIELD_ENABLED", "1")
    monkeypatch.setenv("WAVEFIELD_ROLLOUT_MODE", "shadow")
    monkeypatch.setenv("WAVEFIELD_ROUTE_MIN_TOKENS", "10")
    out = select_model_route(prompt="x" * 400)
    assert out.model_route == "auto"
    assert out.shadow_wavefield is True


def test_select_model_route_canary_zero_percent_disables_wavefield(monkeypatch) -> None:
    monkeypatch.setenv("WAVEFIELD_ENABLED", "1")
    monkeypatch.setenv("WAVEFIELD_ROLLOUT_MODE", "canary")
    monkeypatch.setenv("WAVEFIELD_CANARY_PERCENT", "0")
    monkeypatch.setenv("WAVEFIELD_ROUTE_MIN_TOKENS", "10")
    out = select_model_route(prompt="x" * 400)
    assert out.model_route == "auto"
    assert out.shadow_wavefield is False


def test_select_model_route_off_mode_disables_wavefield(monkeypatch) -> None:
    monkeypatch.setenv("WAVEFIELD_ENABLED", "1")
    monkeypatch.setenv("WAVEFIELD_ROLLOUT_MODE", "off")
    monkeypatch.setenv("WAVEFIELD_ROUTE_MIN_TOKENS", "10")
    out = select_model_route(prompt="x" * 400)
    assert out.model_route == "auto"
