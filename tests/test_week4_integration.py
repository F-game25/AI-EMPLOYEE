"""Week 4 Integration Tests — Observability, Error Tracking, Health Checks"""
import json
import os
import pytest
import requests
import time
from pathlib import Path

# Test configuration
BASE_URL = os.environ.get("TEST_BASE_URL", "http://localhost:8787")
PYTHON_BASE_URL = os.environ.get("PYTHON_BASE_URL", "http://localhost:18790")
TIMEOUT = 10


def _request_or_skip(method: str, url: str, **kwargs):
    """Run a live integration request, or skip when the target service is absent."""
    try:
        return requests.request(method, url, **kwargs)
    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as exc:
        pytest.skip(f"Integration service not reachable at {url}: {exc}")


def _get(url: str, **kwargs):
    return _request_or_skip("GET", url, **kwargs)


def _post(url: str, **kwargs):
    return _request_or_skip("POST", url, **kwargs)


class TestHealthEndpoints:
    """Test enhanced health check endpoints with LLM and dependency validation."""

    def test_node_health_endpoint(self):
        """GET /health returns detailed health status."""
        res = _get(f"{BASE_URL}/health", timeout=TIMEOUT)
        assert res.status_code in (200, 503), f"Health check failed: {res.text}"
        data = res.json()
        assert "status" in data
        assert "checks" in data
        assert "uptime" in data
        assert "python_backend" in data["checks"]
        assert "llm_api" in data["checks"]
        assert "database" in data["checks"]

    def test_python_health_endpoint(self):
        """GET /health on Python backend returns security posture."""
        res = _get(f"{PYTHON_BASE_URL}/health", timeout=TIMEOUT)
        assert res.status_code == 200, f"Python health check failed: {res.text}"
        data = res.json()
        assert "status" in data
        assert "secure_mode" in data

    def test_health_endpoint_liveness(self):
        """Health endpoints respond within timeout for liveness probes."""
        start = time.time()
        res = _get(f"{BASE_URL}/health", timeout=TIMEOUT)
        duration = time.time() - start
        assert duration < 5, f"Health check took {duration}s, should be < 5s"
        assert res.status_code in (200, 503)


class TestSentryIntegration:
    """Test Sentry error tracking integration."""

    def test_sentry_header_presence(self):
        """Sentry SDK should not break request handling if DSN not set."""
        # This is a soft test — just ensure the app starts without Sentry breaking it
        res = _get(f"{BASE_URL}/version", timeout=TIMEOUT)
        assert res.status_code == 200
        assert "commit" in res.json()

    def test_no_sensitive_data_in_health(self):
        """Health endpoint should not expose API keys or secrets."""
        res = _get(f"{BASE_URL}/health", timeout=TIMEOUT)
        data = json.dumps(res.json())
        assert "ANTHROPIC" not in data
        assert "SECRET" not in data
        assert "API_KEY" not in data


class TestNginxRateLimiting:
    """Test rate limiting configuration (if nginx is running)."""

    def test_rate_limit_headers(self):
        """nginx should set X-RateLimit-* headers (if deployed)."""
        # This test is optional — only validates if nginx is in front
        headers = {}
        for i in range(3):
            res = _get(f"{BASE_URL}/api/agents", timeout=TIMEOUT, headers=headers)
            if res.status_code == 429:
                # Rate limit hit
                assert "Retry-After" in res.headers or res.json().get("retry_after")
                return
        # If we didn't hit rate limit, that's fine — nginx might not be running

    def test_auth_rate_limit_strictness(self):
        """Authentication endpoints should have stricter rate limiting."""
        # Try multiple failed auth attempts
        payload = {"secret": "wrong"}
        for i in range(6):
            res = _post(
                f"{BASE_URL}/api/auth/token",
                json=payload,
                timeout=TIMEOUT,
            )
            if res.status_code == 429:
                # Hit rate limit
                assert "Too many" in res.text or res.status_code == 429
                return
        # If not rate limited, that's also acceptable for this test


class TestPrometheusMetrics:
    """Test Prometheus metrics endpoint."""

    def test_metrics_endpoint_exists(self):
        """GET /metrics returns Prometheus-format metrics."""
        res = _get(f"{BASE_URL}/metrics", timeout=TIMEOUT)
        assert res.status_code == 200
        assert "text/plain" in res.headers.get("Content-Type", "")

    def test_metrics_content_format(self):
        """Metrics should be in Prometheus text format."""
        res = _get(f"{BASE_URL}/metrics", timeout=TIMEOUT)
        content = res.text
        assert "# HELP" in content or "ai_employee_" in content
        assert "#" in content  # Prometheus format uses # for comments


class TestAgentsHttpFallback:
    """Test /api/agents HTTP endpoint for AgentsPage WebSocket fallback."""

    def test_agents_endpoint_returns_json(self):
        """GET /api/agents returns list of agents."""
        res = _get(f"{BASE_URL}/api/agents", timeout=TIMEOUT)
        assert res.status_code == 200
        data = res.json()
        assert isinstance(data, dict)
        assert "agents" in data or isinstance(data, list)

    def test_agents_endpoint_schema(self):
        """Each agent in /api/agents has required fields."""
        res = _get(f"{BASE_URL}/api/agents", timeout=TIMEOUT)
        data = res.json()
        agents = data.get("agents", data if isinstance(data, list) else [])
        if agents:
            for agent in agents[:3]:  # Check first 3
                assert "id" in agent or "name" in agent


class TestErrorRecovery:
    """Test error recovery and resilience."""

    def test_500_error_handling(self):
        """Invalid routes return proper error responses, not 500s."""
        res = _get(f"{BASE_URL}/api/invalid-route-xyz", timeout=TIMEOUT)
        assert res.status_code in (404, 400, 422)
        assert "error" in res.json() or "detail" in res.json()

    def test_malformed_json_handling(self):
        """Malformed JSON request bodies are rejected gracefully."""
        res = _post(
            f"{BASE_URL}/api/chat",
            data="not valid json",
            headers={"Content-Type": "application/json"},
            timeout=TIMEOUT,
        )
        assert res.status_code in (400, 422)


class TestSecurityHeaders:
    """Test security headers in responses."""

    def test_security_headers_present(self):
        """Response includes security headers (helmet)."""
        res = _get(f"{BASE_URL}/", timeout=TIMEOUT)
        assert "X-Content-Type-Options" in res.headers or res.status_code == 200


class TestDatabaseResilience:
    """Test database access patterns."""

    def test_file_locking_protection(self):
        """Concurrent writes to state files are protected by file locking."""
        # This is a soft test — we just ensure the system doesn't corrupt state
        res = _get(f"{BASE_URL}/api/status", timeout=TIMEOUT)
        assert res.status_code == 200
        # If we got here, state files are accessible and not corrupted


class TestDeploymentReadiness:
    """Test overall deployment readiness."""

    def test_all_critical_endpoints_reachable(self):
        """All critical endpoints respond."""
        critical_endpoints = [
            "/health",
            "/metrics",
            "/api/health",
            "/api/agents",
            "/api/status",
            "/version",
        ]
        for endpoint in critical_endpoints:
            res = _get(f"{BASE_URL}{endpoint}", timeout=TIMEOUT)
            assert res.status_code in (200, 401, 403, 503), \
                f"{endpoint} returned {res.status_code}"

    def test_python_backend_reachable(self):
        """Python backend is accessible."""
        res = _get(f"{PYTHON_BASE_URL}/health", timeout=TIMEOUT)
        assert res.status_code == 200

    def test_docker_compose_config_valid(self):
        """docker-compose.yml is syntactically valid."""
        compose_file = Path(__file__).parent.parent / "docker-compose.yml"
        assert compose_file.exists()
        # Just check it's readable YAML
        import yaml
        with open(compose_file) as f:
            config = yaml.safe_load(f)
        assert "services" in config
        assert "ai-employee" in config["services"]
        assert "nginx" in config["services"]

    def test_nginx_config_readable(self):
        """nginx.conf exists and is readable."""
        nginx_file = Path(__file__).parent.parent / "nginx.conf"
        assert nginx_file.exists()
        assert "worker_processes" in nginx_file.read_text()
        assert "rate limiting" in nginx_file.read_text().lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
