"""Phase A5 — role resolver + hard PC-control gate.

The execution_reasoning role only counts a model as available when it is actually
INSTALLED and meets the quant floor; otherwise PC-control must be blocked with an
install suggestion (never run on a weak/absent model).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "runtime"))

from core import model_lanes as ml  # noqa: E402
from core import model_role_resolver as rr  # noqa: E402


def _force_vram(monkeypatch, mb):
    for fn in ("_live_free_vram_mb", "_usable_vram_mb"):
        monkeypatch.setattr(ml, fn, lambda: mb, raising=False)


def test_execution_blocked_when_nothing_installed(monkeypatch):
    monkeypatch.setattr(rr, "_installed_models", lambda: set())
    out = rr.execution_reasoning_ready()
    assert out["available"] is False
    assert out["install_suggestion"] == "qwythos:q4"  # first preferred (primary system model)
    assert out["model"] is None


def test_execution_available_when_capable_model_installed(monkeypatch):
    # qwen3.5 is in execution_reasoning's preferred list and is a real local reasoner.
    monkeypatch.setattr(rr, "_installed_models", lambda: {"qwen3.5"})
    _force_vram(monkeypatch, 20000)
    out = rr.execution_reasoning_ready()
    assert out["available"] is True and out["installed"] is True
    assert out["model"] == "qwen3.5"


def test_execution_offloads_but_available_when_vram_tight(monkeypatch):
    monkeypatch.setattr(rr, "_installed_models", lambda: {"qwen3.5"})
    _force_vram(monkeypatch, 1000)  # too little to fully fit
    out = rr.execution_reasoning_ready()
    assert out["available"] is True            # installed → usable (even if it offloads)
    assert out["fits"] is False and out["offload_layers"] >= 0


def test_coding_never_resolves_to_a_non_coder(monkeypatch):
    monkeypatch.setattr(rr, "_installed_models", lambda: {"qwen2.5-coder:14b", "gemma3"})
    _force_vram(monkeypatch, 20000)
    out = rr.resolve_role("coding")
    assert out["available"] and "coder" in out["model"]


def test_quant_floor_respected(monkeypatch):
    # review_safety floor is q5_K_M; gemma3:12b-it-qat (q4_0 only, and in its
    # preferred list) must NOT satisfy it.
    monkeypatch.setattr(rr, "_installed_models", lambda: {"gemma3:12b-it-qat"})
    _force_vram(monkeypatch, 20000)
    out = rr.resolve_role("review_safety")
    assert out["available"] is False  # q4_0 < q5_K_M floor


def test_specific_tag_not_satisfied_by_different_tag(monkeypatch):
    # gemma3:latest installed must NOT count as gemma3:4b-it-qat (a different tag).
    monkeypatch.setattr(rr, "_installed_models", lambda: {"gemma3:latest", "gemma3"})
    _force_vram(monkeypatch, 20000)
    out = rr.resolve_role("execution_reasoning")
    # gemma3:4b-it-qat / gemma4 / gemma3:12b-it-qat not installed, qwen3.5 not installed
    assert out["available"] is False


def test_broker_imports_with_gate():
    # The broker must import cleanly with the new execution-model gate wired in.
    from companion.execution_broker import get_execution_broker
    assert get_execution_broker() is not None
