"""PipelineStore — SQLite persistence for money-generation workflow telemetry."""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path

_DEFAULT_DB = Path.home() / ".ai-employee" / "pipeline.db"
_SUCCESS_STATUSES = ("executed", "dry_run")

_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS pipeline_runs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id        TEXT    NOT NULL,
    pipeline      TEXT    NOT NULL,
    status        TEXT    NOT NULL DEFAULT 'queued',
    estimated_roi REAL    NOT NULL DEFAULT 0.0,
    context       TEXT    NOT NULL DEFAULT '{}',
    steps         TEXT    NOT NULL DEFAULT '[]',
    created_at    TEXT    NOT NULL
);
"""


class PipelineStore:
    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = db_path or _DEFAULT_DB
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        with self._connect() as conn:
            conn.execute(_CREATE_SQL)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def record_run(
        self,
        *,
        run_id: str,
        pipeline: str,
        status: str,
        estimated_roi: float,
        context: dict,
        steps: list[dict],
    ) -> dict:
        ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        with self._lock:
            with self._connect() as conn:
                cur = conn.execute(
                    """INSERT INTO pipeline_runs
                       (run_id, pipeline, status, estimated_roi, context, steps, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        run_id,
                        pipeline,
                        status,
                        float(estimated_roi),
                        json.dumps(context, ensure_ascii=False),
                        json.dumps(steps, ensure_ascii=False),
                        ts,
                    ),
                )
                row_id = int(cur.lastrowid or 0)
        return {
            "id": row_id,
            "run_id": run_id,
            "pipeline": pipeline,
            "status": status,
            "estimated_roi": round(float(estimated_roi), 3),
            "context": context,
            "steps": steps,
            "created_at": ts,
        }

    def recent_runs(self, *, limit: int = 20) -> list[dict]:
        with self._lock:
            with self._connect() as conn:
                rows = conn.execute(
                    "SELECT * FROM pipeline_runs ORDER BY id DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        output: list[dict] = []
        for row in rows:
            output.append({
                "id": row["id"],
                "run_id": row["run_id"],
                "pipeline": row["pipeline"],
                "status": row["status"],
                "estimated_roi": row["estimated_roi"],
                "context": json.loads(row["context"] or "{}"),
                "steps": json.loads(row["steps"] or "[]"),
                "created_at": row["created_at"],
            })
        return output

    def overview(self) -> dict:
        with self._lock:
            with self._connect() as conn:
                total_row = conn.execute(
                    """SELECT COUNT(*) AS runs,
                              SUM(CASE WHEN status IN (?, ?) THEN 1 ELSE 0 END) AS successful,
                              SUM(CASE WHEN status = 'queued' THEN 1 ELSE 0 END) AS pending,
                              SUM(estimated_roi) AS total_roi
                       FROM pipeline_runs"""
                    ,
                    _SUCCESS_STATUSES,
                ).fetchone()
                by_pipe = conn.execute(
                    """SELECT pipeline,
                              COUNT(*) AS runs,
                              AVG(estimated_roi) AS avg_roi
                       FROM pipeline_runs
                       GROUP BY pipeline
                       ORDER BY avg_roi DESC"""
                ).fetchall()
        runs = int(total_row["runs"] or 0)
        successful = int(total_row["successful"] or 0)
        return {
            "runs": runs,
            "success_rate": round(successful / max(runs, 1), 3),
            "pending_runs": int(total_row["pending"] or 0),
            "total_estimated_roi": round(float(total_row["total_roi"] or 0.0), 3),
            "pipelines": [
                {
                    "pipeline": row["pipeline"],
                    "runs": int(row["runs"] or 0),
                    "avg_estimated_roi": round(float(row["avg_roi"] or 0.0), 3),
                }
                for row in by_pipe
            ],
        }


_instance: PipelineStore | None = None
_instance_lock = threading.Lock()


def get_pipeline_store(db_path: Path | None = None) -> PipelineStore:
    global _instance
    with _instance_lock:
        if _instance is None:
            _instance = PipelineStore(db_path)
    return _instance
