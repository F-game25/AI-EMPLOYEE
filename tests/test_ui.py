"""UI component validation tests.

These tests verify that the frontend components are correctly structured,
the dashboard renders expected pages, and the navigation items map to
valid page components.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_SRC = REPO_ROOT / "frontend" / "src"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _jsx_files(directory: Path) -> list[Path]:
    """Return all .jsx files in *directory* (non-recursive)."""
    return sorted(directory.glob("*.jsx"))


# ---------------------------------------------------------------------------
# Test: All expected page components exist
# ---------------------------------------------------------------------------

EXPECTED_PAGES = [
    "DashboardPage.jsx",
    "ControlCenterPage.jsx",
    "AgentsPage.jsx",
    "AIControlPage.jsx",
    "NeuralBrainPage.jsx",
    "OperationsPage.jsx",
    "SystemPage.jsx",
    "VoicePage.jsx",
]


class TestPageComponentsExist:
    """Verify that every expected page component file is present."""

    @pytest.mark.parametrize("filename", EXPECTED_PAGES)
    def test_page_file_exists(self, filename: str) -> None:
        path = FRONTEND_SRC / "components" / "pages" / filename
        assert path.exists(), f"Missing page component: {path}"

    @pytest.mark.parametrize("filename", EXPECTED_PAGES)
    def test_page_exports_default(self, filename: str) -> None:
        """Each page must have a default export."""
        path = FRONTEND_SRC / "components" / "pages" / filename
        content = _read_text(path)
        assert "export default" in content, f"{filename} missing default export"


# ---------------------------------------------------------------------------
# Test: Sidebar navigation items are well-formed
# ---------------------------------------------------------------------------

class TestSidebarNavigation:
    """Validate the sidebar navigation configuration."""

    SIDEBAR_PATH = FRONTEND_SRC / "components" / "layout" / "Sidebar.jsx"

    def test_sidebar_file_exists(self) -> None:
        assert self.SIDEBAR_PATH.exists()

    def test_nav_items_defined(self) -> None:
        content = _read_text(self.SIDEBAR_PATH)
        assert "NAV_ITEMS" in content, "Sidebar must define NAV_ITEMS"

    def test_nav_items_have_required_fields(self) -> None:
        """Each nav item must have id, icon, and label."""
        content = _read_text(self.SIDEBAR_PATH)
        # Extract the NAV_ITEMS array literal
        match = re.search(r"NAV_ITEMS\s*=\s*\[(.*?)\]", content, re.DOTALL)
        assert match, "Could not parse NAV_ITEMS"
        items_text = match.group(1)
        # Each item object must have id, icon, label
        for field in ("id:", "icon:", "label:"):
            assert field in items_text, f"NAV_ITEMS missing '{field}' field"

    def test_expected_nav_ids_present(self) -> None:
        """Dashboard, agents, control-center must be in the nav."""
        content = _read_text(self.SIDEBAR_PATH)
        for nav_id in ("dashboard", "agents", "control-center"):
            assert f"'{nav_id}'" in content or f'"{nav_id}"' in content, (
                f"NAV_ITEMS missing '{nav_id}'"
            )


# ---------------------------------------------------------------------------
# Test: Dashboard routing maps all page IDs to components
# ---------------------------------------------------------------------------

class TestDashboardRouting:
    """The PAGES mapping in Dashboard.jsx must reference all nav IDs."""

    DASHBOARD_PATH = FRONTEND_SRC / "components" / "Dashboard.jsx"

    def test_dashboard_exists(self) -> None:
        assert self.DASHBOARD_PATH.exists()

    def test_pages_map_defined(self) -> None:
        content = _read_text(self.DASHBOARD_PATH)
        assert "PAGES" in content, "Dashboard.jsx must define PAGES mapping"

    @pytest.mark.parametrize(
        "page_id",
        ["dashboard", "ai-control", "neural-brain", "operations", "agents", "control-center", "system", "voice"],
    )
    def test_page_id_in_routing(self, page_id: str) -> None:
        content = _read_text(self.DASHBOARD_PATH)
        assert f"'{page_id}'" in content or f'"{page_id}"' in content, (
            f"PAGES mapping missing '{page_id}'"
        )


# ---------------------------------------------------------------------------
# Test: App.jsx top-level structure
# ---------------------------------------------------------------------------

class TestAppStructure:
    """Basic structural checks on the root App component."""

    APP_PATH = FRONTEND_SRC / "App.jsx"

    def test_app_file_exists(self) -> None:
        assert self.APP_PATH.exists()

    def test_app_imports_boot_sequence(self) -> None:
        content = _read_text(self.APP_PATH)
        assert "BootSequence" in content

    def test_app_imports_dashboard(self) -> None:
        content = _read_text(self.APP_PATH)
        assert "Dashboard" in content

    def test_app_exports_default(self) -> None:
        content = _read_text(self.APP_PATH)
        assert "export default" in content


# ---------------------------------------------------------------------------
# Test: Frontend configuration
# ---------------------------------------------------------------------------

class TestFrontendConfig:
    """Validate frontend configuration files."""

    def test_vite_config_exists(self) -> None:
        assert (REPO_ROOT / "frontend" / "vite.config.js").exists()

    def test_api_config_defines_url(self) -> None:
        path = FRONTEND_SRC / "config" / "api.js"
        assert path.exists()
        content = _read_text(path)
        assert "API_URL" in content

    def test_api_config_defines_ws_url(self) -> None:
        path = FRONTEND_SRC / "config" / "api.js"
        content = _read_text(path)
        assert "WS_URL" in content

    def test_vite_proxy_configured(self) -> None:
        """The Vite dev server must proxy /api calls to the backend."""
        content = _read_text(REPO_ROOT / "frontend" / "vite.config.js")
        assert "proxy" in content
        assert "'/api'" in content or '"/api"' in content


# ---------------------------------------------------------------------------
# Test: No empty page components
# ---------------------------------------------------------------------------

class TestNoEmptyPages:
    """Every page component must contain substantive JSX, not just a stub."""

    PAGES_DIR = FRONTEND_SRC / "components" / "pages"

    @pytest.mark.parametrize("filename", EXPECTED_PAGES)
    def test_page_has_content(self, filename: str) -> None:
        path = self.PAGES_DIR / filename
        content = _read_text(path)
        # Must be at least 200 chars — a meaningful component
        assert len(content) > 200, f"{filename} looks like an empty stub ({len(content)} chars)"

    @pytest.mark.parametrize("filename", EXPECTED_PAGES)
    def test_page_returns_jsx(self, filename: str) -> None:
        """Page component must have a return statement with JSX."""
        content = _read_text(path := self.PAGES_DIR / filename)
        assert "return" in content and ("<" in content), (
            f"{filename} does not appear to return JSX"
        )


# ---------------------------------------------------------------------------
# Test: CSS/styling entry points exist
# ---------------------------------------------------------------------------

class TestStylingAssets:
    """Verify core CSS entry points are present."""

    def test_index_css_exists(self) -> None:
        assert (FRONTEND_SRC / "index.css").exists()

    def test_app_css_exists(self) -> None:
        assert (FRONTEND_SRC / "App.css").exists()

    def test_index_html_exists(self) -> None:
        assert (REPO_ROOT / "frontend" / "index.html").exists()
