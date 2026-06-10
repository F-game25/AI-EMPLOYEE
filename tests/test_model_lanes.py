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


# ── Execution targets: local (free) vs external API / rented remote (paid) ────

def test_default_target_is_free_local_no_approval():
    r = ml.resolve_target(ml.TIER_CODE)
    assert r["target"] == ml.TARGET_LOCAL
    assert r["requires_approval"] is False
    assert r["requires_payment"] is False


def test_external_api_not_used_unless_paid_allowed():
    r = ml.resolve_target(ml.TIER_CODE, prefer=ml.TARGET_EXTERNAL_API, allow_paid=False)
    assert r["target"] == ml.TARGET_LOCAL  # falls back, never silently pays


def test_external_api_when_allowed_is_paid_and_needs_approval():
    r = ml.resolve_target(ml.TIER_CODE, prefer=ml.TARGET_EXTERNAL_API, allow_paid=True)
    assert r["target"] == ml.TARGET_EXTERNAL_API
    assert r["provider"] in ("anthropic", "openai")
    assert r["requires_approval"] is True and r["requires_payment"] is True


def test_rented_remote_when_allowed_is_paid_and_needs_approval():
    r = ml.resolve_target(ml.TIER_DEEP, prefer=ml.TARGET_RENTED_REMOTE, allow_paid=True)
    assert r["target"] == ml.TARGET_RENTED_REMOTE
    assert r["requires_approval"] is True and r["requires_payment"] is True
    assert r["model"]  # a concrete bigger model to run on the rented GPU


def test_upgrade_options_offers_both_paid_paths():
    opts = ml.upgrade_options(ml.TIER_CODE)
    targets = {o["target"] for o in opts}
    assert targets == {ml.TARGET_EXTERNAL_API, ml.TARGET_RENTED_REMOTE}
    assert all(o["requires_approval"] and o["requires_payment"] for o in opts)


# ── DeepSeek / OpenAI-compatible external provider selection ──────────────────

def test_default_external_provider_is_anthropic_for_code():
    """No COMPANION_EXTERNAL_PROVIDER → CODE external target stays anthropic."""
    prior = os.environ.pop("COMPANION_EXTERNAL_PROVIDER", None)
    try:
        provider, model = ml.external_api_model_for(ml.TIER_CODE)
        assert provider == "anthropic"
        assert model  # concrete claude coder model
    finally:
        if prior is not None:
            os.environ["COMPANION_EXTERNAL_PROVIDER"] = prior


def test_companion_external_provider_deepseek_routes_code_to_deepseek_coder():
    """COMPANION_EXTERNAL_PROVIDER=deepseek → CODE external provider is deepseek + a coder model."""
    prior = os.environ.get("COMPANION_EXTERNAL_PROVIDER")
    os.environ["COMPANION_EXTERNAL_PROVIDER"] = "deepseek"
    try:
        provider, model = ml.external_api_model_for(ml.TIER_CODE)
        assert provider == "deepseek"
        assert "coder" in model.lower()
        # And the full resolve_target path agrees (paid + approval unchanged).
        r = ml.resolve_target(ml.TIER_CODE, prefer=ml.TARGET_EXTERNAL_API, allow_paid=True)
        assert r["target"] == ml.TARGET_EXTERNAL_API
        assert r["provider"] == "deepseek"
        assert "coder" in r["model"].lower()
        assert r["requires_approval"] is True and r["requires_payment"] is True
    finally:
        if prior is None:
            os.environ.pop("COMPANION_EXTERNAL_PROVIDER", None)
        else:
            os.environ["COMPANION_EXTERNAL_PROVIDER"] = prior


def test_companion_external_provider_deepseek_routes_deep_and_heavy_to_reasoner():
    """DEEP/HEAVY under deepseek → deepseek-reasoner (not the coder)."""
    prior = os.environ.get("COMPANION_EXTERNAL_PROVIDER")
    os.environ["COMPANION_EXTERNAL_PROVIDER"] = "deepseek"
    try:
        for tier in (ml.TIER_DEEP, ml.TIER_HEAVY):
            provider, model = ml.external_api_model_for(tier)
            assert provider == "deepseek"
            assert "reasoner" in model.lower()
    finally:
        if prior is None:
            os.environ.pop("COMPANION_EXTERNAL_PROVIDER", None)
        else:
            os.environ["COMPANION_EXTERNAL_PROVIDER"] = prior


def test_explicit_provider_arg_overrides_env():
    """external_api_model_for(provider=...) overrides COMPANION_EXTERNAL_PROVIDER."""
    prior = os.environ.get("COMPANION_EXTERNAL_PROVIDER")
    os.environ["COMPANION_EXTERNAL_PROVIDER"] = "anthropic"
    try:
        provider, model = ml.external_api_model_for(ml.TIER_CODE, provider="deepseek")
        assert provider == "deepseek" and "coder" in model.lower()
    finally:
        if prior is None:
            os.environ.pop("COMPANION_EXTERNAL_PROVIDER", None)
        else:
            os.environ["COMPANION_EXTERNAL_PROVIDER"] = prior


def test_deepseek_code_and_reasoner_models_are_env_overridable():
    prior = os.environ.get("COMPANION_EXTERNAL_PROVIDER")
    prior_code = os.environ.get("DEEPSEEK_CODE_MODEL")
    prior_reasoner = os.environ.get("DEEPSEEK_REASONER_MODEL")
    os.environ["COMPANION_EXTERNAL_PROVIDER"] = "deepseek"
    os.environ["DEEPSEEK_CODE_MODEL"] = "deepseek-coder-v2"
    os.environ["DEEPSEEK_REASONER_MODEL"] = "deepseek-r1"
    try:
        assert ml.external_api_model_for(ml.TIER_CODE) == ("deepseek", "deepseek-coder-v2")
        assert ml.external_api_model_for(ml.TIER_DEEP) == ("deepseek", "deepseek-r1")
    finally:
        for k, v in (
            ("COMPANION_EXTERNAL_PROVIDER", prior),
            ("DEEPSEEK_CODE_MODEL", prior_code),
            ("DEEPSEEK_REASONER_MODEL", prior_reasoner),
        ):
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def test_provider_key_present_handles_deepseek():
    prior = os.environ.get("DEEPSEEK_API_KEY")
    try:
        os.environ.pop("DEEPSEEK_API_KEY", None)
        assert ml._provider_key_present("deepseek") is False
        os.environ["DEEPSEEK_API_KEY"] = "sk-test-deepseek"
        assert ml._provider_key_present("deepseek") is True
    finally:
        if prior is None:
            os.environ.pop("DEEPSEEK_API_KEY", None)
        else:
            os.environ["DEEPSEEK_API_KEY"] = prior


def test_normal_and_fast_external_stay_openai_under_deepseek():
    """The companion switch governs only CODE/DEEP/HEAVY; NORMAL/FAST stay OpenAI."""
    prior = os.environ.get("COMPANION_EXTERNAL_PROVIDER")
    os.environ["COMPANION_EXTERNAL_PROVIDER"] = "deepseek"
    try:
        assert ml.external_api_model_for(ml.TIER_NORMAL)[0] == "openai"
        assert ml.external_api_model_for(ml.TIER_FAST)[0] == "openai"
    finally:
        if prior is None:
            os.environ.pop("COMPANION_EXTERNAL_PROVIDER", None)
        else:
            os.environ["COMPANION_EXTERNAL_PROVIDER"] = prior
