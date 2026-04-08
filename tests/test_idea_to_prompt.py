"""Unit tests for runtime/agents/idea-to-prompt/idea_to_prompt.py

Covers:
  - convert_idea() — empty input, fallback expansion, AI path, title parsing
  - _parse_ai_response() — correct title extraction and prompt body
  - _fallback_expand() — keyword matching and default fallback
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Add the idea-to-prompt module to sys.path
_IDEA_DIR = Path(__file__).parent.parent / "runtime" / "agents" / "idea-to-prompt"
if str(_IDEA_DIR) not in sys.path:
    sys.path.insert(0, str(_IDEA_DIR))

import idea_to_prompt as itp


# ══════════════════════════════════════════════════════════════════════════════
# _parse_ai_response
# ══════════════════════════════════════════════════════════════════════════════

class TestParseAiResponse:
    def test_extracts_title(self):
        raw = "Do something great.\nStep 1: research.\nTITLE: My Great Task"
        prompt, title = itp._parse_ai_response(raw, "fallback idea")
        assert title == "My Great Task"
        assert "TITLE:" not in prompt

    def test_title_prefix_case_insensitive(self):
        raw = "Some steps here.\ntitle: Lower Case Title"
        _, title = itp._parse_ai_response(raw, "fallback")
        assert title == "Lower Case Title"

    def test_fallback_title_when_missing(self):
        raw = "Steps without a title line."
        _, title = itp._parse_ai_response(raw, "my idea text")
        assert title == "my idea text"

    def test_prompt_body_strips_title_line(self):
        raw = "Step 1.\nStep 2.\nTITLE: Test"
        prompt, _ = itp._parse_ai_response(raw, "idea")
        assert "TITLE:" not in prompt
        assert "Step 1." in prompt

    def test_empty_raw_returns_original_title(self):
        prompt, title = itp._parse_ai_response("", "original")
        assert title == "original"
        assert prompt == ""


# ══════════════════════════════════════════════════════════════════════════════
# _fallback_expand
# ══════════════════════════════════════════════════════════════════════════════

class TestFallbackExpand:
    def test_ecommerce_keyword_matches(self):
        prompt, title = itp._fallback_expand("I want to build an online store")
        assert "e-commerce" in prompt.lower() or "store" in prompt.lower() or "product" in prompt.lower()

    def test_startup_keyword_matches(self):
        prompt, _ = itp._fallback_expand("Help me launch a new startup company")
        assert "business" in prompt.lower() or "company" in prompt.lower() or "launch" in prompt.lower()

    def test_app_keyword_matches(self):
        prompt, _ = itp._fallback_expand("build an app for fitness tracking")
        assert "software" in prompt.lower() or "app" in prompt.lower() or "develop" in prompt.lower() or "feature" in prompt.lower()

    def test_marketing_keyword_matches(self):
        prompt, _ = itp._fallback_expand("grow my social media brand")
        assert "content" in prompt.lower() or "audience" in prompt.lower() or "brand" in prompt.lower()

    def test_default_fallback_for_unknown_topic(self):
        prompt, title = itp._fallback_expand("fix my unicorn collection")
        assert "Goal:" in prompt
        assert "action plan" in prompt.lower()
        assert title == "fix my unicorn collection"

    def test_title_truncated_at_60_chars(self):
        long_idea = "a" * 100
        _, title = itp._fallback_expand(long_idea)
        assert len(title) <= 60


# ══════════════════════════════════════════════════════════════════════════════
# convert_idea — empty input
# ══════════════════════════════════════════════════════════════════════════════

class TestConvertIdeaEmptyInput:
    def test_empty_string_returns_not_ok(self):
        result = itp.convert_idea("")
        assert result["ok"] is False
        assert "empty" in result["error"].lower()

    def test_whitespace_only_returns_not_ok(self):
        result = itp.convert_idea("   ")
        assert result["ok"] is False


# ══════════════════════════════════════════════════════════════════════════════
# convert_idea — fallback path (no AI router)
# ══════════════════════════════════════════════════════════════════════════════

class TestConvertIdeaFallback:
    def test_returns_ok_true(self, monkeypatch):
        monkeypatch.setattr(itp, "_AI_AVAILABLE", False)
        result = itp.convert_idea("I want to start a business")
        assert result["ok"] is True

    def test_returns_prompt_string(self, monkeypatch):
        monkeypatch.setattr(itp, "_AI_AVAILABLE", False)
        result = itp.convert_idea("build a website")
        assert isinstance(result["prompt"], str)
        assert len(result["prompt"]) > 20

    def test_provider_is_fallback(self, monkeypatch):
        monkeypatch.setattr(itp, "_AI_AVAILABLE", False)
        result = itp.convert_idea("some random idea")
        assert result["provider"] == "fallback"

    def test_original_preserved(self, monkeypatch):
        monkeypatch.setattr(itp, "_AI_AVAILABLE", False)
        idea = "turn my hobby into a business"
        result = itp.convert_idea(idea)
        assert result["original"] == idea

    def test_title_is_string(self, monkeypatch):
        monkeypatch.setattr(itp, "_AI_AVAILABLE", False)
        result = itp.convert_idea("launch a podcast")
        assert isinstance(result["title"], str)
        assert len(result["title"]) > 0


# ══════════════════════════════════════════════════════════════════════════════
# convert_idea — AI path (mocked)
# ══════════════════════════════════════════════════════════════════════════════

class TestConvertIdeaAIPath:
    def _mock_query(self, *args, **kwargs):
        return {
            "content": "1. Research the market.\n2. Build the product.\nTITLE: AI Generated Task",
            "provider": "ollama",
        }

    def test_uses_ai_result(self, monkeypatch):
        monkeypatch.setattr(itp, "_AI_AVAILABLE", True)
        monkeypatch.setattr(itp, "_query_ai", self._mock_query)
        result = itp.convert_idea("great idea here")
        assert result["ok"] is True
        assert "Research the market" in result["prompt"]
        assert result["title"] == "AI Generated Task"
        assert result["provider"] == "ollama"

    def test_falls_back_on_ai_exception(self, monkeypatch):
        monkeypatch.setattr(itp, "_AI_AVAILABLE", True)
        monkeypatch.setattr(itp, "_query_ai", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
        result = itp.convert_idea("another idea")
        assert result["ok"] is True
        assert result["provider"] == "fallback"

    def test_falls_back_when_ai_returns_empty(self, monkeypatch):
        monkeypatch.setattr(itp, "_AI_AVAILABLE", True)
        monkeypatch.setattr(itp, "_query_ai", lambda *a, **k: {"content": "  ", "provider": "ollama"})
        result = itp.convert_idea("empty ai response idea")
        assert result["ok"] is True
        assert len(result["prompt"]) > 10
