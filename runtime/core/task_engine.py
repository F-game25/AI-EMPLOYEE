"""Task Execution Engine — 3-layer Planner / Executor / Validator.

Builds a formal pipeline on top of the existing agent ecosystem:

1. **Planner**   — breaks a natural-language goal into ``TaskSpec`` dicts,
                   warm-starting from ``StrategyStore`` when prior wins exist.
2. **Executor**  — dispatches each ``TaskSpec`` to the right skill with
                   configurable retry + exponential back-off.
3. **Validator** — checks outputs, scores 0–1, persists results to
                   ``~/.ai-employee/task_log.db``, and emits escalation
                   notifications on repeated failures.

Usage::

    from core.task_engine import get_task_engine

    engine = get_task_engine()
    run = engine.run_goal("Create and publish a TikTok affiliate post")
    print(run["performance_score"])
"""
from __future__ import annotations

import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# ── Data model ────────────────────────────────────────────────────────────────

@dataclass
class TaskSpec:
    """Specification for a single executable task."""

    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    skill: str = ""
    inputs: dict = field(default_factory=dict)
    expected_outputs: dict = field(default_factory=dict)
    timeout_s: int = 60
    max_retries: int = 3
    retry_backoff_s: float = 2.0

    # Filled by executor/validator
    actual_output: Any = None
    attempts: int = 0
    success: bool = False
    score: float = 0.0
    error: str = ""
    started_at: str = ""
    finished_at: str = ""


# ── SQLite helpers ─────────────────────────────────────────────────────────────

_DEFAULT_DB = Path.home() / ".ai-employee" / "task_log.db"

_CREATE_SQL = """
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


def _get_conn(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute(_CREATE_SQL)
    return conn


# ── Task Engine ────────────────────────────────────────────────────────────────

class TaskEngine:
    """Planner → Executor → Validator pipeline."""

    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = db_path or _DEFAULT_DB
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ helpers

    def _log_task(self, run_id: str, task: TaskSpec) -> None:
        try:
            with _get_conn(self._db_path) as conn:
                conn.execute(
                    """INSERT INTO task_log
                       (run_id, task_id, skill, success, attempts, score,
                        error, started_at, finished_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        run_id, task.id, task.skill,
                        int(task.success), task.attempts, task.score,
                        task.error, task.started_at, task.finished_at,
                    ),
                )
        except Exception:
            pass

    def _escalate(self, task: TaskSpec, run_id: str) -> None:
        """Attempt to send a failure notification through available tools."""
        msg = (
            f"[AI-Employee] Task failed after {task.attempts} attempts.\n"
            f"run_id={run_id}  task_id={task.id}  skill={task.skill}\n"
            f"error: {task.error}"
        )
        try:
            from core.change_log import get_changelog
            get_changelog().record(
                actor="task_engine",
                action_type="task_escalated",
                reason=f"Task {task.id} exhausted retries",
                before={"skill": task.skill, "attempts": task.attempts},
                after={"error": task.error},
                outcome="escalated",
            )
        except Exception:
            pass
        # Emit to Discord/email tools if available
        try:
            import sys, os
            _tools = Path(__file__).parent.parent / "agents" / "tools"
            if str(_tools) not in sys.path:
                sys.path.insert(0, str(_tools))
            from discord_notify import send_discord  # type: ignore
            send_discord(msg)
        except Exception:
            pass

    # ------------------------------------------------------------------ planner

    def plan(self, goal: str) -> list[TaskSpec]:
        """Break *goal* into an ordered list of TaskSpecs.

        Uses StrategyStore to warm-start with prior winning agent configs.
        Falls back to a simple keyword-based mapping when no history exists.
        """
        tasks: list[TaskSpec] = []

        # Try strategy store warm-start
        best_strategies: list[dict] = []
        try:
            from memory.strategy_store import get_strategy_store
            goal_type = self._classify_goal(goal)
            best_strategies = get_strategy_store().get_best_strategy(goal_type)
        except Exception:
            pass

        if best_strategies:
            for strategy in best_strategies[:2]:
                tasks.append(
                    TaskSpec(
                        skill=strategy.get("agent", "problem_solver"),
                        inputs={**strategy.get("config", {}), "goal": goal},
                        expected_outputs={"status": "success"},
                    )
                )
        else:
            # Keyword-based fallback plan
            tasks = self._keyword_plan(goal)

        return tasks

    def _classify_goal(self, goal: str) -> str:
        goal_lower = goal.lower()
        if any(w in goal_lower for w in ("content", "post", "publish", "video")):
            return "content_generation"
        if any(w in goal_lower for w in ("lead", "prospect", "outreach")):
            return "lead_generation"
        if any(w in goal_lower for w in ("email", "campaign", "newsletter")):
            return "email_marketing"
        if any(w in goal_lower for w in ("analyse", "analyze", "report", "metric")):
            return "analytics"
        return "general"

    def _keyword_plan(self, goal: str) -> list[TaskSpec]:
        goal_type = self._classify_goal(goal)
        mapping = {
            "content_generation": [
                TaskSpec(skill="content-calendar", inputs={"goal": goal},
                         expected_outputs={"status": "success"}),
                TaskSpec(skill="social-media-manager", inputs={"goal": goal},
                         expected_outputs={"status": "success"}),
            ],
            "lead_generation": [
                TaskSpec(skill="lead-generator", inputs={"goal": goal},
                         expected_outputs={"leads": []}),
                TaskSpec(skill="lead-crm", inputs={"goal": goal},
                         expected_outputs={"status": "success"}),
            ],
            "email_marketing": [
                TaskSpec(skill="email-marketing", inputs={"goal": goal},
                         expected_outputs={"campaign_id": ""}),
            ],
            "analytics": [
                TaskSpec(skill="ceo-briefing", inputs={"goal": goal},
                         expected_outputs={"report": ""}),
            ],
        }
        return mapping.get(goal_type, [
            TaskSpec(skill="problem-solver", inputs={"goal": goal},
                     expected_outputs={"status": "success"}),
        ])

    # ---------------------------------------------------------------- executor

    def execute(self, task: TaskSpec) -> TaskSpec:
        """Run a single TaskSpec with retry logic."""
        task.started_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        for attempt in range(1, task.max_retries + 1):
            task.attempts = attempt
            try:
                result = self._dispatch(task)
                task.actual_output = result
                task.success = True
                task.error = ""
                break
            except Exception as exc:
                task.error = str(exc)
                if attempt < task.max_retries:
                    backoff = task.retry_backoff_s * (2 ** (attempt - 1))
                    time.sleep(min(backoff, 30))

        task.finished_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        return task

    def _dispatch(self, task: TaskSpec) -> Any:
        """Dispatch a task to the ActionBus (or mock execute if skill not found)."""
        try:
            from actions.action_bus import get_action_bus
            result = get_action_bus().emit(
                action_type=f"skill:{task.skill}",
                payload={"task_id": task.id, "inputs": task.inputs},
                actor="task_engine",
                reason=f"Executing task {task.id}",
            )
            return result
        except Exception as exc:
            raise RuntimeError(f"Dispatch failed for skill '{task.skill}': {exc}") from exc

    # --------------------------------------------------------------- validator

    def validate(self, task: TaskSpec) -> float:
        """Score a completed task 0–1.

        Scoring:
          - 0.0  if task never succeeded
          - 0.5  base for success on first try
          - +0.3 bonus if actual_output contains expected_outputs keys
          - -0.1 per extra attempt beyond the first
        """
        if not task.success:
            task.score = 0.0
            return 0.0

        score = 0.5
        if task.actual_output and task.expected_outputs:
            matched = 0
            for key in task.expected_outputs:
                if isinstance(task.actual_output, dict) and key in task.actual_output:
                    matched += 1
            if task.expected_outputs:
                score += 0.3 * (matched / len(task.expected_outputs))
        score -= 0.1 * max(0, task.attempts - 1)
        task.score = max(0.0, min(1.0, score))
        return task.score

    # --------------------------------------------------------------- full run

    def run_goal(self, goal: str) -> dict:
        """Plan, execute, and validate a complete goal.  Returns run summary."""
        run_id = str(uuid.uuid4())[:8]
        tasks = self.plan(goal)

        results = []
        total_score = 0.0

        for task in tasks:
            self.execute(task)
            score = self.validate(task)
            total_score += score
            self._log_task(run_id, task)
            if not task.success:
                self._escalate(task, run_id)

            # Update strategy store
            try:
                from memory.strategy_store import get_strategy_store
                get_strategy_store().record(
                    goal_type=self._classify_goal(goal),
                    agent=task.skill,
                    config=task.inputs,
                    outcome_score=score,
                    notes=task.error or "ok",
                )
            except Exception:
                pass

            results.append({
                "task_id": task.id,
                "skill": task.skill,
                "success": task.success,
                "attempts": task.attempts,
                "score": round(task.score, 3),
                "error": "Task failed" if task.error else "",
            })

        performance_score = round(total_score / max(len(tasks), 1), 3)

        # Log run to change log
        try:
            from core.change_log import get_changelog
            get_changelog().record(
                actor="task_engine",
                action_type="goal_completed",
                reason=f"Goal: {goal}",
                before=None,
                after={"run_id": run_id, "tasks": len(tasks)},
                outcome=f"score={performance_score}",
            )
        except Exception:
            pass

        return {
            "run_id": run_id,
            "goal": goal,
            "tasks": results,
            "performance_score": performance_score,
            "success_rate": round(
                sum(1 for r in results if r["success"]) / max(len(results), 1), 3
            ),
        }

    def recent_runs(self, *, limit: int = 20) -> list[dict]:
        """Return recent task log entries."""
        try:
            with _get_conn(self._db_path) as conn:
                rows = conn.execute(
                    "SELECT * FROM task_log ORDER BY id DESC LIMIT ?", (limit,)
                ).fetchall()
            return [dict(r) for r in rows]
        except Exception:
            return []

    def daily_stats(self) -> dict:
        """Return today's task execution statistics."""
        today = time.strftime("%Y-%m-%d", time.gmtime())
        try:
            with _get_conn(self._db_path) as conn:
                row = conn.execute(
                    """SELECT COUNT(*) AS total,
                              SUM(success)    AS succeeded,
                              AVG(score)      AS avg_score
                       FROM task_log
                       WHERE started_at LIKE ?""",
                    (f"{today}%",),
                ).fetchone()
            total = row["total"] or 0
            succeeded = row["succeeded"] or 0
            return {
                "date": today,
                "tasks_executed": total,
                "success_rate": round(succeeded / max(total, 1), 3),
                "avg_score": round(row["avg_score"] or 0.0, 3),
            }
        except Exception:
            return {"date": today, "tasks_executed": 0, "success_rate": 0.0, "avg_score": 0.0}


# ── Singleton ─────────────────────────────────────────────────────────────────

_instance: TaskEngine | None = None
_instance_lock = threading.Lock()


def get_task_engine(db_path: Path | None = None) -> TaskEngine:
    """Return the process-wide TaskEngine singleton."""
    global _instance
    with _instance_lock:
        if _instance is None:
            _instance = TaskEngine(db_path)
    return _instance
