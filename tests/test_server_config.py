"""Tests for server.py configuration correctness.

Validates agent count constants, mode lists, and agent_capabilities.json
stay in sync so "56 agents" / "73 agents" drift never goes undetected.
"""
from __future__ import annotations

import importlib
import json
import re
import sys
from pathlib import Path

import pytest

# ── Paths ─────────────────────────────────────────────────────────────────────

_REPO_ROOT = Path(__file__).parent.parent
_SERVER_PY = _REPO_ROOT / "runtime" / "agents" / "problem-solver-ui" / "server.py"
_AGENT_CAPS = _REPO_ROOT / "runtime" / "config" / "agent_capabilities.json"

_SERVER_SRC: str = _SERVER_PY.read_text()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _extract_power_agents() -> list[str]:
    """Parse the AGENTS_BY_MODE['power'] list from server.py without executing it."""
    m = re.search(r'"power"\s*:\s*\[(.*?)\]', _SERVER_SRC, re.DOTALL)
    assert m, "Could not find AGENTS_BY_MODE['power'] in server.py"
    return re.findall(r'"([\w-]+)"', m.group(1))


def _extract_js_constant(name: str) -> int:
    """Extract a JS numeric constant like `const FOO = 74;` from server.py."""
    m = re.search(rf'const\s+{re.escape(name)}\s*=\s*(\d+)', _SERVER_SRC)
    assert m, f"JS constant {name!r} not found in server.py"
    return int(m.group(1))


# ══════════════════════════════════════════════════════════════════════════════
# Agent count consistency
# ══════════════════════════════════════════════════════════════════════════════

class TestAgentCountConsistency:
    """All agent-count constants must agree with the actual power-mode list."""

    def test_power_mode_list_length(self):
        agents = _extract_power_agents()
        assert len(agents) == 74, (
            f"Power mode has {len(agents)} agents, expected 74. "
            "Update AGENTS_BY_MODE or these tests."
        )

    def test_power_mode_no_duplicates(self):
        agents = _extract_power_agents()
        assert len(agents) == len(set(agents)), (
            "Duplicate agent names in power mode: "
            + str([a for a in agents if agents.count(a) > 1])
        )

    def test_max_agents_total_js_constant(self):
        val = _extract_js_constant("MAX_AGENTS_TOTAL")
        agents = _extract_power_agents()
        assert val == len(agents), (
            f"MAX_AGENTS_TOTAL={val} does not match actual power agent count "
            f"{len(agents)}."
        )

    def test_mode_capacity_power_js(self):
        m = re.search(r'modeCapacity\s*=\s*\{[^}]*power\s*:\s*(\d+)', _SERVER_SRC)
        assert m, "modeCapacity.power not found in server.py"
        cap = int(m.group(1))
        agents = _extract_power_agents()
        assert cap == len(agents), (
            f"modeCapacity.power={cap} does not match power agent count {len(agents)}."
        )

    def test_boot_sequence_agent_count(self):
        m = re.search(r'\[AGNT\]\s+(\d+) agents registered', _SERVER_SRC)
        assert m, "Boot sequence agent count line not found in server.py"
        boot_count = int(m.group(1))
        agents = _extract_power_agents()
        assert boot_count == len(agents), (
            f"Boot sequence says {boot_count} but actual count is {len(agents)}."
        )

    def test_chat_help_agent_count(self):
        """The 'agents — list all N AI agents' help string must be current."""
        m = re.search(r'list all (\d+) AI agents', _SERVER_SRC)
        assert m, "'list all N AI agents' not found in server.py"
        count = int(m.group(1))
        agents = _extract_power_agents()
        assert count == len(agents), (
            f"Chat help string says {count} but actual count is {len(agents)}."
        )

    def test_chat_response_agent_count(self):
        """The 'Switch to power mode to run all N agents' response must be current."""
        m = re.search(r'run all (\d+) agents', _SERVER_SRC)
        assert m, "'run all N agents' message not found in server.py"
        count = int(m.group(1))
        agents = _extract_power_agents()
        assert count == len(agents), (
            f"Chat response says {count} agents but actual count is {len(agents)}."
        )

    def test_agent_capabilities_json_total(self):
        """agent_capabilities.json total_agents must match the power mode list."""
        with _AGENT_CAPS.open() as f:
            caps = json.load(f)
        total = caps.get("_meta", {}).get("total_agents")
        assert total is not None, "total_agents not found in agent_capabilities.json"
        agents = _extract_power_agents()
        assert total == len(agents), (
            f"agent_capabilities.json total_agents={total} but power list has "
            f"{len(agents)} agents."
        )


# ══════════════════════════════════════════════════════════════════════════════
# Polling guards
# ══════════════════════════════════════════════════════════════════════════════

class TestPollingGuards:
    """Polling intervals must include document.hidden checks to avoid wasted requests."""

    def test_dashboard_setinterval_has_hidden_guard(self):
        m = re.search(
            r"setInterval\s*\(\s*\(\)\s*=>\s*\{[^}]*document\.hidden[^}]*loadDashboard",
            _SERVER_SRC,
        )
        assert m, "Dashboard setInterval should guard with document.hidden"

    def test_ascend_setinterval_has_hidden_guard(self):
        m = re.search(
            r"setInterval\s*\(\s*\(\)\s*=>\s*\{[^}]*document\.hidden[^}]*ascend",
            _SERVER_SRC,
        )
        assert m, "Ascend Forge setInterval should guard with document.hidden"

    def test_tab_refresh_setinterval_has_hidden_guard(self):
        # The 30s multi-tab refresh interval must have a document.hidden guard
        m = re.search(
            r"Auto-refresh new tabs.*\n.*setInterval.*\n.*document\.hidden",
            _SERVER_SRC,
        )
        assert m, "Multi-tab refresh setInterval should guard with document.hidden"


# ══════════════════════════════════════════════════════════════════════════════
# No fake CPU simulation
# ══════════════════════════════════════════════════════════════════════════════

class TestNoFakeCpuSimulation:
    """startStatsUpdater() must not randomly walk _fakeCpu/_fakeMem for fake metrics."""

    def test_no_fake_random_walk_simulation(self):
        # The old pattern was: _fakeCpu += (Math.random() - 0.45) * 6
        # and:                  _fakeMem += (Math.random() - 0.45) * 3
        assert "Math.random() - 0.45" not in _SERVER_SRC, (
            "Fake CPU/RAM random-walk simulation found in startStatsUpdater(). "
            "This was removed; real metrics come from /api/system/resources."
        )

    def test_stats_updater_no_fake_mem_bar_update(self):
        # The old pattern pushed fake memory into the sidebar: updateStatBar('sb-mem', 'sv-mem', _fakeMem, ...)
        # Real RAM is now updated only by loadSysRes() which uses psutil.
        assert "_fakeMem, Math.round(_fakeMem)" not in _SERVER_SRC, (
            "startStatsUpdater() must not update the memory bar with fake data."
        )
