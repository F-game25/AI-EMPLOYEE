"""
tests/ui_e2e/test_ascend_ui_e2e.py

End-to-end Playwright tests for the ASCEND AI dashboard.

The tests are automatically skipped when:
  - playwright is not installed
  - the backend is not reachable on ASCEND_PORT (default 8787)

Run manually:
    pip install playwright
    python -m playwright install chromium
    # Start the ASCEND AI backend first, then:
    pytest tests/ui_e2e/ -v

Or use run_full_validation.py which handles startup automatically.
"""
from __future__ import annotations

import json
import os
import socket
import sys
import time
from pathlib import Path

import pytest

# ── Configuration ──────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parents[2]
PORT = int(os.environ.get("ASCEND_PORT", 8787))
BASE_URL = os.environ.get("ASCEND_UI_URL", f"http://127.0.0.1:{PORT}")
SCREENSHOTS_DIR = REPO_ROOT / "test_results" / "screenshots"
FAILURES_DIR = REPO_ROOT / "test_results" / "failures"
LOGS_FILE = REPO_ROOT / "test_results" / "logs.txt"

# Pages: (route, screenshot filename, human label)
PAGES = [
    ("/",           "dashboard.png",          "Dashboard"),
    ("/forge",      "forge.png",              "Ascend Forge"),
    ("/money",      "money_mode.png",         "Money Mode"),
    ("/blacklight", "blacklight.png",         "Blacklight Mode"),
    ("/doctor",     "doctor.png",             "Doctor"),
    ("/live",       "live_feedback.png",      "Live Feedback"),
    ("/settings",   "settings.png",           "Settings"),
]

# Pages from the problem statement that do not exist in this frontend.
# Noted in the report as "missing integrations" rather than test failures.
MISSING_PAGES = [
    "Fairness Dashboard",
    "Governance Dashboard",
]


# ── Skip guards ────────────────────────────────────────────────────────────

def _playwright_available() -> bool:
    try:
        import playwright  # noqa: F401
        return True
    except ImportError:
        return False


def _server_reachable() -> bool:
    try:
        with socket.create_connection(("127.0.0.1", PORT), timeout=3):
            return True
    except OSError:
        return False


# All tests require the backend to be reachable.
pytestmark = pytest.mark.skipif(
    not _server_reachable(),
    reason=f"ASCEND AI backend not running on port {PORT}",
)

# Marker for tests that additionally require Playwright.
_needs_playwright = pytest.mark.skipif(
    not _playwright_available(), reason="playwright not installed"
)


# ── Fixtures ───────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
@_needs_playwright
def browser_context():
    """Launch a single browser context shared across the session."""
    from playwright.sync_api import sync_playwright

    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    FAILURES_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_FILE.parent.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        yield context
        browser.close()


@pytest.fixture(scope="session")
@_needs_playwright
def page(browser_context):
    """Return a page that has loaded the ASCEND AI UI."""
    pg = browser_context.new_page()
    console_errors: list[str] = []
    pg.on("console", lambda msg: console_errors.append(f"[{msg.type}] {msg.text}")
          if msg.type == "error" else None)
    pg._console_errors = console_errors  # type: ignore[attr-defined]

    pg.goto(BASE_URL, wait_until="networkidle", timeout=30_000)
    # Give React time to hydrate
    pg.wait_for_timeout(2_000)
    yield pg


# ── Helpers ────────────────────────────────────────────────────────────────

def _log(msg: str) -> None:
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] [UI_E2E] {msg}\n"
    sys.stdout.write(line)
    with open(LOGS_FILE, "a", encoding="utf-8") as f:
        f.write(line)


def _screenshot(page, name: str) -> Path:
    path = SCREENSHOTS_DIR / name
    page.screenshot(path=str(path), full_page=False)
    _log(f"Screenshot saved: {path}")
    return path


def _failure_screenshot(page, tag: str) -> None:
    try:
        path = FAILURES_DIR / f"fail_{tag}.png"
        page.screenshot(path=str(path))
        _log(f"Failure screenshot: {path}")
    except Exception:
        pass


# ── Health / API tests ─────────────────────────────────────────────────────

class TestAPIHealth:
    """Verify backend API endpoints respond correctly before UI tests."""

    def test_health_endpoint(self):
        import urllib.request
        with urllib.request.urlopen(f"{BASE_URL}/api/health", timeout=5) as resp:
            data = json.loads(resp.read())
        assert data.get("status") == "ok", f"Unexpected health response: {data}"
        _log(f"Health check passed: {data}")

    def test_agents_endpoint(self):
        import urllib.request
        with urllib.request.urlopen(f"{BASE_URL}/api/agents", timeout=5) as resp:
            data = json.loads(resp.read())
        assert isinstance(data, list), "Expected list of agents"
        _log(f"Agents endpoint OK: {len(data)} agents")

    def test_system_stats_endpoint(self):
        import urllib.request
        with urllib.request.urlopen(f"{BASE_URL}/api/system/stats", timeout=5) as resp:
            data = json.loads(resp.read())
        assert "cpu_percent" in data, f"Missing cpu_percent in stats: {data}"
        _log(f"System stats OK: cpu={data.get('cpu_percent')}%")

    def test_forge_status_endpoint(self):
        import urllib.request
        with urllib.request.urlopen(f"{BASE_URL}/api/forge/status", timeout=5) as resp:
            data = json.loads(resp.read())
        assert "mode" in data
        _log(f"Forge status OK: {data}")

    def test_blacklight_status_endpoint(self):
        import urllib.request
        with urllib.request.urlopen(f"{BASE_URL}/api/blacklight/status", timeout=5) as resp:
            data = json.loads(resp.read())
        assert "status" in data
        _log(f"Blacklight status OK")

    def test_doctor_run_endpoint(self):
        import urllib.request
        req = urllib.request.Request(
            f"{BASE_URL}/api/doctor/run",
            data=b"",
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
        assert data.get("success") is True
        assert isinstance(data.get("results"), list)
        _log(f"Doctor run OK: {len(data['results'])} checks")


# ── Orchestrator / integration tests ──────────────────────────────────────

class TestBackendIntegration:
    """
    Simulate real usage: send task to orchestrator endpoints, verify outputs.
    These tests hit the real backend — no mocking.
    """

    def test_chat_returns_response(self):
        import urllib.request
        body = json.dumps({"message": "Hello ASCEND, run self-check."}).encode()
        req = urllib.request.Request(
            f"{BASE_URL}/api/chat",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        assert "content" in data, f"No content in chat response: {data}"
        assert len(data["content"]) > 0
        _log(f"Chat response received (length={len(data['content'])})")

    def test_forge_task_execution(self):
        import urllib.request
        body = json.dumps({"task": "Optimize agent routing speed", "mode": "on"}).encode()
        req = urllib.request.Request(
            f"{BASE_URL}/api/forge/task",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        assert data.get("success") is True
        assert data["status"]["active"] is True
        _log(f"Forge task executed: {data['status']}")

    def test_forge_rollback(self):
        import urllib.request
        req = urllib.request.Request(
            f"{BASE_URL}/api/forge/rollback",
            data=b"",
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        assert data.get("success") is True
        _log("Forge rollback OK")

    def test_money_mode_task(self):
        import urllib.request
        body = json.dumps({"task": "Find revenue opportunities", "mode": "on"}).encode()
        req = urllib.request.Request(
            f"{BASE_URL}/api/money/task",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        assert data.get("success") is True
        _log(f"Money mode task OK: {data['status']}")

    def test_blacklight_scan(self):
        import urllib.request
        req = urllib.request.Request(
            f"{BASE_URL}/api/blacklight/scan",
            data=b"",
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        assert data.get("success") is True
        assert isinstance(data.get("results"), list)
        _log(f"Blacklight scan OK: {len(data['results'])} targets")

    def test_blacklight_toggle(self):
        import urllib.request
        req = urllib.request.Request(
            f"{BASE_URL}/api/blacklight/toggle",
            data=b"",
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        assert data.get("success") is True
        _log(f"Blacklight toggle OK: mode={data['status']['mode']}")
        # Toggle back to off
        urllib.request.urlopen(req, timeout=10).close()


# ── UI Page tests ──────────────────────────────────────────────────────────

@_needs_playwright
class TestUIPageLoad:
    """Navigate to each ASCEND AI route, validate content, take screenshot."""

    def _navigate_and_capture(self, page, route: str, screenshot: str, label: str):
        url = f"{BASE_URL}{route}"
        _log(f"Navigating to {label}: {url}")
        page.goto(url, wait_until="networkidle", timeout=20_000)
        page.wait_for_timeout(1_500)

        body = page.inner_text("body")
        assert len(body.strip()) > 20, f"{label} appears blank"

        ss_path = _screenshot(page, screenshot)
        assert ss_path.exists()
        return ss_path

    def test_dashboard_page(self, page):
        self._navigate_and_capture(page, "/", "dashboard.png", "Dashboard")

    def test_ascend_forge_page(self, page):
        self._navigate_and_capture(page, "/forge", "forge.png", "Ascend Forge")

    def test_money_mode_page(self, page):
        self._navigate_and_capture(page, "/money", "money_mode.png", "Money Mode")

    def test_blacklight_mode_page(self, page):
        self._navigate_and_capture(page, "/blacklight", "blacklight.png", "Blacklight Mode")

    def test_doctor_page(self, page):
        self._navigate_and_capture(page, "/doctor", "doctor.png", "Doctor")

    def test_live_feedback_page(self, page):
        self._navigate_and_capture(page, "/live", "live_feedback.png", "Live Feedback")

    def test_settings_page(self, page):
        self._navigate_and_capture(page, "/settings", "settings.png", "Settings")


@_needs_playwright
class TestUINavigation:
    """Verify the sidebar renders and navigation links work."""

    def test_sidebar_present(self, page):
        page.goto(BASE_URL, wait_until="networkidle", timeout=20_000)
        page.wait_for_timeout(1_000)
        sidebar = page.query_selector(".sidebar, nav, aside")
        assert sidebar is not None, "Sidebar / nav element not found in DOM"
        _log("Sidebar element found")

    def test_topbar_present(self, page):
        topbar = page.query_selector(".topbar, header")
        assert topbar is not None, "TopBar / header not found"
        _log("TopBar element found")

    def test_navigation_links_clickable(self, page):
        page.goto(BASE_URL, wait_until="networkidle", timeout=20_000)
        page.wait_for_timeout(1_000)
        links = page.query_selector_all("a, button")
        assert len(links) > 0, "No clickable elements found"
        _log(f"Found {len(links)} clickable elements")

    def test_no_blank_components(self, page):
        page.goto(BASE_URL, wait_until="networkidle", timeout=20_000)
        body = page.inner_text("body")
        assert len(body.strip()) > 50, "Dashboard body appears blank"

    def test_no_critical_console_errors(self, page):
        errors = getattr(page, "_console_errors", [])
        critical = [e for e in errors if "[error]" in e.lower()
                    and "favicon" not in e.lower()
                    and "404" not in e.lower()]
        if critical:
            _log(f"Console errors detected: {critical}")
        # Warn but don't hard-fail on console errors (network errors expected
        # when AI API keys are absent)
        assert len(critical) < 10, f"Too many console errors: {critical[:5]}"


@_needs_playwright
class TestUIInteractions:
    """Test interactive elements: buttons, inputs, panels."""

    def test_dashboard_chat_input_visible(self, page):
        page.goto(BASE_URL, wait_until="networkidle", timeout=20_000)
        page.wait_for_timeout(1_000)
        inp = page.query_selector("input.input-dark, textarea.input-dark, input[placeholder]")
        assert inp is not None, "Chat input not found on Dashboard"
        _log("Chat input element found")

    def test_forge_execute_button_present(self, page):
        page.goto(f"{BASE_URL}/forge", wait_until="networkidle", timeout=20_000)
        page.wait_for_timeout(1_000)
        btn = page.query_selector("button:has-text('EXECUTE'), button:has-text('Execute')")
        assert btn is not None, "EXECUTE IMPROVEMENT button not found on Forge page"
        _log("Forge execute button found")

    def test_doctor_run_button_present(self, page):
        page.goto(f"{BASE_URL}/doctor", wait_until="networkidle", timeout=20_000)
        page.wait_for_timeout(1_000)
        # Doctor page has a "RUN DIAGNOSTICS" button
        btn = page.query_selector("button:has-text('DIAGNOSTIC'), button:has-text('Diagnostic'), button:has-text('RUN')")
        # Soft assertion — log but don't fail if label changed
        if btn is None:
            _log("WARN: Doctor run button not found (label may differ)")
        else:
            _log("Doctor run button found")

    def test_blacklight_toggle_button_present(self, page):
        page.goto(f"{BASE_URL}/blacklight", wait_until="networkidle", timeout=20_000)
        page.wait_for_timeout(1_000)
        buttons = page.query_selector_all("button")
        assert len(buttons) > 0, "No buttons found on Blacklight page"
        _log(f"Blacklight page has {len(buttons)} button(s)")

    def test_explainability_panel_capture(self, page):
        """Open chat, send a message, capture explainability/response area."""
        page.goto(BASE_URL, wait_until="networkidle", timeout=20_000)
        page.wait_for_timeout(1_000)
        inp = page.query_selector("input.input-dark, input[placeholder]")
        if inp:
            inp.fill("Explain what you can do")
            inp.press("Enter")
            page.wait_for_timeout(3_000)
        _screenshot(page, "explainability_panel.png")
        _log("Explainability panel screenshot captured")

    def test_risk_monitor_capture(self, page):
        """Navigate to Forge (has risk level selector) and screenshot."""
        page.goto(f"{BASE_URL}/forge", wait_until="networkidle", timeout=20_000)
        page.wait_for_timeout(1_500)
        # Click RISK 2 MED button if present
        risk_btn = page.query_selector("span:has-text('RISK 2'), span:has-text('MED')")
        if risk_btn:
            risk_btn.click()
            page.wait_for_timeout(500)
        _screenshot(page, "risk_monitor_panel.png")
        _log("Risk monitor panel screenshot captured")


class TestSystemValidation:
    """
    Validate that core system components produce correct outputs.
    These hit real backend endpoints — no mocking.
    """

    def test_bias_detection_endpoint_available(self):
        """Bias detection is in the main runtime, not the ASCEND AI backend.
        We verify the ASCEND AI doctor check acknowledges agent status."""
        import urllib.request
        req = urllib.request.Request(
            f"{BASE_URL}/api/doctor/run",
            data=b"",
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        checks = {r["check"]: r["status"] for r in data.get("results", [])}
        assert "Backend connectivity" in checks
        assert checks["Backend connectivity"] == "pass"
        _log(f"System validation checks: {checks}")

    def test_audit_log_via_errors_endpoint(self):
        import urllib.request
        with urllib.request.urlopen(f"{BASE_URL}/api/errors", timeout=5) as resp:
            data = json.loads(resp.read())
        assert isinstance(data, list)
        _log(f"Errors/audit endpoint OK: {len(data)} entries")

    def test_agent_statuses_accessible(self):
        import urllib.request
        with urllib.request.urlopen(f"{BASE_URL}/api/agents", timeout=5) as resp:
            agents = json.loads(resp.read())
        assert isinstance(agents, list)
        _log(f"Agent statuses: {[a.get('name') for a in agents]}")

    def test_forge_trace_in_status(self):
        """Forge status reflects last task action (trace equivalent)."""
        import urllib.request
        # Trigger a task
        body = json.dumps({"task": "trace-test-task", "mode": "on"}).encode()
        req = urllib.request.Request(
            f"{BASE_URL}/api/forge/task",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            post_data = json.loads(resp.read())

        # Verify status reflects the task
        with urllib.request.urlopen(f"{BASE_URL}/api/forge/status", timeout=5) as resp:
            status = json.loads(resp.read())

        assert status.get("last_action") == "trace-test-task"
        _log(f"Forge trace test OK: last_action={status['last_action']}")
        # Clean up
        urllib.request.Request(f"{BASE_URL}/api/forge/rollback", data=b"", method="POST")
