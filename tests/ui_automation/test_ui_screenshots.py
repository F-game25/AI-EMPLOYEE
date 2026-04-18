"""Playwright-based pytest tests for UI validation.

These tests use the screenshot_runner module to perform actual browser-based
validation. They are skipped when playwright is not installed or the UI is
not reachable.
"""
from __future__ import annotations

import os
import socket
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

BACKEND_PORT = int(os.environ.get("PORT", 8787))


def _playwright_available() -> bool:
    try:
        import playwright  # noqa: F401
        return True
    except ImportError:
        return False


def _server_reachable() -> bool:
    try:
        with socket.create_connection(("127.0.0.1", BACKEND_PORT), timeout=2):
            return True
    except OSError:
        return False


pytestmark = [
    pytest.mark.skipif(not _playwright_available(), reason="playwright not installed"),
    pytest.mark.skipif(not _server_reachable(), reason=f"UI server not running on port {BACKEND_PORT}"),
]


class TestUIScreenshots:
    """Run the full UI screenshot suite and validate results."""

    def test_screenshot_suite_runs(self) -> None:
        from tests.ui_automation.screenshot_runner import run_screenshot_suite, generate_summary
        results = run_screenshot_suite()
        summary = generate_summary(results)
        assert summary["total"] > 0, "No pages were tested"

    def test_all_screenshots_captured(self) -> None:
        from tests.ui_automation.screenshot_runner import run_screenshot_suite
        results = run_screenshot_suite()
        for r in results:
            if r.success:
                assert Path(r.screenshot_path).exists(), f"Screenshot missing: {r.screenshot_path}"

    def test_no_blank_pages(self) -> None:
        from tests.ui_automation.screenshot_runner import run_screenshot_suite
        results = run_screenshot_suite()
        blank_pages = [r.page_id for r in results if "blank_page" in r.validation_issues]
        assert len(blank_pages) == 0, f"Blank pages detected: {blank_pages}"
