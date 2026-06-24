"""Phase 2 — concurrent + independent multi-provider routing, egress-guarded."""

import asyncio
import sys
from pathlib import Path

import pytest

_RUNTIME = Path(__file__).resolve().parents[1] / "runtime"
sys.path.insert(0, str(_RUNTIME))
sys.path.insert(0, str(_RUNTIME / "core"))

import llm_provider_router as lpr  # noqa: E402
from core import egress_guard as eg  # noqa: E402


class FakeClient:
    """Records the messages it was asked to send; can be set to fail."""
    def __init__(self, fail=False, tag="ok"):
        self.fail = fail
        self.tag = tag
        self.seen = None

    async def generate(self, messages, temperature=0.7, max_tokens=2048):
        self.seen = messages
        if self.fail:
            raise Exception("simulated provider failure")
        return f"{self.tag}-reply"


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    # Hermetic: clear EVERY provider key (incl. NVIDIA) so local/CI env can't
    # configure a real client, and disable graceful pipeline fallbacks.
    for k in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "OPENROUTER_API_KEY",
              "NVIDIA_API_KEY", "OLLAMA_ENDPOINT", "EGRESS_GUARD"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("STRICT_PIPELINE", "1")
    eg.reload()
    lpr.reset_router()
    yield
    eg.reload()
    lpr.reset_router()


def _router_with(**clients):
    r = lpr.LLMProviderRouter()
    r.anthropic_client = clients.get("anthropic")
    r.openai_client = clients.get("openai")
    r.openrouter_client = clients.get("openrouter")
    r.nvidia_client = clients.get("nvidia")
    r.ollama_client = clients.get("ollama")
    return r


def test_openai_and_nvidia_providers_are_wired():
    r = _router_with(openai=FakeClient(tag="openai"), nvidia=FakeClient(tag="nvidia"))
    assert r._get_client("openai") is not None
    assert r._get_client("nvidia") is not None


def test_nvidia_runs_concurrently_and_is_egress_guarded():
    nv = FakeClient(tag="nvidia")
    r = _router_with(nvidia=nv, anthropic=FakeClient(tag="anthropic"))
    out = asyncio.run(r.generate_concurrent([{"role": "user", "content": "deploy agent"}],
                                            providers=["nvidia", "anthropic"]))
    assert out["nvidia"] == {"ok": True, "text": "nvidia-reply"}
    # secret must be blocked before reaching NVIDIA cloud too
    nv2 = FakeClient(tag="nvidia")
    r2 = _router_with(nvidia=nv2)
    out2 = asyncio.run(r2.generate_concurrent([{"role": "user", "content": "key sk-ant-AAAAAAAAAAAAAAAAAAAAAAAA"}],
                                              providers=["nvidia"]))
    assert out2["nvidia"]["ok"] is False
    assert nv2.seen is None


def test_concurrent_runs_all_providers_independently():
    a, o, fail = FakeClient(tag="anthropic"), FakeClient(tag="openai"), FakeClient(fail=True)
    r = _router_with(anthropic=a, openai=o, openrouter=fail)
    out = asyncio.run(r.generate_concurrent([{"role": "user", "content": "hi"}],
                                            providers=["anthropic", "openai", "openrouter"]))
    assert out["anthropic"] == {"ok": True, "text": "anthropic-reply"}
    assert out["openai"] == {"ok": True, "text": "openai-reply"}
    # one provider failing does NOT affect the others
    assert out["openrouter"]["ok"] is False


def test_concurrent_skips_unconfigured_providers():
    r = _router_with(anthropic=FakeClient(tag="anthropic"))
    out = asyncio.run(r.generate_concurrent([{"role": "user", "content": "hi"}],
                                            providers=["anthropic", "openai"]))
    assert set(out.keys()) == {"anthropic"}


def test_secret_is_blocked_before_reaching_external_provider():
    o = FakeClient(tag="openai")
    r = _router_with(openai=o)
    msgs = [{"role": "user", "content": "my key is sk-ant-AAAAAAAAAAAAAAAAAAAAAAAA deploy it"}]
    out = asyncio.run(r.generate_concurrent(msgs, providers=["openai"]))
    assert out["openai"]["ok"] is False
    assert "egress blocked" in out["openai"]["error"]
    assert o.seen is None, "secret must never reach the external client"


def test_pii_is_redacted_before_external_provider():
    o = FakeClient(tag="openai")
    r = _router_with(openai=o)
    msgs = [{"role": "user", "content": "email jane.doe@example.com the report"}]
    asyncio.run(r.generate_concurrent(msgs, providers=["openai"]))
    assert o.seen is not None
    assert "jane.doe@example.com" not in str(o.seen), "PII must be redacted before egress"


def test_local_provider_not_redacted():
    ol = FakeClient(tag="ollama")
    r = _router_with(ollama=ol)
    msgs = [{"role": "user", "content": "email jane.doe@example.com the report"}]
    asyncio.run(r.generate_concurrent(msgs, providers=["ollama"]))
    # local stays on-box → no redaction applied
    assert "jane.doe@example.com" in str(ol.seen)


def test_generate_falls_back_and_is_guarded():
    r = _router_with(anthropic=FakeClient(fail=True, tag="anthropic"), openai=FakeClient(tag="openai"))
    r.primary_provider = "anthropic"
    out = asyncio.run(r.generate([{"role": "user", "content": "hello"}]))
    assert out == "openai-reply"
