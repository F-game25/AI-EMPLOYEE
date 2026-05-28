"""Shared pytest fixtures for the AI Employee test suite.

These fixtures ensure that tests run in complete isolation — each test gets a
fresh temporary directory for state files so nothing leaks between runs and no
live installation is required.
"""
from __future__ import annotations

import os
import sys
import importlib
import importlib.util
import time
import uuid
from pathlib import Path

import pytest

os.environ["JWT_SECRET_KEY"] = "ci-test-jwt-secret-for-isolated-pytest-runs-only-32bytes"

# ── Make runtime packages importable from any test ───────────────────────────
_RUNTIME_DIR = Path(__file__).parent.parent / "runtime"
if str(_RUNTIME_DIR) not in sys.path:
    sys.path.insert(0, str(_RUNTIME_DIR))

_AGENTS_DIR = Path(__file__).parent.parent / "runtime" / "agents"
if str(_AGENTS_DIR) not in sys.path:
    sys.path.insert(1, str(_AGENTS_DIR))


def _install_testclient_auth_header() -> None:
    """Attach a valid zero-trust/tenant JWT to TestClient API calls by default."""
    try:
        import jwt
        from starlette.testclient import TestClient
    except Exception:
        return

    if getattr(TestClient, "_ai_employee_auth_patched", False):
        return

    original_request = TestClient.request

    def request_with_default_auth(self, method, url, *args, **kwargs):
        headers = dict(kwargs.pop("headers", {}) or {})
        has_auth = any(str(key).lower() == "authorization" for key in headers)
        if str(url).startswith("/api/") and not str(url).startswith("/api/auth/") and not has_auth:
            now = int(time.time())
            token = jwt.encode(
                {
                    "sub": "pytest-user",
                    "role": "admin",
                    "tenant_id": "test-tenant",
                    "org_name": "Pytest",
                    "email": "pytest@example.com",
                    "iat": now,
                    "exp": now + 600,
                    "jti": str(uuid.uuid4()),
                    "type": "access",
                },
                os.environ["JWT_SECRET_KEY"],
                algorithm="HS256",
            )
            headers["Authorization"] = f"Bearer {token}"
        return original_request(self, method, url, *args, headers=headers, **kwargs)

    TestClient.request = request_with_default_auth
    TestClient._ai_employee_auth_patched = True


_install_testclient_auth_header()

def _pin_runtime_core_module(name: str) -> None:
    """Load selected runtime/core modules ahead of similarly named packages."""
    module_name = f"core.{name}"
    module_path = _RUNTIME_DIR / "core" / f"{name}.py"
    if not module_path.exists():
        return

    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec and spec.loader:
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        try:
            core_pkg = importlib.import_module("core")
            setattr(core_pkg, name, module)
        except Exception:
            pass


for _module_name in (
    "state_paths",
    "bus",
    "cost_ledger",
    "model_routing",
    "phase_reporter",
    "wavefield_provider",
    "hitl_gate",
    "contracts",
    "knowledge_store",
    "memory_index",
    "learning_engine",
    "planner",
    "orchestrator",
    "task_log_store",
    "agent_controller",
    "task_engine",
):
    _pin_runtime_core_module(_module_name)


@pytest.fixture(autouse=True)
def isolated_ai_home(tmp_path, monkeypatch):
    """Redirect AI_HOME to a fresh tmp directory for every test.

    This prevents any test from reading or writing to ~/.ai-employee and
    ensures test runs are fully reproducible.
    """
    fake_home = tmp_path / "ai-employee"
    fake_home.mkdir(parents=True)
    (fake_home / "agents").mkdir()
    (fake_home / "state").mkdir()

    monkeypatch.setenv("AI_HOME", str(fake_home))
    monkeypatch.setenv("AUTO_RESEARCH_MODE", "off")
    # Patch the module-level constants that were already bound at import time
    # for ascend_forge and turbo_quant.
    for mod_name in ("ascend_forge", "turbo_quant"):
        mod = sys.modules.get(mod_name)
        if mod is not None:
            for attr in ("AI_HOME", "STATE_DIR", "STATE_FILE", "CHANGELOG_FILE"):
                if hasattr(mod, attr):
                    original = getattr(mod, attr)
                    new_val = fake_home / str(original).replace(
                        str(Path.home() / ".ai-employee"), ""
                    ).lstrip("/")
                    try:
                        setattr(mod, attr, new_val)
                    except AttributeError:
                        pass

    return fake_home


@pytest.fixture()
def agents_dir(isolated_ai_home):
    """Return the fake agents directory path."""
    return isolated_ai_home / "agents"


@pytest.fixture()
def state_dir(isolated_ai_home):
    """Return the fake state directory path."""
    return isolated_ai_home / "state"
