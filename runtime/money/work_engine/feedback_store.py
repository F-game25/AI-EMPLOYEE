"""Feedback + offline study loop for the work engine.

record(opp_id, outcome) — store the outcome/rating per job.
study_session() — summarize lessons across recorded feedback into money_memory.json.

The study loop is offline/async-friendly and non-blocking: LLM is optional and
guarded, and a deterministic aggregate summary is always produced even with no
LLM. Never raises.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _state_dir() -> Path:
    try:
        from core.state_paths import canonical_state_dir
        base = canonical_state_dir()
    except Exception:
        base = Path.home() / ".ai-employee" / "state"  # canonical default, never repo-local (C0)
    try:
        base.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    return base


def _feedback_file() -> Path:
    return _state_dir() / "work_feedback.json"


def _memory_file() -> Path:
    return _state_dir() / "money_memory.json"


def _load(path: Path, default: Any) -> Any:
    try:
        from core.file_lock import read_json_safe
        data = read_json_safe(path, default=default)
        return data if data is not None else default
    except Exception:
        return default


def _save(path: Path, data: Any) -> bool:
    try:
        from core.file_lock import write_json_safe
        return bool(write_json_safe(path, data))
    except Exception:
        try:
            import json
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            return True
        except Exception:
            return False


def _coerce_rating(val: Any) -> float | None:
    if isinstance(val, bool):
        return None
    if isinstance(val, (int, float)):
        return max(0.0, min(5.0, float(val)))
    return None


def record(opp_id: str, outcome: dict[str, Any] | None) -> dict[str, Any]:
    """Record an outcome/rating for a job. Never raises."""
    try:
        out = dict(outcome or {})
        entry = {
            "opp_id": str(opp_id),
            "rating": _coerce_rating(out.get("rating")),
            "outcome": str(out.get("outcome") or out.get("status") or "unknown"),
            "accepted": bool(out.get("accepted", False)),
            "paid": bool(out.get("paid", False)),
            "notes": str(out.get("notes") or ""),
            "recorded_at": _now(),
        }
        data = _load(_feedback_file(), {"feedback": []})
        if not isinstance(data, dict) or "feedback" not in data:
            data = {"feedback": []}
        data["feedback"].append(entry)
        _save(_feedback_file(), data)
        return {"ok": True, "feedback": entry}
    except Exception as exc:  # pragma: no cover — defensive
        return {"ok": False, "error": str(exc)}


def list_feedback(opp_id: str | None = None) -> list[dict[str, Any]]:
    data = _load(_feedback_file(), {"feedback": []})
    items = data.get("feedback", []) if isinstance(data, dict) else []
    if opp_id:
        items = [f for f in items if f.get("opp_id") == str(opp_id)]
    return items


def study_session(*, use_llm: bool = True) -> dict[str, Any]:
    """Summarize lessons from recorded feedback into money_memory.json.

    Offline-safe + non-blocking: always returns a deterministic aggregate;
    LLM lessons are additive and guarded. Never raises.
    """
    try:
        items = list_feedback()
        total = len(items)
        ratings = [f["rating"] for f in items if isinstance(f.get("rating"), (int, float))]
        avg_rating = round(sum(ratings) / len(ratings), 2) if ratings else None
        accepted = sum(1 for f in items if f.get("accepted"))
        paid = sum(1 for f in items if f.get("paid"))

        lessons: list[str] = []
        if total == 0:
            lessons.append("No feedback yet — nothing to study.")
        else:
            accept_rate = round(accepted / total, 2)
            lessons.append(f"Acceptance rate {accept_rate} across {total} jobs.")
            if avg_rating is not None:
                lessons.append(f"Average client rating {avg_rating}/5.")
            if accept_rate < 0.5:
                lessons.append("Low acceptance — revisit fit scoring + pricing estimates.")
            if paid < accepted:
                lessons.append("Some accepted jobs unpaid — tighten delivery/follow-up.")

        # Optional LLM deepening — guarded, additive, never blocks the summary.
        if use_llm and total > 0:
            llm_lesson = _llm_lessons(items)
            if llm_lesson:
                lessons.append(llm_lesson)

        memory = {
            "updated_at": _now(),
            "jobs_studied": total,
            "avg_rating": avg_rating,
            "accepted": accepted,
            "paid": paid,
            "lessons": lessons,
        }
        _save(_memory_file(), memory)
        return {"ok": True, **memory}
    except Exception as exc:  # pragma: no cover — defensive
        return {"ok": False, "error": str(exc), "lessons": []}


def _llm_lessons(items: list[dict[str, Any]]) -> str | None:
    try:
        from engine.api import generate
    except Exception:
        return None
    try:
        sample = items[-20:]
        prompt = (
            "Given these completed-work feedback records, give ONE concise lesson "
            "(<=200 chars) to improve future fit-scoring, pricing, or delivery.\n"
            f"{sample}\nLesson:"
        )
        out = generate(prompt=prompt, system="Be concise and actionable.", timeout=30)
        return out.strip()[:200] if isinstance(out, str) and out.strip() else None
    except Exception:
        return None
