"""Change Log — cross-session audit trail.

Every side-effecting action in the system is recorded here.
Entries are written as newline-delimited JSON to
~/.ai-employee/changelog.jsonl.

Usage::

    from core.change_log import get_changelog

    log = get_changelog()
    log.record(
        actor="task_engine",
        action_type="task_completed",
        reason="all validators passed",
        before={"status": "running"},
        after={"status": "done"},
        outcome="success",
    )
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any


_DEFAULT_PATH = Path.home() / ".ai-employee" / "changelog.jsonl"


class ChangeLog:
    """Thread-safe append-only audit log backed by a JSONL file."""

    def __init__(self, path: Path | None = None) -> None:
        self._path: Path = path or _DEFAULT_PATH
        self._lock = threading.Lock()
        self._path.parent.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def record(
        self,
        *,
        actor: str,
        action_type: str,
        reason: str = "",
        before: Any = None,
        after: Any = None,
        outcome: str = "",
    ) -> dict:
        """Append one entry and return it."""
        entry = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "actor": actor,
            "action_type": action_type,
            "reason": reason,
            "before": before,
            "after": after,
            "outcome": outcome,
        }
        with self._lock:
            with self._path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return entry

    def read(self, *, limit: int = 100, offset: int = 0) -> list[dict]:
        """Return up to *limit* entries starting at *offset* (newest first)."""
        if not self._path.exists():
            return []
        with self._lock:
            lines = self._path.read_text(encoding="utf-8").splitlines()
        entries = []
        for line in reversed(lines):
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
        return entries[offset : offset + limit]

    def total(self) -> int:
        """Return the total number of log entries."""
        if not self._path.exists():
            return 0
        with self._lock:
            text = self._path.read_text(encoding="utf-8")
        return sum(1 for line in text.splitlines() if line.strip())


# ── Singleton ─────────────────────────────────────────────────────────────────

_instance: ChangeLog | None = None
_instance_lock = threading.Lock()


def get_changelog(path: Path | None = None) -> ChangeLog:
    """Return the process-wide ChangeLog singleton."""
    global _instance
    with _instance_lock:
        if _instance is None:
            _instance = ChangeLog(path)
    return _instance
