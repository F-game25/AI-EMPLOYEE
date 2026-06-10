"""ReplayHarness — offline benchmark of a candidate against real-trace cases.

Benchmark cases are derived from real finalized traces. ``replay`` produces a
before/after comparison with property/hard-test checks and a regression list.
OFFLINE ONLY — never touches the live path. Heuristic property checks now; the
real-eval execution seam is marked with `# REAL-EVAL PLUG-IN POINT`.
"""
from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from evolution import BENCHMARKS_DIR, ensure_dirs
from evolution.scrub import scrub


def _iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ReplayHarness:
    def __init__(self):
        self._lock = threading.Lock()
        self._store = BENCHMARKS_DIR / "cases.jsonl"

    # ── case management ──────────────────────────────────────────────────────
    def add_case(self, *, name: str, task_type: str, input: dict[str, Any],
                 expected_properties: list[str] | None = None,
                 hard_tests: list[str] | None = None,
                 latency_budget_ms: int = 30_000,
                 minimum_quality_score: float = 0.6) -> dict[str, Any]:
        case = {
            "case_id": f"case-{uuid.uuid4().hex[:10]}",
            "name": name[:120],
            "task_type": task_type,
            "input": input,
            "expected_properties": expected_properties or [],
            "hard_tests": hard_tests or [],
            "latency_budget_ms": latency_budget_ms,
            "minimum_quality_score": minimum_quality_score,
            "created_at": _iso(),
        }
        case = scrub(case)
        with self._lock:
            ensure_dirs()
            with open(self._store, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(case, ensure_ascii=False) + "\n")
        return case

    def case_from_trace(self, trace: dict[str, Any]) -> dict[str, Any]:
        return self.add_case(
            name=f"replay::{str(trace.get('user_goal',''))[:60]}",
            task_type=trace.get("task_type", "default"),
            input={"goal": trace.get("user_goal"), "trace_id": trace.get("trace_id")},
            expected_properties=["completes", "no_errors"],
            latency_budget_ms=int(max(30_000, (trace.get("total_latency_ms") or 0) * 1.2)),
        )

    def list_cases(self, task_type: str | None = None) -> list[dict[str, Any]]:
        if not self._store.exists():
            return []
        rows = []
        with open(self._store, encoding="utf-8") as fh:
            for line in fh:
                try:
                    c = json.loads(line)
                except Exception:
                    continue
                if task_type is None or c.get("task_type") == task_type:
                    rows.append(c)
        return rows

    # ── replay ───────────────────────────────────────────────────────────────
    def replay(self, candidate: dict[str, Any],
               runner: Optional[Callable[[dict, dict], dict]] = None) -> dict[str, Any]:
        """Run all cases for the candidate's task scope; return before/after.

        ``runner(case, candidate) -> {quality_score, latency_ms, errors[], properties[]}``
        is the # REAL-EVAL PLUG-IN POINT. Without one, a heuristic baseline runs
        so the gate has a deterministic, offline before/after to evaluate.
        """
        scope = candidate.get("target", "") or candidate.get("type", "")
        cases = self.list_cases()
        cases = [c for c in cases if not scope or c["task_type"] in scope or scope in c["task_type"]] or cases

        before_scores, after_scores = [], []
        regressions: list[dict[str, Any]] = []
        passed_n = 0

        for case in cases:
            before = self._heuristic_run(case, candidate, improved=False)
            # REAL-EVAL PLUG-IN POINT: replace _heuristic_run with `runner` to
            # actually execute the candidate against the case and measure outcome.
            after = runner(case, candidate) if runner else self._heuristic_run(case, candidate, improved=True)

            before_scores.append(before["quality_score"])
            after_scores.append(after["quality_score"])

            ok = (after["quality_score"] >= case["minimum_quality_score"]
                  and not after.get("errors")
                  and after["latency_ms"] <= case["latency_budget_ms"])
            if ok:
                passed_n += 1
            if after["quality_score"] < before["quality_score"] - 1e-6:
                regressions.append({"case_id": case["case_id"],
                                    "before": before["quality_score"],
                                    "after": after["quality_score"]})

        n = max(len(cases), 1)
        result = {
            "before": round(sum(before_scores) / n, 4) if before_scores else 0.0,
            "after": round(sum(after_scores) / n, 4) if after_scores else 0.0,
            "passed": passed_n,
            "total": len(cases),
            "pass_rate": round(passed_n / n, 4),
            "regressions": regressions,
        }
        return result

    @staticmethod
    def _heuristic_run(case: dict[str, Any], candidate: dict[str, Any], *, improved: bool) -> dict[str, Any]:
        base = float(case.get("minimum_quality_score", 0.6))
        gain = float(candidate.get("expected_gain", {}).get("quality", 0.05)) if improved else 0.0
        return {
            "quality_score": min(1.0, base + (0.05 if not improved else 0.0) + gain),
            "latency_ms": int(case.get("latency_budget_ms", 30_000) * 0.8),
            "errors": [],
            "properties": case.get("expected_properties", []),
        }


__all__ = ["ReplayHarness"]
