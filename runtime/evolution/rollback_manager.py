"""RollbackManager — version tracking + rollback per target.

Tracks active/previous/candidate versions per target and records auto-rollback
triggers (latency spike, error-rate spike, negative feedback, test failure,
safety flag). Persistent JSON so a promotion's rollback artifact always exists
before the promotion gate allows it through.
"""
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from typing import Any, Optional

from evolution import METRICS_DIR, ensure_dirs
from evolution.scrub import scrub

AUTO_ROLLBACK_TRIGGERS = (
    "latency_spike", "error_rate_spike", "negative_feedback",
    "test_failure", "safety_flag",
)


def _iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class RollbackManager:
    def __init__(self):
        self._lock = threading.Lock()
        self._path = METRICS_DIR / "versions.json"
        self._state: dict[str, Any] = self._load()

    def _load(self) -> dict[str, Any]:
        if self._path.exists():
            try:
                return json.loads(self._path.read_text(encoding="utf-8"))
            except Exception:
                return {}
        return {}

    def _save(self) -> None:
        ensure_dirs()
        self._path.write_text(json.dumps(scrub(self._state), ensure_ascii=False, indent=2),
                              encoding="utf-8")

    def record_rollback_artifact(self, target: str, active_version: str,
                                 snapshot: dict[str, Any] | None = None) -> dict[str, Any]:
        """Capture the current active version BEFORE applying a candidate."""
        with self._lock:
            entry = self._state.setdefault(target, {"active": None, "previous": None,
                                                     "candidate": None, "history": []})
            entry["active"] = active_version
            entry["rollback_artifact"] = {"version": active_version,
                                          "snapshot": snapshot or {}, "captured_at": _iso()}
            self._save()
            return entry["rollback_artifact"]

    def stage_candidate(self, target: str, candidate_version: str) -> None:
        with self._lock:
            entry = self._state.setdefault(target, {"active": None, "previous": None,
                                                     "candidate": None, "history": []})
            entry["candidate"] = candidate_version
            self._save()

    def promote(self, target: str, candidate_version: str) -> None:
        with self._lock:
            entry = self._state.setdefault(target, {"active": None, "previous": None,
                                                     "candidate": None, "history": []})
            entry["previous"] = entry.get("active")
            entry["active"] = candidate_version
            entry["candidate"] = None
            entry["history"].append({"action": "promote", "version": candidate_version, "at": _iso()})
            self._save()

    def rollback(self, target: str, trigger: str = "manual") -> bool:
        with self._lock:
            entry = self._state.get(target)
            if not entry:
                return False
            prev = entry.get("previous") or (entry.get("rollback_artifact") or {}).get("version")
            if prev is None:
                return False
            entry["active"], entry["previous"] = prev, entry.get("active")
            entry["history"].append({"action": "rollback", "to": prev,
                                     "trigger": trigger, "at": _iso()})
            self._save()
            return True

    def has_rollback_artifact(self, target: str) -> bool:
        return bool(self._state.get(target, {}).get("rollback_artifact"))

    def get(self, target: str) -> Optional[dict[str, Any]]:
        return self._state.get(target)


__all__ = ["RollbackManager", "AUTO_ROLLBACK_TRIGGERS"]
