"""Content-creation media base (vendored Open-Generative-AI + MuAPI client).

Offline — no network. Verifies the catalog loads from the vendored base, the
MuAPI submit→poll flow + url normalization (mocked HTTP), and honest failure
when no API key is set.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "runtime"))

from content import media_models as mm  # noqa: E402
from content import muapi_client as mc  # noqa: E402


# ── Catalog from the vendored base ────────────────────────────────────────────

def test_catalog_loads_from_vendor():
    models = mm.list_models()
    assert len(models) >= 40  # vendored Open-Generative-AI catalog
    sample = mm.get_model("flux-dev")
    assert sample and sample["id"] == "flux-dev"


def test_endpoint_mapping_from_models_js():
    # models.js maps flux-dev -> flux-dev-image (endpoint differs from id).
    assert mm.endpoint_for("flux-dev") == "flux-dev-image"
    # Unknown id falls back to itself (never raises).
    assert mm.endpoint_for("totally-unknown-xyz") == "totally-unknown-xyz"


# ── Honest failure with no key ────────────────────────────────────────────────

def test_generate_requires_api_key(monkeypatch):
    monkeypatch.delenv("MUAPI_API_KEY", raising=False)
    monkeypatch.delenv("MUAPI_KEY", raising=False)
    with pytest.raises(mc.MuapiError):
        mc.generate("flux-dev", "a red fox")


def test_content_factory_cloud_media_honest_without_key(monkeypatch):
    # Cloud (MuAPI) is opt-in via provider="cloud"; the default is local/offline.
    monkeypatch.delenv("MUAPI_API_KEY", raising=False)
    monkeypatch.delenv("MUAPI_KEY", raising=False)
    from content.content_factory import get_content_factory
    out = get_content_factory().generate_media("a red fox", model="flux-dev", provider="cloud")
    assert out["ok"] is False and out["provider"] == "cloud" and "MUAPI_API_KEY" in out["error"]


# ── Submit → poll → url (mocked HTTP) ─────────────────────────────────────────

def test_submit_poll_and_url_extraction(monkeypatch):
    monkeypatch.setenv("MUAPI_API_KEY", "test-key")
    calls = {"n": 0}

    def fake_request(url, key, payload, timeout):
        assert key == "test-key"
        if payload is not None:                       # submit POST
            assert url.endswith("/api/v1/flux-dev-image")  # endpoint-mapped
            assert payload["prompt"] == "a red fox"
            return {"request_id": "req-123"}
        calls["n"] += 1                                # poll GET
        if calls["n"] < 2:
            return {"status": "processing"}
        return {"status": "completed", "outputs": ["https://cdn.muapi.ai/out.png"]}

    monkeypatch.setattr(mc, "_request", fake_request)
    out = mc.generate("flux-dev", "a red fox", interval=0)
    assert out["url"] == "https://cdn.muapi.ai/out.png"
    assert out["request_id"] == "req-123" and out["status"] == "completed"


def test_failed_generation_raises(monkeypatch):
    monkeypatch.setenv("MUAPI_API_KEY", "test-key")

    def fake_request(url, key, payload, timeout):
        if payload is not None:
            return {"request_id": "r1"}
        return {"status": "failed", "error": "content policy"}

    monkeypatch.setattr(mc, "_request", fake_request)
    with pytest.raises(mc.MuapiError):
        mc.generate("flux-dev", "x", interval=0)


# ── Tool registration ─────────────────────────────────────────────────────────

def test_media_generate_tool_registered():
    from tools.registry import get_tool_registry
    assert get_tool_registry().get("media_generate") is not None
