"""Infrastructure persistence for task execution records."""
from __future__ import annotations

import sqlite3
import time
from pathlib import Path

from core.contracts import TaskNode

CREATE_SQL = """
CREATE TABLE IF NOT EXISTS task_log (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id       TEXT NOT NULL,
    task_id      TEXT NOT NULL,
    skill        TEXT NOT NULL DEFAULT '',
    success      INTEGER NOT NULL DEFAULT 0,
    attempts     INTEGER NOT NULL DEFAULT 0,
    score        REAL    NOT NULL DEFAULT 0.0,
    error        TEXT    NOT NULL DEFAULT '',
    started_at   TEXT    NOT NULL DEFAULT '',
    finished_at  TEXT    NOT NULL DEFAULT ''
);
"""


class TaskLogStore:
    """SQLite-backed store for task run telemetry."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as conn:
            conn.execute(CREATE_SQL)

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._db_path))
        conn.execute("PRAGMA journal_mode=WAL")
        conn.row_factory = sqlite3.Row
        return conn

    def log_task(self, run_id: str, task: TaskNode) -> None:
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO task_log
                   (run_id, task_id, skill, success, attempts, score,
                    error, started_at, finished_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    run_id,
                    task.task_id,
                    task.skill,
                    int(task.status == "success"),
                    task.attempts,
                    task.score,
                    task.error,
                    task.started_at,
                    task.finished_at,
                ),
            )

    def recent_runs(self, *, limit: int = 20) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM task_log ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(row) for row in rows]

    def daily_stats(self) -> dict:
        today = time.strftime("%Y-%m-%d", time.gmtime())
        with self._conn() as conn:
            row = conn.execute(
                """SELECT COUNT(*) AS total,
                          SUM(success) AS succeeded,
                          AVG(score) AS avg_score
                   FROM task_log
                   WHERE started_at LIKE ?""",
                (f"{today}%",),
            ).fetchone()
        total = int(row["total"] or 0)
        succeeded = int(row["succeeded"] or 0)
        avg_score = float(row["avg_score"] or 0.0)
        return {
            "date": today,
            "tasks_executed": total,
            "success_rate": round(succeeded / max(total, 1), 3),
            "avg_score": round(avg_score, 3),
        }

    def top_skills(self, *, limit: int = 5) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT skill,
                          COUNT(*) AS runs,
                          SUM(success) AS succeeded,
                          AVG(score) AS avg_score
                   FROM task_log
                   WHERE skill != ''
                   GROUP BY skill
                   ORDER BY (SUM(success) * 1.0 / MAX(COUNT(*), 1)) DESC, runs DESC
                   LIMIT ?""",
                (limit,),
            ).fetchall()
        output: list[dict] = []
        for row in rows:
            runs = int(row["runs"] or 0)
            succeeded = int(row["succeeded"] or 0)
            output.append({
                "skill": row["skill"],
                "runs": runs,
                "success_rate": round(succeeded / max(runs, 1), 3),
                "avg_score": round(float(row["avg_score"] or 0.0), 3),
            })
        return output
