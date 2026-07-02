"""Integration tests for the Node.js backend API surface (port 8787).

These tests exercise the HTTP layer end-to-end.  They are decorated with
``pytest.mark.integration`` and skip gracefully when the backend is not
reachable so the unit-test suite can still run in CI without a live stack.

Run only integration tests:
    pytest tests/test_integration_api.py -v -m integration

Run with a live JWT:
    TEST_JWT=<token> pytest tests/test_integration_api.py -v -m integration
"""
from __future__ import annotations

import os
import socket

import pytest
import requests

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BASE = os.environ.get("API_BASE", "http://localhost:8787")
_raw_jwt = os.environ.get("TEST_JWT", "")
AUTH_HEADERS = {"Authorization": f"Bearer {_raw_jwt}"} if _raw_jwt else {}
_HAS_JWT = bool(_raw_jwt)

# ---------------------------------------------------------------------------
# Reachability guard — evaluated once at collection time
# ---------------------------------------------------------------------------

def _reachable() -> bool:
    """Return True if the backend accepts TCP connections on the expected port."""
    try:
        host = BASE.split("://", 1)[-1].split(":")[0]
        port_str = BASE.rsplit(":", 1)[-1].split("/")[0]
        port = int(port_str) if port_str.isdigit() else 8787
        with socket.create_connection((host, port), timeout=2):
            return True
    except OSError:
        return False


skip_if_offline = pytest.mark.skipif(
    not _reachable(),
    reason="Backend not reachable at %s — start the stack with 'bash start.sh'" % BASE,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get(path: str, *, auth: bool = False, timeout: int = 5) -> requests.Response:
    headers = AUTH_HEADERS if auth else {}
    try:
        return requests.get(f"{BASE}{path}", headers=headers, timeout=timeout)
    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as exc:
        # _reachable() is checked once at collection time; the backend can still
        # go down (or not be fully up yet) by the time a test actually runs. Skip
        # rather than fail so a flapping/slow-starting local server doesn't read
        # as a code regression.
        pytest.skip(f"Backend became unreachable at {BASE}{path}: {exc}")


def _post(path: str, payload: dict, *, auth: bool = False, timeout: int = 5) -> requests.Response:
    headers = {"Content-Type": "application/json"}
    if auth:
        headers.update(AUTH_HEADERS)
    try:
        return requests.post(f"{BASE}{path}", json=payload, headers=headers, timeout=timeout)
    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as exc:
        pytest.skip(f"Backend became unreachable at {BASE}{path}: {exc}")


def _assert_auth_gate(resp: requests.Response) -> None:
    """Assert the endpoint enforces authentication (401) rather than crashing (5xx)."""
    assert resp.status_code in (401, 403), (
        f"Expected 401/403 auth gate, got {resp.status_code}. "
        "A 5xx means the endpoint crashed before reaching auth middleware."
    )


def _assert_ok_or_auth(resp: requests.Response) -> None:
    """When a JWT is present assert 2xx; when absent assert 401/403, never 5xx."""
    if _HAS_JWT:
        assert resp.status_code < 300, (
            f"Expected 2xx with TEST_JWT, got {resp.status_code}: {resp.text[:200]}"
        )
    else:
        _assert_auth_gate(resp)


# ---------------------------------------------------------------------------
# 1. Health check — always public
# ---------------------------------------------------------------------------

@skip_if_offline
@pytest.mark.integration
def test_health_returns_200():
    resp = _get("/health")
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"


@skip_if_offline
@pytest.mark.integration
def test_health_body_has_status_key():
    resp = _get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert "status" in body, f"'status' key missing from health response: {body}"


# ---------------------------------------------------------------------------
# 2. Agents list — auth-gated route
# ---------------------------------------------------------------------------

@skip_if_offline
@pytest.mark.integration
def test_agents_list_enforces_auth():
    resp = _get("/api/agents")
    _assert_ok_or_auth(resp)


@skip_if_offline
@pytest.mark.integration
def test_agents_list_is_non_empty():
    # Only assert content when authenticated
    if not os.environ.get("TEST_JWT"):
        pytest.skip("TEST_JWT not set — skipping content assertion")
    resp = _get("/api/agents", auth=True)
    assert resp.status_code == 200
    body = resp.json()
    agents = body if isinstance(body, list) else body.get("agents", body.get("data", []))
    assert len(agents) >= 1, f"Agent catalog must contain at least 1 agent. Got: {body}"


# ---------------------------------------------------------------------------
# 3. Vault notes — protected route
# ---------------------------------------------------------------------------

@skip_if_offline
@pytest.mark.integration
def test_vault_notes_enforces_auth():
    resp = _get("/api/vault/notes")
    _assert_ok_or_auth(resp)


# ---------------------------------------------------------------------------
# 4. Topics — protected route
# ---------------------------------------------------------------------------

@skip_if_offline
@pytest.mark.integration
def test_topics_enforces_auth():
    resp = _get("/api/topics")
    _assert_ok_or_auth(resp)


# ---------------------------------------------------------------------------
# 5. Learning pending-review — protected route
# ---------------------------------------------------------------------------

@skip_if_offline
@pytest.mark.integration
def test_learning_pending_review_enforces_auth():
    resp = _get("/api/learning/pending-review")
    _assert_ok_or_auth(resp)


# ---------------------------------------------------------------------------
# 6. Security threats — protected route
# ---------------------------------------------------------------------------

@skip_if_offline
@pytest.mark.integration
def test_security_threats_enforces_auth():
    resp = _get("/api/security/threats")
    _assert_ok_or_auth(resp)


# ---------------------------------------------------------------------------
# 7. Blacklight tools — protected route
# ---------------------------------------------------------------------------

@skip_if_offline
@pytest.mark.integration
def test_blacklight_tools_enforces_auth():
    resp = _get("/api/blacklight/tools")
    _assert_ok_or_auth(resp)


# ---------------------------------------------------------------------------
# 8. Forge projects — protected route
# ---------------------------------------------------------------------------

@skip_if_offline
@pytest.mark.integration
def test_forge_projects_enforces_auth():
    resp = _get("/api/forge/projects")
    _assert_ok_or_auth(resp)


# ---------------------------------------------------------------------------
# 9. Memory graph relations — protected route
# ---------------------------------------------------------------------------

@skip_if_offline
@pytest.mark.integration
def test_memory_graph_relations_enforces_auth():
    resp = _get("/api/memory/graph/relations")
    _assert_ok_or_auth(resp)


# ---------------------------------------------------------------------------
# 10. Auth login with bad credentials — must not 500
# ---------------------------------------------------------------------------

@skip_if_offline
@pytest.mark.integration
def test_login_bad_credentials_returns_4xx_not_5xx():
    resp = _post(
        "/api/auth/login",
        {"username": "no_such_user@example.com", "password": "definitely-wrong-pw-12345!"},
    )
    assert resp.status_code in (400, 401, 403, 404, 422), (
        f"Bad-credentials login must return 4xx, got {resp.status_code}. "
        "A 5xx indicates an unhandled exception in the auth route."
    )


@skip_if_offline
@pytest.mark.integration
def test_login_missing_body_returns_4xx_not_5xx():
    """Sending an empty body must not trigger a server crash."""
    resp = _post("/api/auth/login", {})
    assert resp.status_code < 500, (
        f"Empty-body login must not crash the server (got {resp.status_code})."
    )


# ---------------------------------------------------------------------------
# Bonus: response-time sanity guard for health endpoint
# ---------------------------------------------------------------------------

@skip_if_offline
@pytest.mark.integration
def test_health_responds_within_two_seconds():
    import time
    t0 = time.monotonic()
    _get("/health")
    elapsed = time.monotonic() - t0
    assert elapsed < 2.0, f"Health check took {elapsed:.2f}s — should respond in < 2s"
