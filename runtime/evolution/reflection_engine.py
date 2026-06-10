"""ReflectionEngine — produces compact typed lessons, only on trigger conditions.

Triggers (lesson is produced ONLY if at least one holds):
  failed | user-corrected | high-value | score<threshold | repeated-failure |
  saved-as-artifact.
A clean high-score trace produces NO lesson (returns None) — that is the test
invariant. Lessons are SHORT typed records (no log dumps), stored as scrubbed
JSONL with dedup + a simple conflict check.
"""
from __future__ import annotations

import json
import os
import threading
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from evolution import LESSONS_DIR, ensure_dirs
from evolution.scrub import scrub

_SCORE_THRESHOLD = float(os.environ.get("EVOLUTION_REFLECT_THRESHOLD", "0.6"))
_LESSON_TTL_DAYS = int(os.environ.get("EVOLUTION_LESSON_TTL_DAYS", "60"))

LESSON_TYPES = (
    "failure_avoidance", "success_pattern", "routing_hint",
    "context_gap", "preference", "tool_usage",
)


def _iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ReflectionEngine:
    def __init__(self):
        self._lock = threading.Lock()
        self._store = LESSONS_DIR / "lessons.jsonl"

    def _should_reflect(self, trace: dict[str, Any], scores: dict[str, float],
                        failure: dict[str, Any] | None) -> Optional[str]:
        """Return the trigger name if reflection should fire, else None."""
        if failure or not trace.get("success", True):
            return "failed"
        if trace.get("user_corrected"):
            return "user_corrected"
        if trace.get("saved_as_artifact"):
            return "saved_as_artifact"
        if trace.get("repeated_failure"):
            return "repeated_failure"
        comp = sum(scores.values()) / max(len(scores), 1) if scores else 1.0
        if comp < _SCORE_THRESHOLD:
            return "low_score"
        if scores.get("learning_value_score", 0.0) >= 0.85:
            return "high_value"
        return None  # clean high-score trace → no lesson

    def reflect(self, trace: dict[str, Any], scores: dict[str, float],
                failure: dict[str, Any] | None = None) -> Optional[dict[str, Any]]:
        trigger = self._should_reflect(trace, scores, failure)
        if trigger is None:
            return None

        if failure:
            ltype, summary = "failure_avoidance", (
                f"On {trace.get('task_type')} tasks, {failure.get('failure_type')} occurred: "
                f"{failure.get('root_cause', '')[:160]}")
        elif trigger == "user_corrected":
            ltype, summary = "preference", (
                f"User corrected output on '{str(trace.get('user_goal',''))[:80]}' — "
                "capture preference for similar tasks.")
        else:
            ltype, summary = "success_pattern", (
                f"High-value {trace.get('task_type')} run succeeded; reusable pattern.")

        lesson = {
            "lesson_id": f"les-{uuid.uuid4().hex[:12]}",
            "lesson_type": ltype,
            "scope": trace.get("task_type") or "global",
            "trigger": trigger,
            "summary": summary[:280],
            "evidence_trace_ids": [trace.get("trace_id")],
            "retrieval_tags": self._tags(trace, failure),
            "confidence": "high" if trigger in ("failed", "repeated_failure") else "medium",
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=_LESSON_TTL_DAYS)).isoformat(),
            "promotion_state": "candidate",
            "created_at": _iso(),
        }
        self._persist(scrub(lesson))
        return lesson

    @staticmethod
    def _tags(trace: dict[str, Any], failure: dict[str, Any] | None) -> list[str]:
        tags = [trace.get("task_type") or "general"]
        if failure:
            tags.append(failure.get("failure_type", "failure"))
        tags += [m for m in (trace.get("models_used") or [])][:2]
        return [t for t in tags if t]

    def _persist(self, lesson: dict[str, Any]) -> None:
        with self._lock:
            if self._is_dup(lesson):
                return
            ensure_dirs()
            with open(self._store, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(lesson, ensure_ascii=False) + "\n")

    def _is_dup(self, lesson: dict[str, Any]) -> bool:
        """Dedup + simple conflict check: same scope+type+summary already stored."""
        if not self._store.exists():
            return False
        key = (lesson["scope"], lesson["lesson_type"], lesson["summary"])
        with open(self._store, encoding="utf-8") as fh:
            for line in fh:
                try:
                    ex = json.loads(line)
                except Exception:
                    continue
                if (ex.get("scope"), ex.get("lesson_type"), ex.get("summary")) == key:
                    return True
        return False

    def list_lessons(self, limit: int = 100) -> list[dict[str, Any]]:
        if not self._store.exists():
            return []
        out = []
        with open(self._store, encoding="utf-8") as fh:
            for line in fh:
                try:
                    out.append(json.loads(line))
                except Exception:
                    continue
        return out[-limit:]


__all__ = ["ReflectionEngine", "LESSON_TYPES"]
