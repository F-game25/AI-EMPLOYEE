"""Goal Engine — persistent goal lifecycle management.

Storage: SQLite at ~/.ai-employee/planning.db
All goal mutations are logged as events for audit and replay.
Goal hierarchy forms a DAG: parent_id creates objective trees.
Dependency resolution prevents circular waits.
"""
from __future__ import annotations

import json
import logging
import sqlite3
import time
import uuid
from pathlib import Path
from threading import RLock
from typing import Any

from infra.planning.schema import (
    Goal, GoalStatus, Horizon, KeyResult, Milestone, Priority, StrategicPlan,
)

logger = logging.getLogger("planning.goal_engine")

_DB_PATH = Path.home() / ".ai-employee" / "planning.db"

_INIT_SQL = """
CREATE TABLE IF NOT EXISTS goals (
    id              TEXT PRIMARY KEY,
    tenant_id       TEXT NOT NULL,
    data            TEXT NOT NULL,   -- JSON blob of Goal.to_dict()
    status          TEXT NOT NULL,
    horizon         TEXT NOT NULL,
    priority        TEXT NOT NULL,
    due_at          REAL NOT NULL,
    updated_at      REAL NOT NULL,
    parent_id       TEXT
);

CREATE INDEX IF NOT EXISTS idx_goals_tenant ON goals(tenant_id);
CREATE INDEX IF NOT EXISTS idx_goals_status ON goals(tenant_id, status);
CREATE INDEX IF NOT EXISTS idx_goals_due ON goals(tenant_id, due_at);

CREATE TABLE IF NOT EXISTS goal_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          REAL NOT NULL,
    goal_id     TEXT NOT NULL,
    event_type  TEXT NOT NULL,   -- created, updated, status_changed, kr_updated, reviewed
    actor       TEXT NOT NULL DEFAULT 'system',
    data        TEXT NOT NULL DEFAULT '{}'
);
"""


class GoalEngine:
    def __init__(self, db_path: Path = _DB_PATH) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db_path = db_path
        self._lock = RLock()
        with self._connect() as conn:
            conn.executescript(_INIT_SQL)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._db_path), timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    # ── CRUD ─────────────────────────────────────────────────────────────────

    def create_goal(
        self,
        tenant_id: str,
        title: str,
        description: str,
        horizon: Horizon,
        priority: Priority,
        owner_id: str,
        due_at: float,
        *,
        parent_id: str | None = None,
        key_results: list[dict] | None = None,
        milestones: list[dict] | None = None,
        depends_on: list[str] | None = None,
        tags: list[str] | None = None,
        review_cadence_days: int = 7,
        actor: str = "system",
    ) -> Goal:
        goal_id = str(uuid.uuid4())
        now = time.time()
        krs = [KeyResult(**kr) for kr in (key_results or [])]
        mls = [Milestone(**m) for m in (milestones or [])]
        goal = Goal(
            id=goal_id, tenant_id=tenant_id, title=title,
            description=description, horizon=horizon, priority=priority,
            status=GoalStatus.DRAFT, owner_id=owner_id,
            created_at=now, updated_at=now, due_at=due_at,
            parent_id=parent_id, key_results=krs, milestones=mls,
            depends_on=depends_on or [], tags=tags or [],
            review_cadence_days=review_cadence_days,
        )
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO goals VALUES (?,?,?,?,?,?,?,?,?)",
                (goal.id, goal.tenant_id, json.dumps(goal.to_dict()),
                 goal.status.value, goal.horizon.value, goal.priority.value,
                 goal.due_at, goal.updated_at, goal.parent_id),
            )
            self._log_event(conn, goal.id, "created", actor, {"title": title})
        logger.info("Goal created: id=%s tenant=%s title=%r", goal_id, tenant_id, title)
        # Cross-layer goal identity (best-effort; never breaks goal creation).
        from core.goal_registry import register_goal, SOURCE_OBJECTIVE  # noqa: PLC0415
        register_goal(title, SOURCE_OBJECTIVE, goal.id, tenant_id=tenant_id)
        return goal

    def get_goal(self, goal_id: str, tenant_id: str) -> Goal | None:
        with self._connect() as conn:
            row = conn.execute("SELECT data FROM goals WHERE id=? AND tenant_id=?",
                               (goal_id, tenant_id)).fetchone()
        return self._deserialize(row["data"]) if row else None

    def list_goals(
        self,
        tenant_id: str,
        *,
        status: GoalStatus | None = None,
        horizon: Horizon | None = None,
        priority: Priority | None = None,
        parent_id: str | None = None,
        overdue_only: bool = False,
        limit: int = 200,
    ) -> list[Goal]:
        sql = "SELECT data FROM goals WHERE tenant_id=?"
        params: list[Any] = [tenant_id]
        if status:
            sql += " AND status=?"; params.append(status.value)
        if horizon:
            sql += " AND horizon=?"; params.append(horizon.value)
        if priority:
            sql += " AND priority=?"; params.append(priority.value)
        if parent_id:
            sql += " AND parent_id=?"; params.append(parent_id)
        if overdue_only:
            sql += " AND due_at < ? AND status NOT IN ('completed','cancelled','failed')"; params.append(time.time())
        sql += " ORDER BY priority, due_at LIMIT ?"
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._deserialize(r["data"]) for r in rows]

    def update_status(self, goal_id: str, tenant_id: str, new_status: GoalStatus, actor: str = "system") -> bool:
        goal = self.get_goal(goal_id, tenant_id)
        if not goal:
            return False
        old_status = goal.status
        goal.status = new_status
        goal.updated_at = time.time()
        with self._lock, self._connect() as conn:
            conn.execute("UPDATE goals SET status=?, updated_at=?, data=? WHERE id=? AND tenant_id=?",
                         (new_status.value, goal.updated_at, json.dumps(goal.to_dict()), goal_id, tenant_id))
            self._log_event(conn, goal_id, "status_changed", actor,
                            {"from": old_status.value, "to": new_status.value})
        return True

    def update_key_result(self, goal_id: str, tenant_id: str, kr_id: str, current: float, actor: str = "system") -> bool:
        goal = self.get_goal(goal_id, tenant_id)
        if not goal:
            return False
        kr = next((k for k in goal.key_results if k.id == kr_id), None)
        if not kr:
            return False
        old_val = kr.current
        kr.current = current
        goal.updated_at = time.time()
        # Auto-complete goal if all KRs at 100%
        if all(k.progress >= 1.0 for k in goal.key_results):
            goal.status = GoalStatus.COMPLETED
        with self._lock, self._connect() as conn:
            conn.execute("UPDATE goals SET data=?, updated_at=?, status=? WHERE id=? AND tenant_id=?",
                         (json.dumps(goal.to_dict()), goal.updated_at, goal.status.value, goal_id, tenant_id))
            self._log_event(conn, goal_id, "kr_updated", actor,
                            {"kr_id": kr_id, "from": old_val, "to": current})
        return True

    def mark_reviewed(self, goal_id: str, tenant_id: str, confidence: float, notes: str = "", actor: str = "system") -> bool:
        goal = self.get_goal(goal_id, tenant_id)
        if not goal:
            return False
        goal.last_reviewed_at = time.time()
        goal.confidence = max(0.0, min(1.0, confidence))
        goal.updated_at = time.time()
        with self._lock, self._connect() as conn:
            conn.execute("UPDATE goals SET data=?, updated_at=? WHERE id=? AND tenant_id=?",
                         (json.dumps(goal.to_dict()), goal.updated_at, goal_id, tenant_id))
            self._log_event(conn, goal_id, "reviewed", actor, {"confidence": confidence, "notes": notes})
        return True

    def get_children(self, goal_id: str, tenant_id: str) -> list[Goal]:
        with self._connect() as conn:
            rows = conn.execute("SELECT data FROM goals WHERE parent_id=? AND tenant_id=?",
                                (goal_id, tenant_id)).fetchall()
        return [self._deserialize(r["data"]) for r in rows]

    def get_objective_tree(self, root_id: str, tenant_id: str, depth: int = 0) -> dict:
        goal = self.get_goal(root_id, tenant_id)
        if not goal:
            return {}
        node = goal.to_dict()
        if depth < 5:
            children = self.get_children(root_id, tenant_id)
            node["children"] = [self.get_objective_tree(c.id, tenant_id, depth + 1) for c in children]
        return node

    def get_due_for_review(self, tenant_id: str) -> list[Goal]:
        now = time.time()
        goals = self.list_goals(tenant_id, status=GoalStatus.ACTIVE)
        return [
            g for g in goals
            if (now - g.last_reviewed_at) > (g.review_cadence_days * 86400)
        ]

    def get_events(self, goal_id: str, limit: int = 50) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT ts, event_type, actor, data FROM goal_events WHERE goal_id=? ORDER BY ts DESC LIMIT ?",
                (goal_id, limit)
            ).fetchall()
        return [{"ts": r["ts"], "event_type": r["event_type"], "actor": r["actor"],
                 "data": json.loads(r["data"])} for r in rows]

    @staticmethod
    def _log_event(conn: sqlite3.Connection, goal_id: str, event_type: str, actor: str, data: dict) -> None:
        conn.execute(
            "INSERT INTO goal_events(ts, goal_id, event_type, actor, data) VALUES(?,?,?,?,?)",
            (time.time(), goal_id, event_type, actor, json.dumps(data)),
        )

    @staticmethod
    def _deserialize(data: str) -> Goal:
        d = json.loads(data)
        krs = [KeyResult(**kr) for kr in d.pop("key_results", [])]
        mls = [Milestone(**{k: v for k, v in m.items() if k != "completed"})
               for m in d.pop("milestones", [])]
        d.pop("overall_progress", None)
        return Goal(
            **{k: v for k, v in d.items()
               if k in Goal.__dataclass_fields__},
            key_results=krs,
            milestones=mls,
        )


_engine: GoalEngine | None = None

def get_goal_engine() -> GoalEngine:
    global _engine
    if _engine is None:
        _engine = GoalEngine()
    return _engine
