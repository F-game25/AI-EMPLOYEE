"""Backend API endpoint tests.

Validates that the Node.js backend server endpoints exist, return correct
status codes, and provide expected response shapes.
"""
from __future__ import annotations

import json
import os
import socket
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_PORT = int(os.environ.get("PORT", 8787))
BASE_URL = f"http://127.0.0.1:{BACKEND_PORT}"


def _server_reachable() -> bool:
    """Return True if the backend server is accepting connections."""
    try:
        with socket.create_connection(("127.0.0.1", BACKEND_PORT), timeout=2):
            return True
    except OSError:
        return False


# Skip entire module if the backend isn't running
pytestmark = pytest.mark.skipif(
    not _server_reachable(),
    reason=f"Backend server not running on port {BACKEND_PORT}",
)


def _get(path: str) -> "tuple[int, dict | list | str]":
    """Perform a simple GET request using urllib (no extra deps)."""
    import urllib.request
    import urllib.error
    url = f"{BASE_URL}{path}"
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = resp.read().decode("utf-8")
            try:
                data = json.loads(body)
            except json.JSONDecodeError:
                data = body
            return resp.status, data
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            data = body
        return e.code, data


def _post(path: str, body: dict | None = None) -> "tuple[int, dict | list | str]":
    """Perform a simple POST request using urllib."""
    import urllib.request
    import urllib.error
    url = f"{BASE_URL}{path}"
    payload = json.dumps(body or {}).encode("utf-8")
    try:
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data_raw = resp.read().decode("utf-8")
            try:
                data = json.loads(data_raw)
            except json.JSONDecodeError:
                data = data_raw
            return resp.status, data
    except urllib.error.HTTPError as e:
        data_raw = e.read().decode("utf-8", errors="replace")
        try:
            data = json.loads(data_raw)
        except json.JSONDecodeError:
            data = data_raw
        return e.code, data


# ---------------------------------------------------------------------------
# Test: Health and version endpoints
# ---------------------------------------------------------------------------

class TestHealthEndpoints:
    """Verify health and version endpoints respond correctly."""

    def test_health_endpoint(self) -> None:
        status, data = _get("/health")
        assert status == 200

    def test_version_endpoint(self) -> None:
        status, data = _get("/version")
        assert status == 200
        assert isinstance(data, dict)
        assert "commit" in data or "version" in data or "started_at" in data


# ---------------------------------------------------------------------------
# Test: System status API
# ---------------------------------------------------------------------------

class TestSystemStatusAPI:
    """Verify system status endpoint returns expected shape."""

    def test_system_status(self) -> None:
        status, data = _get("/api/status")
        assert status == 200
        assert isinstance(data, dict)


# ---------------------------------------------------------------------------
# Test: Dashboard / product APIs
# ---------------------------------------------------------------------------

class TestDashboardAPIs:
    """Verify dashboard-related API endpoints."""

    def test_product_dashboard(self) -> None:
        status, data = _get("/api/product/dashboard")
        assert status == 200
        assert isinstance(data, dict)

    def test_mode_endpoint(self) -> None:
        status, data = _get("/api/mode")
        assert status == 200
        assert isinstance(data, dict)
        assert "mode" in data

    def test_agents_endpoint(self) -> None:
        status, data = _get("/agents")
        assert status == 200
        assert isinstance(data, (dict, list))


# ---------------------------------------------------------------------------
# Test: Brain API endpoints
# ---------------------------------------------------------------------------

class TestBrainAPIs:
    """Verify brain-related endpoints."""

    def test_brain_status(self) -> None:
        status, data = _get("/api/brain/status")
        assert status == 200

    def test_brain_insights(self) -> None:
        status, data = _get("/api/brain/insights")
        assert status == 200

    def test_brain_activity(self) -> None:
        status, data = _get("/api/brain/activity?limit=10")
        assert status == 200


# ---------------------------------------------------------------------------
# Test: Audit API endpoints
# ---------------------------------------------------------------------------

class TestAuditAPIs:
    """Verify audit log endpoints."""

    def test_audit_events(self) -> None:
        status, data = _get("/api/audit/events")
        assert status == 200

    def test_audit_stats(self) -> None:
        status, data = _get("/api/audit/stats")
        assert status == 200


# ---------------------------------------------------------------------------
# Test: Forge API endpoints
# ---------------------------------------------------------------------------

class TestForgeAPIs:
    """Verify Forge API endpoints."""

    def test_forge_queue(self) -> None:
        status, data = _get("/api/forge/queue")
        assert status == 200

    def test_forge_submit(self) -> None:
        status, data = _post("/api/forge/submit", {"goal": "test improvement"})
        # 200 or 201 are both acceptable
        assert status in (200, 201)


# ---------------------------------------------------------------------------
# Test: Reliability API endpoints
# ---------------------------------------------------------------------------

class TestReliabilityAPIs:
    """Verify reliability engine endpoints."""

    def test_reliability_status(self) -> None:
        status, data = _get("/api/reliability/status")
        assert status == 200
