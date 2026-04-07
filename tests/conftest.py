"""Shared pytest fixtures for the AI Employee test suite.

These fixtures ensure that tests run in complete isolation — each test gets a
fresh temporary directory for state files so nothing leaks between runs and no
live installation is required.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

# ── Make runtime/agents importable from any test ─────────────────────────────
_AGENTS_DIR = Path(__file__).parent.parent / "runtime" / "agents"
if str(_AGENTS_DIR) not in sys.path:
    sys.path.insert(0, str(_AGENTS_DIR))


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
