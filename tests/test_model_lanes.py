"""Tests for hardware-dynamic model tiers (runtime/core/model_lanes.py)."""
import os
import sys
from pathlib import Path

_RUNTIME = Path(__file__).resolve().parents[1] / "runtime"
if str(_RUNTIME) not in sys.path:
    sys.path.insert(0, str(_RUNTIME))

from core import model_lanes as ml  # noqa: E402

_CODER_PREFIX = "qwen2.5-coder"


def test_all_tiers_resolve_to_nonempty_model():
    models = ml.tier_models()
    assert set(models.keys()) == set(ml.ALL_TIERS)
    for tier, model in models.items():
        assert isinstance(model, str) and model, f"{tier} resolved empty"


def test_code_tier_is_always_a_coder_model():
    """CODE must never degrade to a general model like llama — always a coder."""
    model = ml.resolve_tier(ml.TIER_CODE)
    assert model.startswith(_CODER_PREFIX), f"CODE resolved to non-coder: {model}"
    # And via task routing
    assert ml.resolve_for_task("coding").startswith(_CODER_PREFIX)
    assert ml.resolve_for_task("review").startswith(_CODER_PREFIX)


def test_size_tiers_never_resolve_to_a_coder_model():
    """FAST/NORMAL/HEAVY/DEEP are general tiers — should not pick a coder model."""
    for tier in ml.SIZE_TIERS:
        m = ml.resolve_tier(tier)
        assert not m.startswith(_CODER_PREFIX), f"{tier} wrongly picked coder: {m}"


def test_task_to_tier_mapping():
    assert ml.tier_for_task("coding") == ml.TIER_CODE
    assert ml.tier_for_task("research") == ml.TIER_DEEP
    assert ml.tier_for_task("analysis") == ml.TIER_HEAVY
    assert ml.tier_for_task("chat") == ml.TIER_NORMAL
    assert ml.tier_for_task("routing") == ml.TIER_FAST
    assert ml.tier_for_task("something-weird") == ml.TIER_NORMAL
    assert ml.tier_for_task(None) == ml.TIER_NORMAL


def test_env_override_wins_for_any_tier():
    os.environ["MODEL_TIER_HEAVY"] = "my-custom-heavy:1b"
    try:
        assert ml.resolve_tier(ml.TIER_HEAVY) == "my-custom-heavy:1b"
    finally:
        del os.environ["MODEL_TIER_HEAVY"]


def test_hot_tier_models_deduped_nonempty():
    hot = ml.hot_tier_models()
    assert hot
    assert len(hot) == len(set(hot))


def test_unknown_tier_falls_back_to_normal():
    assert ml.resolve_tier("NONSENSE") == ml.resolve_tier(ml.TIER_NORMAL)


def test_tiers_are_named_fast_normal_heavy_deep():
    """Lock the required tier names."""
    assert ml.SIZE_TIERS == ("FAST", "NORMAL", "HEAVY", "DEEP_THINKING")
