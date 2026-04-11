"""ROI Tracker — per-action revenue tracking.

Records every agent action with its token cost and estimated revenue so the
system can calculate return-on-investment for each strategy.

Storage: SQLite at ~/.ai-employee/roi.db

Usage::

    from core.roi_tracker import get_roi_tracker

    tracker = get_roi_tracker()
    tracker.record(
        action_id="task-123",
        agent="content_calendar",
        cost_tokens=500,
        estimated_revenue=25.0,
        notes="Published TikTok affiliate post",
    )
    summary = tracker.daily_summary()
"""
from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path
from typing import Any


_DEFAULT_DB = Path.home() / ".ai-employee" / "roi.db"

_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS roi_events (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    action_id    TEXT    NOT NULL,
    agent        TEXT    NOT NULL DEFAULT '',
    cost_tokens  INTEGER NOT NULL DEFAULT 0,
    estimated_revenue REAL NOT NULL DEFAULT 0.0,
    notes        TEXT    NOT NULL DEFAULT '',
    timestamp    TEXT    NOT NULL
);
"""


class RoiTracker:
    """Lightweight SQLite-backed ROI log."""

    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = db_path or _DEFAULT_DB
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        with self._connect() as conn:
            conn.execute(_CREATE_SQL)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def record(
        self,
        *,
        action_id: str,
        agent: str = "",
        cost_tokens: int = 0,
        estimated_revenue: float = 0.0,
        notes: str = "",
    ) -> dict:
        """Insert one ROI event and return it as a dict."""
        ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        with self._lock:
            with self._connect() as conn:
                cur = conn.execute(
                    """INSERT INTO roi_events
                       (action_id, agent, cost_tokens, estimated_revenue, notes, timestamp)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (action_id, agent, cost_tokens, estimated_revenue, notes, ts),
                )
                row_id = cur.lastrowid
        return {
            "id": row_id,
            "action_id": action_id,
            "agent": agent,
            "cost_tokens": cost_tokens,
            "estimated_revenue": estimated_revenue,
            "notes": notes,
            "timestamp": ts,
        }

    def daily_summary(self, date: str | None = None) -> dict:
        """Return aggregated stats for *date* (YYYY-MM-DD, defaults to today)."""
        if date is None:
            date = time.strftime("%Y-%m-%d", time.gmtime())
        with self._lock:
            with self._connect() as conn:
                row = conn.execute(
                    """SELECT
                         COUNT(*)            AS events,
                         SUM(cost_tokens)    AS total_tokens,
                         SUM(estimated_revenue) AS total_revenue
                       FROM roi_events
                       WHERE timestamp LIKE ?""",
                    (f"{date}%",),
                ).fetchone()
        return {
            "date": date,
            "events": row["events"] or 0,
            "total_tokens": row["total_tokens"] or 0,
            "total_revenue": round(row["total_revenue"] or 0.0, 2),
            "roi": (
                round((row["total_revenue"] or 0.0) / max(row["total_tokens"] or 1, 1), 4)
            ),
        }

    def top_agents(self, *, limit: int = 5) -> list[dict]:
        """Return agents ranked by total estimated revenue."""
        with self._lock:
            with self._connect() as conn:
                rows = conn.execute(
                    """SELECT agent,
                              COUNT(*)                 AS actions,
                              SUM(estimated_revenue)   AS revenue
                       FROM roi_events
                       GROUP BY agent
                       ORDER BY revenue DESC
                       LIMIT ?""",
                    (limit,),
                ).fetchall()
        return [
            {
                "agent": r["agent"],
                "actions": r["actions"],
                "revenue": round(r["revenue"] or 0.0, 2),
            }
            for r in rows
        ]

    def recent(self, *, limit: int = 20) -> list[dict]:
        """Return the most recent *limit* events."""
        with self._lock:
            with self._connect() as conn:
                rows = conn.execute(
                    """SELECT * FROM roi_events ORDER BY id DESC LIMIT ?""",
                    (limit,),
                ).fetchall()
        return [dict(r) for r in rows]


# ── Singleton ─────────────────────────────────────────────────────────────────

_instance: RoiTracker | None = None
_instance_lock = threading.Lock()


def get_roi_tracker(db_path: Path | None = None) -> RoiTracker:
    """Return the process-wide RoiTracker singleton."""
    global _instance
    with _instance_lock:
        if _instance is None:
            _instance = RoiTracker(db_path)
    return _instance
