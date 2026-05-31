"""EvaluationEngine — score simulation results against success criteria."""
from __future__ import annotations
import logging
import time
from typing import Any

from .schema import AssertionResult, Scenario, SimulationResult, StepResult

logger = logging.getLogger(__name__)


def _score_assertion(metric: str, threshold: Any,
                     steps: list[StepResult]) -> AssertionResult:
    if metric == "task_completion_rate":
        total = len(steps)
        completed = sum(1 for s in steps if s.ok)
        actual = completed / total if total else 0.0
        passed = actual >= float(threshold)
        score = actual / float(threshold) if float(threshold) else 1.0
        return AssertionResult(metric, passed, actual, threshold, min(1.0, score))

    if metric == "no_hallucinations":
        errors = [s for s in steps if s.error and "hallucination" in (s.error or "").lower()]
        actual = len(errors) == 0
        passed = actual == bool(threshold)
        return AssertionResult(metric, passed, actual, threshold, 1.0 if passed else 0.0)

    if metric == "max_latency_ms":
        latencies = [s.latency_ms for s in steps if s.latency_ms > 0]
        actual = max(latencies) if latencies else 0.0
        passed = actual <= float(threshold)
        score = 1.0 - max(0.0, (actual - float(threshold)) / float(threshold))
        return AssertionResult(metric, passed, actual, threshold, max(0.0, score))

    if metric == "error_rate":
        total = len(steps)
        errors = sum(1 for s in steps if not s.ok)
        actual = errors / total if total else 0.0
        passed = actual <= float(threshold)
        score = 1.0 - actual / float(threshold) if float(threshold) else 1.0
        return AssertionResult(metric, passed, actual, threshold, max(0.0, score))

    # Generic: return unknown as passed
    return AssertionResult(metric, True, "unknown", threshold, 1.0)


class EvaluationEngine:
    def evaluate(self, scenario: Scenario, result: SimulationResult) -> SimulationResult:
        assertions = []
        for crit in scenario.success_criteria:
            ar = _score_assertion(crit.metric, crit.threshold, result.steps)
            assertions.append(ar)

        if assertions:
            weights = [c.weight for c in scenario.success_criteria]
            total_weight = sum(weights)
            weighted_score = sum(
                ar.score * w for ar, w in zip(assertions, weights)
            ) / total_weight if total_weight else 0.0
        else:
            weighted_score = 1.0

        result.assertions = assertions
        result.overall_score = round(weighted_score, 4)
        result.completed_at = time.time()
        return result

    def persist(self, result: SimulationResult) -> None:
        try:
            import sqlite3, json, os
            from pathlib import Path
            db = Path(os.path.expanduser("~/.ai-employee/simulation.db"))
            db.parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(str(db), timeout=10) as c:
                c.execute("PRAGMA journal_mode=WAL")
                c.execute("PRAGMA busy_timeout=5000")
                c.execute("""
                    CREATE TABLE IF NOT EXISTS simulation_runs (
                        run_id TEXT PRIMARY KEY,
                        scenario_id TEXT NOT NULL,
                        status TEXT NOT NULL,
                        overall_score REAL,
                        step_count INTEGER,
                        started_at REAL,
                        completed_at REAL,
                        result_json TEXT NOT NULL
                    )
                """)
                c.execute("""
                    INSERT INTO simulation_runs
                      (run_id,scenario_id,status,overall_score,step_count,started_at,completed_at,result_json)
                    VALUES (?,?,?,?,?,?,?,?)
                    ON CONFLICT(run_id) DO UPDATE SET
                      status=excluded.status, overall_score=excluded.overall_score,
                      completed_at=excluded.completed_at, result_json=excluded.result_json
                """, (result.run_id, result.scenario_id, result.status.value,
                      result.overall_score, len(result.steps),
                      result.started_at, result.completed_at,
                      json.dumps({"assertions": [a.__dict__ for a in result.assertions],
                                  "error": result.error})))
        except Exception as e:
            logger.warning("Failed to persist simulation result: %s", e)

    def load(self, run_id: str) -> dict:
        try:
            import sqlite3, json, os
            from pathlib import Path
            db = Path(os.path.expanduser("~/.ai-employee/simulation.db"))
            with sqlite3.connect(str(db), timeout=10) as c:
                c.execute("PRAGMA journal_mode=WAL")
                c.execute("PRAGMA busy_timeout=5000")
                row = c.execute(
                    "SELECT * FROM simulation_runs WHERE run_id=?", (run_id,)
                ).fetchone()
            if not row:
                return {}
            return {
                "run_id": row[0], "scenario_id": row[1], "status": row[2],
                "overall_score": row[3], "step_count": row[4],
                "started_at": row[5], "completed_at": row[6],
                **json.loads(row[7]),
            }
        except Exception:
            return {}
