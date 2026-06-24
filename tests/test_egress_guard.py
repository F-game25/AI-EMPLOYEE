"""Egress guard (Python) — never-leak gate for the external LLM provider path."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "runtime"))

from core import egress_guard as eg  # noqa: E402


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    monkeypatch.delenv("EGRESS_GUARD", raising=False)
    eg.reload()
    yield
    eg.reload()


def test_classify_levels():
    assert eg.classify({"env": "OPENAI_API_KEY=sk-abcdefghijklmnopqrstuvwx0123"}) == "secret"
    assert eg.classify("reach me at jane.doe@example.com") == "pii"
    assert eg.classify("/home/lars/.ai-employee/state/x") == "internal"
    assert eg.classify("summarize the quarterly trend") == "public"


def test_secret_blocked_to_every_remote_tier():
    for tier in ("peer_trusted", "rented_trusted", "external_api"):
        d = eg.guard({"k": "sk-ant-AAAAAAAAAAAAAAAAAAAAAAAA"}, tier)
        assert d["action"] == "block"
        assert d["payload"] is None


def test_pii_redacted_email_actually_gone():
    r = eg.guard("contact jane.doe@example.com about it", "external_api")
    assert r["action"] == "redact"
    assert "jane.doe@example.com" not in str(r["payload"])


def test_public_allowed_local_allows_everything():
    assert eg.guard("hello world", "external_api")["action"] == "allow"
    assert eg.guard({"k": "sk-ant-AAAAAAAAAAAAAAAAAAAAAAAA"}, "local")["action"] == "allow"


def test_unknown_tier_blocked_deny_by_default():
    assert eg.guard("x", "mystery")["action"] == "block"


def test_oversize_blocked():
    big = {"blob": "x" * (3 * 1024 * 1024)}
    assert eg.guard(big, "external_api")["action"] == "block"


def test_provider_tier_mapping():
    assert eg.tier_for_provider("ollama") == "local"
    assert eg.tier_for_provider("openai") == "external_api"
    assert eg.tier_for_provider("anthropic") == "external_api"
    assert eg.tier_for_provider("openrouter") == "external_api"


def test_guard_for_provider_blocks_secret_to_openai():
    d = eg.guard_for_provider({"prompt": "key is sk-ant-AAAAAAAAAAAAAAAAAAAAAAAA"}, "openai")
    assert d["action"] == "block"


def test_redact_strips_prototype_pollution_keys():
    out = eg.redact({"__proto__": {"x": 1}, "constructor": {"y": 2}, "ok": "fine"})
    assert "__proto__" not in out and "constructor" not in out
    assert out["ok"] == "fine"


def test_kill_switch_passes_through():
    import os
    os.environ["EGRESS_GUARD"] = "0"
    eg.reload()
    try:
        d = eg.guard({"k": "sk-ant-AAAAAAAAAAAAAAAAAAAAAAAA"}, "external_api")
        assert d["action"] == "allow"
    finally:
        del os.environ["EGRESS_GUARD"]
        eg.reload()


def test_never_raises_on_garbage():
    assert eg.guard(object(), "external_api")["action"] in ("allow", "redact", "block")
    assert eg.classify(object()) in ("public", "internal", "pii", "secret")
