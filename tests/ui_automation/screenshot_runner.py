"""Playwright-based UI automation with screenshot capture.

Navigates through every major page of the AI Employee dashboard,
waits for content to load, validates that the page is non-empty,
and captures a screenshot for visual proof.

Usage (standalone):
    python -m tests.ui_automation.screenshot_runner

Or via the main test runner (run_full_tests.py) which calls this module.

Requirements:
    pip install playwright
    python -m playwright install chromium
"""
from __future__ import annotations

import json
import logging
import os
import sys
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger("ui_automation")

REPO_ROOT = Path(__file__).resolve().parents[2]
SCREENSHOTS_DIR = REPO_ROOT / "test_results" / "screenshots"
FAILURES_DIR = REPO_ROOT / "test_results" / "failures"
LOGS_FILE = REPO_ROOT / "test_results" / "logs.txt"

# The dashboard is served on the backend port after build, or Vite dev port
DEFAULT_BASE_URL = os.environ.get("UI_BASE_URL", "http://127.0.0.1:8787")

# Pages to navigate — the sidebar button IDs
# The dashboard uses a PAGES mapping keyed by these IDs.
PAGE_CONFIG: list[dict] = [
    {"id": "dashboard", "label": "Dashboard", "screenshot": "dashboard.png"},
    {"id": "ai-control", "label": "AI Control", "screenshot": "ai_control.png"},
    {"id": "neural-brain", "label": "Neural Brain", "screenshot": "neural_brain.png"},
    {"id": "operations", "label": "Operations", "screenshot": "operations.png"},
    {"id": "agents", "label": "Agents", "screenshot": "agent_monitor.png"},
    {"id": "control-center", "label": "Control Center", "screenshot": "control_center.png"},
    {"id": "system", "label": "System", "screenshot": "system.png"},
    {"id": "voice", "label": "Voice", "screenshot": "voice.png"},
]


@dataclass
class ScreenshotResult:
    """Result of a single page screenshot attempt."""

    page_id: str
    label: str
    screenshot_path: str = ""
    success: bool = False
    error: str = ""
    console_errors: list[str] = field(default_factory=list)
    validation_issues: list[str] = field(default_factory=list)
    load_time_ms: int = 0


def _ensure_dirs() -> None:
    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    FAILURES_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_FILE.parent.mkdir(parents=True, exist_ok=True)


def _log(msg: str) -> None:
    """Append to the shared log file."""
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] [UI_AUTOMATION] {msg}"
    logger.info(msg)
    with open(LOGS_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def run_screenshot_suite(
    base_url: str = DEFAULT_BASE_URL,
    headless: bool = True,
) -> list[ScreenshotResult]:
    """Run the full UI automation suite.

    Returns a list of ScreenshotResult for each page.
    """
    # Late import so the module can be imported without playwright installed
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        _log("ERROR: playwright not installed. Run: pip install playwright && python -m playwright install chromium")
        return [
            ScreenshotResult(
                page_id="__init__",
                label="Playwright Setup",
                error="playwright not installed",
            )
        ]

    _ensure_dirs()
    results: list[ScreenshotResult] = []

    _log(f"Starting UI automation suite against {base_url}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        page = context.new_page()

        # Collect console errors
        console_errors: list[str] = []
        page.on("console", lambda msg: (
            console_errors.append(f"[{msg.type}] {msg.text}")
            if msg.type == "error"
            else None
        ))

        # 1. Navigate to the root URL — this triggers the boot sequence
        _log(f"Navigating to {base_url}")
        try:
            page.goto(base_url, wait_until="networkidle", timeout=30000)
        except Exception as e:
            _log(f"FATAL: Could not load {base_url}: {e}")
            results.append(
                ScreenshotResult(
                    page_id="__load__",
                    label="Initial Load",
                    error=str(e),
                )
            )
            browser.close()
            return results

        # 2. Wait for boot to complete (the app has a boot animation)
        _log("Waiting for boot sequence to complete...")
        try:
            # The dashboard appears after boot — wait for sidebar nav
            page.wait_for_selector("nav.sidebar, [role='navigation']", timeout=20000)
            _log("Boot sequence complete — sidebar visible")
        except Exception:
            _log("WARN: Sidebar not found after 20s — attempting screenshot anyway")

        # Small extra wait for animations
        page.wait_for_timeout(1500)

        # 3. Iterate through each page
        for pc in PAGE_CONFIG:
            result = _capture_page(page, pc, console_errors)
            results.append(result)

        browser.close()

    _log(f"UI automation complete: {sum(1 for r in results if r.success)}/{len(results)} passed")
    return results


def _capture_page(page, pc: dict, console_errors: list[str]) -> ScreenshotResult:
    """Navigate to a page via sidebar click, validate, and screenshot."""
    page_id = pc["id"]
    label = pc["label"]
    screenshot_name = pc["screenshot"]
    result = ScreenshotResult(page_id=page_id, label=label)

    _log(f"Navigating to: {label} (id={page_id})")
    start_ts = time.time()

    try:
        # Click the sidebar button for this page
        selector = f"button:has-text('{label}')"
        btn = page.query_selector(selector)
        if not btn:
            # Fallback: try by aria
            selector = f"[aria-current], button >> text='{label}'"
            btn = page.query_selector(f"button >> text='{label}'")
        if btn:
            btn.click()
        else:
            result.error = f"Sidebar button '{label}' not found"
            result.validation_issues.append(f"nav_button_missing:{page_id}")
            _log(f"  WARN: Button not found for {label}")

        # Wait for the page content to appear
        page.wait_for_timeout(2000)

        # Calculate load time
        result.load_time_ms = int((time.time() - start_ts) * 1000)

        # Validate: page should not be blank
        body_text = page.inner_text("body")
        if len(body_text.strip()) < 20:
            result.validation_issues.append("blank_page")
            _log(f"  WARN: Page '{label}' appears blank")

        # Validate: check for console errors since last page
        errors_snapshot = list(console_errors)
        if errors_snapshot:
            result.console_errors = errors_snapshot.copy()
            # Don't clear — accumulate, but note they exist
            _log(f"  WARN: {len(errors_snapshot)} console errors detected")

        # Take screenshot
        ss_path = SCREENSHOTS_DIR / screenshot_name
        page.screenshot(path=str(ss_path), full_page=False)
        result.screenshot_path = str(ss_path)
        result.success = True
        _log(f"  OK: Screenshot saved to {ss_path} ({result.load_time_ms}ms)")

    except Exception as exc:
        result.error = str(exc)
        result.success = False
        _log(f"  ERROR: {exc}")

        # Capture failure screenshot
        try:
            fail_path = FAILURES_DIR / f"fail_{page_id}.png"
            page.screenshot(path=str(fail_path))
            _log(f"  Failure screenshot saved to {fail_path}")
        except Exception:
            pass

    return result


def generate_summary(results: list[ScreenshotResult]) -> dict:
    """Generate a summary dict from screenshot results."""
    passed = [r for r in results if r.success]
    failed = [r for r in results if not r.success]
    return {
        "total": len(results),
        "passed": len(passed),
        "failed": len(failed),
        "screenshot_paths": [r.screenshot_path for r in passed if r.screenshot_path],
        "failures": [
            {"page": r.page_id, "label": r.label, "error": r.error}
            for r in failed
        ],
        "validation_warnings": [
            {"page": r.page_id, "issues": r.validation_issues}
            for r in results
            if r.validation_issues
        ],
        "console_errors_detected": any(r.console_errors for r in results),
    }


# ---------------------------------------------------------------------------
# Standalone execution
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    url = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_BASE_URL
    results = run_screenshot_suite(base_url=url)
    summary = generate_summary(results)
    print(json.dumps(summary, indent=2))
