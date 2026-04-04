"""Session Manager — Persistent Agent Sessions Across Reboots for AI-EMPLOYEE.

One of Paperclip's key selling points: "Tasks are ticket-based, conversations
are threaded, sessions persist across reboots."

This module saves every agent's active task context to disk so that on restart
agents can resume exactly where they left off, not restart from scratch.

State:  ~/.ai-employee/state/sessions/<session_id>.json
Index:  ~/.ai-employee/state/sessions/index.json

API (via problem-solver-ui server.py):
  GET  /api/sessions                     — list all active sessions
  GET  /api/sessions/{id}                — get session details + context
  POST /api/sessions                     — create / resume a session
  PATCH /api/sessions/{id}               — update session context / status
  DELETE /api/sessions/{id}              — close a session
  POST /api/sessions/{id}/checkpoint     — save a checkpoint for the session
  GET  /api/sessions/{id}/checkpoints    — list checkpoints (resume points)
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger("session-manager")

AI_HOME = Path(os.environ.get("AI_HOME", str(Path.home() / ".ai-employee")))
SESSIONS_DIR = AI_HOME / "state" / "sessions"
INDEX_FILE = SESSIONS_DIR / "index.json"

VALID_STATUSES = ("active", "paused", "completed", "abandoned")


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _ensure_dirs() -> None:
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)


# ── Index ─────────────────────────────────────────────────────────────────────


def _load_index() -> dict:
    _ensure_dirs()
    if INDEX_FILE.exists():
        try:
            return json.loads(INDEX_FILE.read_text())
        except Exception:
            pass
    return {"sessions": {}}


def _save_index(index: dict) -> None:
    _ensure_dirs()
    INDEX_FILE.write_text(json.dumps(index, indent=2))


def _session_file(session_id: str) -> Path:
    return SESSIONS_DIR / f"{session_id}.json"


def _load_session(session_id: str) -> dict | None:
    f = _session_file(session_id)
    if f.exists():
        try:
            return json.loads(f.read_text())
        except Exception:
            pass
    return None


def _save_session(session: dict) -> None:
    _ensure_dirs()
    session["updated_at"] = _now_iso()
    _session_file(session["session_id"]).write_text(json.dumps(session, indent=2))
    # Update index
    index = _load_index()
    index["sessions"][session["session_id"]] = {
        "session_id": session["session_id"],
        "agent_id": session.get("agent_id"),
        "title": session.get("title"),
        "status": session.get("status"),
        "created_at": session.get("created_at"),
        "updated_at": session.get("updated_at"),
        "ticket_id": session.get("ticket_id"),
        "task_plan_id": session.get("task_plan_id"),
    }
    _save_index(index)


# ── Public API ────────────────────────────────────────────────────────────────


def create_session(
    agent_id: str,
    title: str = "",
    context: dict | None = None,
    ticket_id: str | None = None,
    task_plan_id: str | None = None,
    company_id: str | None = None,
) -> dict:
    """Create a new persistent session for an agent.

    The session stores the agent's working context (goals, in-progress task,
    conversation history, etc.) so it can be restored on reboot.
    """
    session_id = str(uuid.uuid4())[:12]
    now = _now_iso()
    session: dict = {
        "session_id": session_id,
        "agent_id": agent_id,
        "title": title or f"{agent_id} session {now[:10]}",
        "status": "active",
        "context": context or {},
        "checkpoints": [],
        "ticket_id": ticket_id,
        "task_plan_id": task_plan_id,
        "company_id": company_id,
        "created_at": now,
        "updated_at": now,
        "last_resumed_at": None,
    }
    _save_session(session)
    logger.info("session-manager: created session %s for agent %s", session_id, agent_id)
    return session


def get_session(session_id: str) -> dict | None:
    return _load_session(session_id)


def list_sessions(
    agent_id: str | None = None,
    status: str | None = None,
    limit: int = 50,
) -> list[dict]:
    """Return sessions from the index, optionally filtered."""
    index = _load_index()
    sessions = list(index["sessions"].values())
    if agent_id:
        sessions = [s for s in sessions if s.get("agent_id") == agent_id]
    if status:
        sessions = [s for s in sessions if s.get("status") == status]
    sessions.sort(key=lambda s: s.get("updated_at", ""), reverse=True)
    return sessions[:limit]


def update_session(
    session_id: str,
    context: dict | None = None,
    status: str | None = None,
    title: str | None = None,
    merge_context: bool = True,
) -> dict:
    """Update a session's context or status.

    If merge_context=True (default), the provided context is merged with
    the existing context rather than replacing it.  This lets agents append
    new state without wiping previous state.
    """
    session = _load_session(session_id)
    if session is None:
        raise ValueError(f"Session '{session_id}' not found")

    if status is not None and status in VALID_STATUSES:
        session["status"] = status
    if title is not None:
        session["title"] = title
    if context is not None:
        if merge_context:
            existing = session.get("context", {})
            existing.update(context)
            session["context"] = existing
        else:
            session["context"] = context

    _save_session(session)
    return session


def resume_session(session_id: str) -> dict:
    """Mark a session as resumed (updates last_resumed_at + status)."""
    session = _load_session(session_id)
    if session is None:
        raise ValueError(f"Session '{session_id}' not found")
    session["status"] = "active"
    session["last_resumed_at"] = _now_iso()
    _save_session(session)
    return session


def close_session(session_id: str) -> bool:
    """Mark a session as completed and remove it from the active index."""
    session = _load_session(session_id)
    if session is None:
        return False
    session["status"] = "completed"
    _save_session(session)
    return True


def save_checkpoint(
    session_id: str,
    label: str,
    snapshot: dict | None = None,
) -> dict:
    """Save a named checkpoint for a session.

    Checkpoints are named resume points — the agent can be restored to any
    checkpoint if something goes wrong, providing rollback capability.
    """
    session = _load_session(session_id)
    if session is None:
        raise ValueError(f"Session '{session_id}' not found")

    checkpoint: dict = {
        "checkpoint_id": str(uuid.uuid4())[:8],
        "label": label,
        "created_at": _now_iso(),
        "context_snapshot": snapshot or session.get("context", {}),
    }
    session.setdefault("checkpoints", []).append(checkpoint)
    # Keep last 20 checkpoints
    session["checkpoints"] = session["checkpoints"][-20:]
    _save_session(session)
    return checkpoint


def list_checkpoints(session_id: str) -> list[dict]:
    session = _load_session(session_id)
    if session is None:
        return []
    return session.get("checkpoints", [])


def restore_checkpoint(session_id: str, checkpoint_id: str) -> dict:
    """Restore a session's context to a specific checkpoint (rollback)."""
    session = _load_session(session_id)
    if session is None:
        raise ValueError(f"Session '{session_id}' not found")
    checkpoints = session.get("checkpoints", [])
    cp = next((c for c in checkpoints if c["checkpoint_id"] == checkpoint_id), None)
    if cp is None:
        raise ValueError(f"Checkpoint '{checkpoint_id}' not found in session '{session_id}'")
    session["context"] = cp.get("context_snapshot", {})
    session["status"] = "active"
    _save_session(session)
    return session


def get_or_create_session(
    agent_id: str,
    task_plan_id: str | None = None,
) -> dict:
    """Return an existing active session for an agent, or create one.

    This is the main entry point for agents — call it at startup to
    resume a previous session rather than starting from scratch.
    """
    # Look for an existing active session for this agent+task
    sessions = list_sessions(agent_id=agent_id, status="active", limit=1)
    if task_plan_id:
        sessions = [s for s in sessions if s.get("task_plan_id") == task_plan_id]
    if sessions:
        # Resume the most recent active session
        return resume_session(sessions[0]["session_id"])
    # Create fresh session
    return create_session(agent_id=agent_id, task_plan_id=task_plan_id)
