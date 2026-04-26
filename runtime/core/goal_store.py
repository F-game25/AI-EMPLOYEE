"""Goal persistence — tracks active goals across restarts.

Goals survive process restarts so the execution loop can resume incomplete work.

Schema: goals(goal_id, message, goal_type, status, task_plan, results,
              created_at, updated_at, completed_at)
"""
from __future__ import annotations

import json
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any

_AI_HOME = Path(__file__).resolve().parent.parent.parent.parent / ".ai-employee"
if not _AI_HOME.exists():
    import os
    _AI_HOME = Path(os.environ.get("AI_HOME", Path.home() / ".ai-employee"))

_DB_PATH = _AI_HOME / "state" / "goals.db"

_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS goals (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    goal_id      TEXT UNIQUE NOT NULL,
    message      TEXT NOT NULL,
    goal_type    TEXT NOT NULL DEFAULT 'general',
    status       TEXT NOT NULL DEFAULT 'pending',
    task_plan    TEXT NOT NULL DEFAULT '[]',
    results      TEXT NOT NULL DEFAULT 'null',
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL,
    completed_at TEXT
);
"""


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _conn() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(_DB_PATH))
    c.execute("PRAGMA journal_mode=WAL")
    c.row_factory = sqlite3.Row
    c.execute(_CREATE_SQL)
    return c


class GoalStore:
    """SQLite-backed goal tracker — create, update, resume, list goals."""

    def create(self, message: str, goal_type: str, task_plan: list[dict]) -> str:
        """Persist a new goal. Returns goal_id."""
        goal_id = f"goal-{uuid.uuid4().hex[:8]}"
        now = _now()
        with _conn() as conn:
            conn.execute(
                """INSERT INTO goals (goal_id, message, goal_type, status, task_plan,
                                      results, created_at, updated_at)
                   VALUES (?, ?, ?, 'pending', ?, 'null', ?, ?)""",
                (goal_id, message, goal_type, json.dumps(task_plan), now, now),
            )
        return goal_id

    def start(self, goal_id: str) -> None:
        with _conn() as conn:
            conn.execute(
                "UPDATE goals SET status='running', updated_at=? WHERE goal_id=?",
                (_now(), goal_id),
            )

    def complete(self, goal_id: str, results: Any) -> None:
        now = _now()
        with _conn() as conn:
            conn.execute(
                """UPDATE goals SET status='completed', results=?,
                                    updated_at=?, completed_at=?
                   WHERE goal_id=?""",
                (json.dumps(results), now, now, goal_id),
            )

    def fail(self, goal_id: str, error: str) -> None:
        with _conn() as conn:
            conn.execute(
                "UPDATE goals SET status='failed', results=?, updated_at=? WHERE goal_id=?",
                (json.dumps({"error": error}), _now(), goal_id),
            )

    def get(self, goal_id: str) -> dict | None:
        with _conn() as conn:
            row = conn.execute("SELECT * FROM goals WHERE goal_id=?", (goal_id,)).fetchone()
        if not row:
            return None
        return self._deserialize(dict(row))

    def list_active(self) -> list[dict]:
        with _conn() as conn:
            rows = conn.execute(
                "SELECT * FROM goals WHERE status IN ('pending','running') ORDER BY created_at"
            ).fetchall()
        return [self._deserialize(dict(r)) for r in rows]

    def list_recent(self, limit: int = 20) -> list[dict]:
        with _conn() as conn:
            rows = conn.execute(
                "SELECT * FROM goals ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [self._deserialize(dict(r)) for r in rows]

    def _deserialize(self, row: dict) -> dict:
        try:
            row["task_plan"] = json.loads(row.get("task_plan") or "[]")
        except (json.JSONDecodeError, TypeError):
            row["task_plan"] = []
        try:
            row["results"] = json.loads(row.get("results") or "null")
        except (json.JSONDecodeError, TypeError):
            row["results"] = None
        return row


_store: GoalStore | None = None


def get_goal_store() -> GoalStore:
    global _store
    if _store is None:
        _store = GoalStore()
    return _store
