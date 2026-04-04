"""Org Chart — Agent Hierarchy & Reporting Structure for AI-EMPLOYEE.

Inspired by Paperclip's org-chart model, this module manages:
  - Role definitions (CEO, CTO, Developer, Marketing Lead, etc.)
  - Reporting lines (who reports to whom)
  - Job descriptions per role
  - Agent assignment to roles
  - Task delegation flowing up and down the org chart
  - Heartbeat-driven agent wake cycles
  - BYOA (Bring Your Own Agent) adapter registration

Config:  ~/.ai-employee/config/org_chart.json
State:   ~/.ai-employee/state/org-chart.state.json
Adapters:~/.ai-employee/config/agent_adapters.json

API (via problem-solver-ui server.py):
  GET  /api/org/chart              — full org chart
  POST /api/org/roles              — create/update a role
  DELETE /api/org/roles/{role_id}  — remove a role
  POST /api/org/assign             — assign an agent to a role
  POST /api/org/delegate           — delegate a task down the chain
  GET  /api/org/adapters           — list registered BYOA adapters
  POST /api/org/adapters           — register a new BYOA adapter
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("org-chart")

AI_HOME = Path(os.environ.get("AI_HOME", str(Path.home() / ".ai-employee")))
ORG_CHART_FILE = AI_HOME / "config" / "org_chart.json"
STATE_FILE = AI_HOME / "state" / "org-chart.state.json"
ADAPTERS_FILE = AI_HOME / "config" / "agent_adapters.json"

# ── Built-in role templates ───────────────────────────────────────────────────

DEFAULT_ROLES: list[dict] = [
    {
        "role_id": "ceo",
        "title": "Chief Executive Officer",
        "description": "Sets the company mission, approves top-level goals, and oversees the entire org.",
        "reports_to": None,
        "heartbeat_interval_minutes": 60,
        "agent_id": None,
    },
    {
        "role_id": "cto",
        "title": "Chief Technology Officer",
        "description": "Owns engineering roadmap, technical architecture, and all engineering agents.",
        "reports_to": "ceo",
        "heartbeat_interval_minutes": 60,
        "agent_id": None,
    },
    {
        "role_id": "cmo",
        "title": "Chief Marketing Officer",
        "description": "Owns brand, content, ads, and all creative/sales agents.",
        "reports_to": "ceo",
        "heartbeat_interval_minutes": 120,
        "agent_id": None,
    },
    {
        "role_id": "cfo",
        "title": "Chief Financial Officer",
        "description": "Owns budgets, financial analysis, and cost controls.",
        "reports_to": "ceo",
        "heartbeat_interval_minutes": 240,
        "agent_id": None,
    },
    {
        "role_id": "lead_engineer",
        "title": "Lead Engineer",
        "description": "Manages engineering-assistant, qa-tester, chatbot-builder agents.",
        "reports_to": "cto",
        "heartbeat_interval_minutes": 30,
        "agent_id": "engineering-assistant",
    },
    {
        "role_id": "lead_sales",
        "title": "Head of Sales",
        "description": "Manages cold-outreach-assassin, sales-closer-pro, appointment-setter agents.",
        "reports_to": "cmo",
        "heartbeat_interval_minutes": 30,
        "agent_id": "sales-closer-pro",
    },
    {
        "role_id": "lead_analyst",
        "title": "Head of Analytics",
        "description": "Manages finance-wizard, growth-hacker, conversion-rate-optimizer agents.",
        "reports_to": "cfo",
        "heartbeat_interval_minutes": 60,
        "agent_id": "finance-wizard",
    },
    {
        "role_id": "lead_research",
        "title": "Head of Research",
        "description": "Manages discovery, financial-deepsearch, partnership-matchmaker agents.",
        "reports_to": "cto",
        "heartbeat_interval_minutes": 120,
        "agent_id": "discovery",
    },
]

# ── Helpers ───────────────────────────────────────────────────────────────────


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_chart() -> dict:
    """Load org chart config, seeding defaults on first run."""
    if ORG_CHART_FILE.exists():
        try:
            return json.loads(ORG_CHART_FILE.read_text())
        except Exception as exc:
            logger.warning("org-chart load error: %s", exc)
    # Seed defaults
    chart = {"roles": DEFAULT_ROLES, "updated_at": _now_iso()}
    _save_chart(chart)
    return chart


def _save_chart(chart: dict) -> None:
    ORG_CHART_FILE.parent.mkdir(parents=True, exist_ok=True)
    chart["updated_at"] = _now_iso()
    ORG_CHART_FILE.write_text(json.dumps(chart, indent=2))


def _load_adapters() -> list:
    if ADAPTERS_FILE.exists():
        try:
            return json.loads(ADAPTERS_FILE.read_text())
        except Exception:
            pass
    return []


def _save_adapters(adapters: list) -> None:
    ADAPTERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    ADAPTERS_FILE.write_text(json.dumps(adapters, indent=2))


# ── Org Chart API ─────────────────────────────────────────────────────────────


def get_chart() -> dict:
    """Return the full org chart with role details."""
    chart = _load_chart()
    roles = chart.get("roles", [])
    # Build a parent→children map for convenience
    children: dict[str | None, list] = {}
    for role in roles:
        parent = role.get("reports_to")
        children.setdefault(parent, []).append(role["role_id"])
    # Annotate each role with its direct reports
    enriched = []
    for role in roles:
        enriched.append({**role, "direct_reports": children.get(role["role_id"], [])})
    return {"roles": enriched, "updated_at": chart.get("updated_at")}


def upsert_role(
    role_id: str,
    title: str,
    description: str,
    reports_to: str | None = None,
    heartbeat_interval_minutes: int = 60,
    agent_id: str | None = None,
) -> dict:
    """Create or update a role in the org chart."""
    chart = _load_chart()
    roles = chart.get("roles", [])
    existing = next((r for r in roles if r["role_id"] == role_id), None)
    if existing:
        existing.update(
            {
                "title": title,
                "description": description,
                "reports_to": reports_to,
                "heartbeat_interval_minutes": heartbeat_interval_minutes,
                "agent_id": agent_id,
            }
        )
        role = existing
    else:
        role = {
            "role_id": role_id,
            "title": title,
            "description": description,
            "reports_to": reports_to,
            "heartbeat_interval_minutes": heartbeat_interval_minutes,
            "agent_id": agent_id,
        }
        roles.append(role)
    chart["roles"] = roles
    _save_chart(chart)
    return role


def delete_role(role_id: str) -> bool:
    """Remove a role from the org chart."""
    chart = _load_chart()
    roles = chart.get("roles", [])
    original_len = len(roles)
    chart["roles"] = [r for r in roles if r["role_id"] != role_id]
    _save_chart(chart)
    return len(chart["roles"]) < original_len


def assign_agent_to_role(role_id: str, agent_id: str) -> dict:
    """Assign an AI-EMPLOYEE agent to a role."""
    chart = _load_chart()
    roles = chart.get("roles", [])
    role = next((r for r in roles if r["role_id"] == role_id), None)
    if not role:
        raise ValueError(f"Role '{role_id}' not found")
    role["agent_id"] = agent_id
    _save_chart(chart)
    return role


def delegate_task(
    from_role_id: str,
    to_role_id: str,
    task: str,
    context: dict | None = None,
) -> dict:
    """Record a delegation of a task from one role to another.

    Returns a delegation record.  The actual task submission is handled by
    the caller (e.g., problem-solver-ui server.py) which forwards the task
    to the receiving agent's queue.
    """
    chart = _load_chart()
    roles = chart.get("roles", [])
    from_role = next((r for r in roles if r["role_id"] == from_role_id), None)
    to_role = next((r for r in roles if r["role_id"] == to_role_id), None)
    if not from_role:
        raise ValueError(f"Delegating role '{from_role_id}' not found")
    if not to_role:
        raise ValueError(f"Receiving role '{to_role_id}' not found")

    delegation = {
        "delegation_id": str(uuid.uuid4())[:8],
        "from_role": from_role_id,
        "to_role": to_role_id,
        "to_agent": to_role.get("agent_id"),
        "task": task,
        "context": context or {},
        "created_at": _now_iso(),
    }

    # Persist delegation log
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    state: dict = {}
    if STATE_FILE.exists():
        try:
            state = json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    delegations: list = state.get("delegations", [])
    delegations.append(delegation)
    state["delegations"] = delegations[-200:]  # keep last 200
    state["updated_at"] = _now_iso()
    STATE_FILE.write_text(json.dumps(state, indent=2))

    return delegation


# ── BYOA Adapter Registry ─────────────────────────────────────────────────────


def list_adapters() -> list:
    """Return all registered BYOA agent adapters."""
    return _load_adapters()


def register_adapter(
    adapter_id: str,
    name: str,
    adapter_type: str,  # "http_webhook" | "cli" | "queue"
    config: dict,
    description: str = "",
) -> dict:
    """Register a new Bring-Your-Own-Agent adapter.

    adapter_type:
      "http_webhook" — agent is reached via HTTP POST to config["url"]
      "cli"          — agent is invoked via config["command"] shell command
      "queue"        — agent reads from a JSONL queue file at config["queue_path"]
    """
    if adapter_type not in ("http_webhook", "cli", "queue"):
        raise ValueError(f"Unknown adapter_type: {adapter_type!r}")

    adapters = _load_adapters()
    # Remove existing entry with same ID
    adapters = [a for a in adapters if a.get("adapter_id") != adapter_id]
    adapter: dict[str, Any] = {
        "adapter_id": adapter_id,
        "name": name,
        "type": adapter_type,
        "description": description,
        "config": config,
        "registered_at": _now_iso(),
    }
    adapters.append(adapter)
    _save_adapters(adapters)
    return adapter


def deregister_adapter(adapter_id: str) -> bool:
    adapters = _load_adapters()
    original = len(adapters)
    _save_adapters([a for a in adapters if a.get("adapter_id") != adapter_id])
    return len(_load_adapters()) < original


# ── Heartbeat scheduler ───────────────────────────────────────────────────────


def get_due_heartbeats(state: dict | None = None) -> list[dict]:
    """Return roles whose heartbeat is due right now.

    state: dict mapping role_id → last_heartbeat_ts (float).
           Defaults to loading from STATE_FILE.
    """
    if state is None:
        if STATE_FILE.exists():
            try:
                saved = json.loads(STATE_FILE.read_text())
                state = saved.get("last_heartbeats", {})
            except Exception:
                state = {}
        else:
            state = {}

    chart = _load_chart()
    now = time.time()
    due = []
    for role in chart.get("roles", []):
        if not role.get("agent_id"):
            continue
        interval_s = role.get("heartbeat_interval_minutes", 60) * 60
        last = state.get(role["role_id"], 0)
        if now - last >= interval_s:
            due.append(role)
    return due


def record_heartbeat(role_id: str) -> None:
    """Update the last heartbeat timestamp for a role."""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    state: dict = {}
    if STATE_FILE.exists():
        try:
            state = json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    heartbeats = state.get("last_heartbeats", {})
    heartbeats[role_id] = time.time()
    state["last_heartbeats"] = heartbeats
    state["updated_at"] = _now_iso()
    STATE_FILE.write_text(json.dumps(state, indent=2))
