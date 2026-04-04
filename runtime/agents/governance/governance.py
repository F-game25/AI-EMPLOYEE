"""Governance — Board Controls & Approval Gates for AI-EMPLOYEE.

Inspired by Paperclip's governance model (human "board" retains control),
this module provides:
  - Approval gates for high-impact agent actions
  - Board approve / reject / override for pending actions
  - Agent pause and terminate controls
  - Configurable risk thresholds (LOW/MEDIUM/HIGH) with auto-approve for LOW
  - Immutable governance audit trail
  - Action rollback support

Config:  ~/.ai-employee/config/governance.json
State:   ~/.ai-employee/state/governance.state.json
Audit:   ~/.ai-employee/state/governance.audit.jsonl

API (via problem-solver-ui server.py):
  GET  /api/governance/pending               — list pending approval requests
  GET  /api/governance/audit                 — full governance audit trail
  POST /api/governance/{id}/approve          — approve an action
  POST /api/governance/{id}/reject           — reject an action
  POST /api/governance/request               — agent submits action for approval
  POST /api/governance/pause/{agent_id}      — pause an agent
  POST /api/governance/resume/{agent_id}     — resume a paused agent
  POST /api/governance/terminate/{agent_id}  — terminate an agent
  GET  /api/governance/agent/{agent_id}      — get agent governance status
  POST /api/governance/settings              — update governance settings
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger("governance")

AI_HOME = Path(os.environ.get("AI_HOME", str(Path.home() / ".ai-employee")))
CONFIG_FILE = AI_HOME / "config" / "governance.json"
STATE_FILE = AI_HOME / "state" / "governance.state.json"
AUDIT_LOG = AI_HOME / "state" / "governance.audit.jsonl"

RISK_LEVELS = ("low", "medium", "high", "critical")
ACTION_STATES = ("pending", "approved", "rejected", "expired", "auto_approved")

# Default settings
DEFAULT_SETTINGS: dict = {
    "auto_approve_low": True,         # auto-approve LOW risk actions
    "require_approval_medium": True,  # require board approval for MEDIUM
    "require_approval_high": True,    # require board approval for HIGH
    "require_approval_critical": True,
    "approval_timeout_hours": 24,     # pending actions expire after this
    "notify_on_high": True,
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ── Config / State / Audit ────────────────────────────────────────────────────


def _load_settings() -> dict:
    if CONFIG_FILE.exists():
        try:
            data = json.loads(CONFIG_FILE.read_text())
            return {**DEFAULT_SETTINGS, **data}
        except Exception:
            pass
    return DEFAULT_SETTINGS.copy()


def _save_settings(settings: dict) -> None:
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(settings, indent=2))


def _load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {"pending": {}, "agent_status": {}}


def _save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = _now_iso()
    STATE_FILE.write_text(json.dumps(state, indent=2))


def _append_audit(event: dict) -> None:
    AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
    event["logged_at"] = _now_iso()
    with AUDIT_LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event) + "\n")


# ── Approval Gate ─────────────────────────────────────────────────────────────


def request_approval(
    agent_id: str,
    action: str,
    description: str,
    risk_level: str = "medium",
    payload: dict | None = None,
) -> dict:
    """An agent submits an action for board approval.

    If AUTO_APPROVE_LOW is set and risk_level is 'low', the action is
    auto-approved immediately.

    Returns the action record with its state.
    """
    if risk_level not in RISK_LEVELS:
        risk_level = "medium"

    settings = _load_settings()
    action_id = str(uuid.uuid4())[:12]
    now = _now_iso()

    record: dict = {
        "action_id": action_id,
        "agent_id": agent_id,
        "action": action,
        "description": description,
        "risk_level": risk_level,
        "payload": payload or {},
        "state": "pending",
        "requested_at": now,
        "decided_at": None,
        "decided_by": None,
        "decision_note": None,
    }

    # Auto-approve low risk if configured
    if risk_level == "low" and settings.get("auto_approve_low"):
        record["state"] = "auto_approved"
        record["decided_at"] = now
        record["decided_by"] = "system"
        record["decision_note"] = "Auto-approved (LOW risk)"
        _append_audit(
            {
                "event": "auto_approved",
                "action_id": action_id,
                "agent_id": agent_id,
                "action": action,
                "risk_level": risk_level,
            }
        )
        return record

    # Store as pending
    state = _load_state()
    state.setdefault("pending", {})[action_id] = record
    _save_state(state)

    _append_audit(
        {
            "event": "requested",
            "action_id": action_id,
            "agent_id": agent_id,
            "action": action,
            "risk_level": risk_level,
        }
    )
    return record


def approve_action(
    action_id: str,
    decided_by: str = "board",
    note: str = "",
) -> dict:
    """Board approves a pending action."""
    state = _load_state()
    pending = state.get("pending", {})
    record = pending.get(action_id)
    if record is None:
        raise ValueError(f"Action '{action_id}' not found in pending queue")
    record["state"] = "approved"
    record["decided_at"] = _now_iso()
    record["decided_by"] = decided_by
    record["decision_note"] = note
    del pending[action_id]
    state.setdefault("history", {})[action_id] = record
    _save_state(state)
    _append_audit(
        {
            "event": "approved",
            "action_id": action_id,
            "decided_by": decided_by,
            "note": note,
        }
    )
    return record


def reject_action(
    action_id: str,
    decided_by: str = "board",
    note: str = "",
) -> dict:
    """Board rejects a pending action."""
    state = _load_state()
    pending = state.get("pending", {})
    record = pending.get(action_id)
    if record is None:
        raise ValueError(f"Action '{action_id}' not found in pending queue")
    record["state"] = "rejected"
    record["decided_at"] = _now_iso()
    record["decided_by"] = decided_by
    record["decision_note"] = note
    del pending[action_id]
    state.setdefault("history", {})[action_id] = record
    _save_state(state)
    _append_audit(
        {
            "event": "rejected",
            "action_id": action_id,
            "decided_by": decided_by,
            "note": note,
        }
    )
    return record


def list_pending() -> list[dict]:
    """Return all pending approval requests sorted by requested_at."""
    state = _load_state()
    records = list(state.get("pending", {}).values())
    records.sort(key=lambda r: r.get("requested_at", ""), reverse=True)
    return records


def get_history(limit: int = 100) -> list[dict]:
    """Return recent governance decisions."""
    state = _load_state()
    records = list(state.get("history", {}).values())
    records.sort(key=lambda r: r.get("decided_at") or r.get("requested_at", ""), reverse=True)
    return records[:limit]


# ── Agent Pause / Terminate ───────────────────────────────────────────────────


def _set_agent_governance_status(agent_id: str, gov_status: str, reason: str = "") -> dict:
    state = _load_state()
    agent_statuses: dict = state.setdefault("agent_status", {})
    record: dict = {
        "agent_id": agent_id,
        "gov_status": gov_status,  # "active" | "paused" | "terminated"
        "reason": reason,
        "updated_at": _now_iso(),
    }
    agent_statuses[agent_id] = record
    _save_state(state)
    _append_audit(
        {
            "event": gov_status,
            "agent_id": agent_id,
            "reason": reason,
        }
    )
    return record


def pause_agent(agent_id: str, reason: str = "") -> dict:
    """Board pauses an agent — it will not accept new tasks."""
    return _set_agent_governance_status(agent_id, "paused", reason)


def resume_agent(agent_id: str, reason: str = "") -> dict:
    """Board resumes a paused agent."""
    return _set_agent_governance_status(agent_id, "active", reason)


def terminate_agent(agent_id: str, reason: str = "") -> dict:
    """Board terminates an agent — permanent stop."""
    return _set_agent_governance_status(agent_id, "terminated", reason)


def get_agent_gov_status(agent_id: str) -> dict:
    """Return governance status for an agent."""
    state = _load_state()
    return state.get("agent_status", {}).get(
        agent_id,
        {"agent_id": agent_id, "gov_status": "active"},
    )


def is_agent_allowed(agent_id: str) -> bool:
    """Return True if the agent is active (not paused/terminated)."""
    status = get_agent_gov_status(agent_id)
    return status.get("gov_status", "active") == "active"


# ── Settings ──────────────────────────────────────────────────────────────────


def get_settings() -> dict:
    return _load_settings()


def update_settings(updates: dict) -> dict:
    settings = _load_settings()
    for key in DEFAULT_SETTINGS:
        if key in updates:
            settings[key] = updates[key]
    _save_settings(settings)
    return settings


# ── Audit log ─────────────────────────────────────────────────────────────────


def get_audit_trail(limit: int = 200) -> list[dict]:
    """Return the most recent governance audit events.

    Uses a bounded deque (2× limit) to avoid loading the entire log file
    into memory, then returns the last `limit` valid events in chronological order.
    """
    if not AUDIT_LOG.exists():
        return []
    events: list[dict] = []
    try:
        tail: deque[str] = deque(maxlen=limit * 2)
        with AUDIT_LOG.open("r", encoding="utf-8") as fh:
            for line in fh:
                tail.append(line)
        for line in tail:
            if not line.strip():
                continue
            try:
                events.append(json.loads(line))
            except Exception:
                continue
        return events[-limit:]
    except Exception as exc:
        logger.warning("governance audit read error: %s", exc)
        return []
