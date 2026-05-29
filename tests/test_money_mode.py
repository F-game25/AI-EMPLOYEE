"""Integration tests for MoneyMode pipelines.

Covers content_publish_track, data_scrape_filter_store, and
outreach_response_conversion with full STATE_DIR isolation and
mocked HTTP calls — no LLM or network access required.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "runtime"))


def _approved_gate_mock():
    """Return a mock HITL gate that always approves (for pipeline unit tests)."""
    gate_instance = MagicMock()
    gate_instance.require_approval.return_value = {"approved": True, "request_id": "test-gate-001"}
    mock = MagicMock(return_value=gate_instance)
    return mock


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_urlopen_mock(html: bytes = b"<html><body>test content about testing</body></html>"):
    """Return a context-manager mock for urllib.request.urlopen."""
    resp = MagicMock()
    resp.read.return_value = html
    resp.info.return_value = MagicMock(**{"get.return_value": "text/html"})
    cm = MagicMock()
    cm.__enter__ = MagicMock(return_value=resp)
    cm.__exit__ = MagicMock(return_value=False)
    return cm


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def isolate_state(tmp_path, monkeypatch):
    """Redirect STATE_DIR to a fresh tmp dir and reset MoneyMode singleton."""
    monkeypatch.setenv("STATE_DIR", str(tmp_path))
    # Reset the module-level singleton so each test gets a clean instance.
    import importlib
    import core.money_mode as mm_mod
    mm_mod._instance = None
    yield tmp_path
    mm_mod._instance = None


@pytest.fixture()
def money_mode(isolate_state):
    from core.money_mode import MoneyMode
    return MoneyMode()


# ── content_publish_track ─────────────────────────────────────────────────────

class TestContentPublishTrack:

    def test_returns_ok_and_nonempty_artifact(self, money_mode):
        result = money_mode.content_publish_track("ecommerce", "blog", "article")
        assert result["ok"] is True
        assert isinstance(result["artifact"], str) and result["artifact"]

    def test_llm_offline_returns_template_status(self, money_mode, monkeypatch):
        # _llm_generate returns None when LLM is unavailable
        monkeypatch.setattr(
            "core.money_mode.MoneyMode._llm_generate",
            staticmethod(lambda prompt, system: None),
        )
        result = money_mode.content_publish_track("ecommerce", "blog", "article")
        assert result["status"] == "template"

    def test_word_count_is_positive(self, money_mode, monkeypatch):
        monkeypatch.setattr(
            "core.money_mode.MoneyMode._llm_generate",
            staticmethod(lambda prompt, system: None),
        )
        result = money_mode.content_publish_track("ecommerce", "blog", "article")
        assert result["word_count"] > 0

    def test_artifact_file_is_written_to_disk(self, money_mode, monkeypatch, isolate_state):
        monkeypatch.setattr(
            "core.money_mode.MoneyMode._llm_generate",
            staticmethod(lambda prompt, system: None),
        )
        result = money_mode.content_publish_track("ecommerce", "blog", "article")
        artifact = Path(result["artifact"])
        assert artifact.exists()
        assert artifact.stat().st_size > 0

    def test_content_log_updated(self, money_mode, monkeypatch, isolate_state):
        monkeypatch.setattr(
            "core.money_mode.MoneyMode._llm_generate",
            staticmethod(lambda prompt, system: None),
        )
        money_mode.content_publish_track("ecommerce", "blog", "article")
        log_path = isolate_state / "content_log.json"
        assert log_path.exists()
        entries = json.loads(log_path.read_text())
        assert len(entries) == 1
        assert entries[0]["topic"] == "ecommerce"

    def test_llm_online_returns_draft_status(self, money_mode, monkeypatch):
        monkeypatch.setattr(
            "core.money_mode.MoneyMode._llm_generate",
            staticmethod(lambda prompt, system: "# Real LLM content\n\nThis is generated."),
        )
        result = money_mode.content_publish_track("ecommerce", "blog", "article")
        assert result["status"] == "draft"


# ── data_scrape_filter_store ──────────────────────────────────────────────────

class TestDataScrapeFilterStore:

    @patch("urllib.request.urlopen")
    def test_returns_ok_url_stored(self, mock_urlopen, money_mode):
        mock_urlopen.return_value = _make_urlopen_mock()
        result = money_mode.data_scrape_filter_store("https://example.com", "testing")
        assert result["ok"] is True
        assert result["url"] == "https://example.com"
        assert result["stored"] is True

    @patch("urllib.request.urlopen")
    def test_words_extracted_is_positive(self, mock_urlopen, money_mode):
        mock_urlopen.return_value = _make_urlopen_mock()
        result = money_mode.data_scrape_filter_store("https://example.com", "testing")
        assert result["words_extracted"] > 0

    @patch("urllib.request.urlopen")
    def test_duplicate_on_second_call(self, mock_urlopen, money_mode):
        mock_urlopen.return_value = _make_urlopen_mock()
        first = money_mode.data_scrape_filter_store("https://example.com", "testing")
        assert first.get("duplicate") is False

        # Second call — urlopen should NOT be called again
        second = money_mode.data_scrape_filter_store("https://example.com", "testing")
        assert second["ok"] is True
        assert second["duplicate"] is True
        assert second["stored"] is False

    @patch("urllib.request.urlopen")
    def test_knowledge_store_written(self, mock_urlopen, money_mode, isolate_state):
        mock_urlopen.return_value = _make_urlopen_mock()
        money_mode.data_scrape_filter_store("https://example.com", "testing")
        ks_path = isolate_state / "knowledge_store.json"
        assert ks_path.exists()
        ks = json.loads(ks_path.read_text())
        assert len(ks["entries"]) == 1
        assert ks["entries"][0]["source"] == "https://example.com"

    @patch("urllib.request.urlopen")
    def test_scraped_sources_registry_written(self, mock_urlopen, money_mode, isolate_state):
        mock_urlopen.return_value = _make_urlopen_mock()
        money_mode.data_scrape_filter_store("https://example.com", "testing")
        sources_path = isolate_state / "scraped_sources.json"
        assert sources_path.exists()
        sources = json.loads(sources_path.read_text())
        assert sources[0]["url"] == "https://example.com"
        assert sources[0]["stored"] is True

    @patch("urllib.request.urlopen")
    def test_fetch_failure_returns_ok_false(self, mock_urlopen, money_mode):
        mock_urlopen.side_effect = OSError("connection refused")
        result = money_mode.data_scrape_filter_store("https://broken.example", "testing")
        assert result["ok"] is False
        assert "error" in result
        assert result["stored"] is False


# ── outreach_response_conversion ──────────────────────────────────────────────

class TestOutreachResponseConversion:

    @pytest.fixture(autouse=True)
    def _approve_gate(self, monkeypatch):
        """Bypass the HITL gate so tests exercise pipeline logic, not the gate."""
        monkeypatch.setattr("core.hitl_gate.get_hitl_gate", _approved_gate_mock())

    def test_returns_ok_and_draft_status(self, money_mode, monkeypatch):
        monkeypatch.setattr(
            "core.money_mode.MoneyMode._llm_generate",
            staticmethod(lambda prompt, system: None),
        )
        result = money_mode.outreach_response_conversion(
            "Hello {name}", {"name": "Alice"}, ""
        )
        assert result["ok"] is True
        assert result["status"] == "draft"

    def test_draft_file_written_contains_draft_marker(self, money_mode, monkeypatch):
        monkeypatch.setattr(
            "core.money_mode.MoneyMode._llm_generate",
            staticmethod(lambda prompt, system: None),
        )
        result = money_mode.outreach_response_conversion(
            "Hello {name}", {"name": "Alice"}, ""
        )
        file_path = Path(result["file_path"])
        assert file_path.exists()
        content = file_path.read_text(encoding="utf-8")
        assert "DRAFT" in content

    def test_outreach_log_updated(self, money_mode, monkeypatch, isolate_state):
        monkeypatch.setattr(
            "core.money_mode.MoneyMode._llm_generate",
            staticmethod(lambda prompt, system: None),
        )
        money_mode.outreach_response_conversion("Hello {name}", {"name": "Alice"}, "")
        log_path = isolate_state / "outreach_log.json"
        assert log_path.exists()
        entries = json.loads(log_path.read_text())
        assert len(entries) == 1
        assert entries[0]["recipient_name"] == "Alice"
        assert entries[0]["status"] == "draft"

    def test_template_variable_substituted_in_draft(self, money_mode, monkeypatch):
        """When LLM is offline the template fallback substitutes {name}."""
        monkeypatch.setattr(
            "core.money_mode.MoneyMode._llm_generate",
            staticmethod(lambda prompt, system: None),
        )
        result = money_mode.outreach_response_conversion(
            "Hello {name}, welcome!", {"name": "Bob"}, ""
        )
        content = Path(result["file_path"]).read_text(encoding="utf-8")
        assert "Bob" in content

    def test_missing_recipient_defaults_to_recipient_label(self, money_mode, monkeypatch):
        monkeypatch.setattr(
            "core.money_mode.MoneyMode._llm_generate",
            staticmethod(lambda prompt, system: None),
        )
        result = money_mode.outreach_response_conversion("Hi there", None, "")
        assert result["ok"] is True
        log_path = Path(result["file_path"])
        content = log_path.read_text(encoding="utf-8")
        assert "Recipient" in content

    def test_multiple_drafts_accumulate_in_log(self, money_mode, monkeypatch, isolate_state):
        monkeypatch.setattr(
            "core.money_mode.MoneyMode._llm_generate",
            staticmethod(lambda prompt, system: None),
        )
        money_mode.outreach_response_conversion("Hi {name}", {"name": "Alice"}, "")
        money_mode.outreach_response_conversion("Hi {name}", {"name": "Bob"}, "")
        log_path = isolate_state / "outreach_log.json"
        entries = json.loads(log_path.read_text())
        assert len(entries) == 2
