"""Ticket System — Task Tracking with Audit Trail for AI-EMPLOYEE.

Inspired by Paperclip's ticket-based task model, every task in AI-EMPLOYEE
now creates an immutable ticket with:
  - Status tracking (open → in_progress → blocked → done / cancelled)
  - Thread of comments (append-only, immutable)
  - Full audit log of every status change and action
  - Tool-call tracing (what each agent did and why)
  - Integration with task-orchestrator (tickets created automatically)

State:  ~/.ai-employee/state/tickets/tickets.jsonl      (immutable append log)
Index:  ~/.ai-employee/state/tickets/index.json         (current ticket states)

API (via problem-solver-ui server.py):
  GET  /api/tickets                    — list tickets (with filters)
  POST /api/tickets                    — create a new ticket
  GET  /api/tickets/{id}               — get ticket with full thread
  PATCH /api/tickets/{id}              — update ticket (status, title, etc.)
  POST /api/tickets/{id}/comment       — add a comment to the thread
  GET  /api/tickets/{id}/audit         — full immutable audit trail
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger("ticket-system")

AI_HOME = Path(os.environ.get("AI_HOME", str(Path.home() / ".ai-employee")))
TICKETS_DIR = AI_HOME / "state" / "tickets"
TICKETS_LOG = TICKETS_DIR / "tickets.jsonl"   # immutable append-only audit log
INDEX_FILE = TICKETS_DIR / "index.json"        # mutable current-state index

VALID_STATUSES = ("open", "in_progress", "blocked", "done", "cancelled")
VALID_PRIORITIES = ("low", "medium", "high", "critical")


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _ensure_dirs() -> None:
    TICKETS_DIR.mkdir(parents=True, exist_ok=True)


# ── Audit log (immutable) ─────────────────────────────────────────────────────


def _append_audit(event: dict) -> None:
    """Append an event to the immutable audit log."""
    _ensure_dirs()
    event["logged_at"] = _now_iso()
    with TICKETS_LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event) + "\n")


# ── Index (current state) ─────────────────────────────────────────────────────


def _load_index() -> dict:
    _ensure_dirs()
    if INDEX_FILE.exists():
        try:
            return json.loads(INDEX_FILE.read_text())
        except Exception as exc:
            logger.warning("tickets index load error: %s", exc)
    return {"tickets": {}}


def _save_index(index: dict) -> None:
    _ensure_dirs()
    INDEX_FILE.write_text(json.dumps(index, indent=2))


def _get_ticket(ticket_id: str) -> dict | None:
    index = _load_index()
    return index["tickets"].get(ticket_id)


def _upsert_ticket(ticket: dict) -> None:
    index = _load_index()
    index["tickets"][ticket["ticket_id"]] = ticket
    _save_index(index)


# ── Public API ────────────────────────────────────────────────────────────────


def create_ticket(
    title: str,
    description: str = "",
    created_by: str = "user",
    agent_id: str | None = None,
    project_id: str | None = None,
    priority: str = "medium",
    task_plan_id: str | None = None,
) -> dict:
    """Create a new ticket and record it in the immutable log."""
    if priority not in VALID_PRIORITIES:
        priority = "medium"
    ticket_id = str(uuid.uuid4())[:8]
    now = _now_iso()
    ticket: dict = {
        "ticket_id": ticket_id,
        "title": title,
        "description": description,
        "status": "open",
        "priority": priority,
        "created_by": created_by,
        "agent_id": agent_id,
        "project_id": project_id,
        "task_plan_id": task_plan_id,
        "created_at": now,
        "updated_at": now,
        "comments": [],
    }
    _upsert_ticket(ticket)
    _append_audit(
        {
            "event": "created",
            "ticket_id": ticket_id,
            "title": title,
            "created_by": created_by,
            "status": "open",
        }
    )
    return ticket


def update_ticket(
    ticket_id: str,
    status: str | None = None,
    title: str | None = None,
    description: str | None = None,
    priority: str | None = None,
    agent_id: str | None = None,
    updated_by: str = "system",
) -> dict:
    """Update mutable fields on a ticket."""
    ticket = _get_ticket(ticket_id)
    if ticket is None:
        raise ValueError(f"Ticket '{ticket_id}' not found")

    changes: dict = {}
    if status is not None and status in VALID_STATUSES:
        changes["status"] = status
    if title is not None:
        changes["title"] = title
    if description is not None:
        changes["description"] = description
    if priority is not None and priority in VALID_PRIORITIES:
        changes["priority"] = priority
    if agent_id is not None:
        changes["agent_id"] = agent_id

    ticket.update(changes)
    ticket["updated_at"] = _now_iso()
    _upsert_ticket(ticket)

    _append_audit(
        {
            "event": "updated",
            "ticket_id": ticket_id,
            "updated_by": updated_by,
            "changes": changes,
        }
    )
    return ticket


def add_comment(
    ticket_id: str,
    body: str,
    author: str = "system",
    tool_call: dict | None = None,
) -> dict:
    """Append an immutable comment/tool-call trace to a ticket thread."""
    ticket = _get_ticket(ticket_id)
    if ticket is None:
        raise ValueError(f"Ticket '{ticket_id}' not found")

    comment: dict = {
        "comment_id": str(uuid.uuid4())[:8],
        "author": author,
        "body": body,
        "created_at": _now_iso(),
    }
    if tool_call:
        comment["tool_call"] = tool_call

    ticket.setdefault("comments", []).append(comment)
    ticket["updated_at"] = _now_iso()
    _upsert_ticket(ticket)

    _append_audit(
        {
            "event": "comment",
            "ticket_id": ticket_id,
            "author": author,
            "comment_id": comment["comment_id"],
        }
    )
    return comment


def get_ticket(ticket_id: str) -> dict | None:
    """Return a ticket with its full comment thread."""
    return _get_ticket(ticket_id)


def list_tickets(
    status: str | None = None,
    agent_id: str | None = None,
    project_id: str | None = None,
    limit: int = 50,
) -> list[dict]:
    """Return tickets filtered by optional criteria, newest first."""
    index = _load_index()
    tickets = list(index["tickets"].values())

    if status:
        tickets = [t for t in tickets if t.get("status") == status]
    if agent_id:
        tickets = [t for t in tickets if t.get("agent_id") == agent_id]
    if project_id:
        tickets = [t for t in tickets if t.get("project_id") == project_id]

    tickets.sort(key=lambda t: t.get("updated_at", ""), reverse=True)
    return tickets[:limit]


def get_audit_trail(ticket_id: str) -> list[dict]:
    """Return all audit events for a ticket from the immutable log."""
    if not TICKETS_LOG.exists():
        return []
    events = []
    try:
        for line in TICKETS_LOG.read_text().splitlines():
            if not line.strip():
                continue
            try:
                ev = json.loads(line)
                if ev.get("ticket_id") == ticket_id:
                    events.append(ev)
            except Exception:
                continue
    except Exception as exc:
        logger.warning("audit trail read error: %s", exc)
    return events


def get_full_audit_log(limit: int = 200) -> list[dict]:
    """Return the most recent audit events across all tickets."""
    if not TICKETS_LOG.exists():
        return []
    events: list[dict] = []
    try:
        # Use a deque to efficiently keep only the last N*2 lines without
        # loading the entire file into memory multiple times.
        tail: deque[str] = deque(maxlen=limit * 2)
        with TICKETS_LOG.open("r", encoding="utf-8") as fh:
            for line in fh:
                tail.append(line)
        for line in tail:
            if not line.strip():
                continue
            try:
                events.append(json.loads(line))
            except Exception:
                continue
        # Return the last `limit` events in chronological order
        return events[-limit:]
    except Exception as exc:
        logger.warning("full audit log read error: %s", exc)
        return []
