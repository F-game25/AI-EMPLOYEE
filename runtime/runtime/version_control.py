"""Version Control — tracks every system change made via Ascend Forge.

Persists a ordered list of snapshots to disk.  Each snapshot captures:
- a diff / code payload
- metadata (module, author, timestamp, performance tag)
- an optional rollback payload

Usage::

    from runtime.version_control import get_version_control

    vc = get_version_control()
    vid = vc.create_snapshot(
        module="core/orchestrator.py",
        code=new_source,
        description="Improve routing logic",
        tag="v1.3",
    )
    vc.set_performance_tag(vid, score=0.87)
    vc.rollback(vid)          # restore snapshot
    vc.list_versions()        # all snapshots
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger("runtime.version_control")

_LOCK = threading.RLock()
_MAX_SNAPSHOTS = int(os.environ.get("AI_EMPLOYEE_MAX_SNAPSHOTS", "200"))


def _default_state_path() -> Path:
    home = os.getenv("AI_HOME")
    base = Path(home) if home else Path(__file__).resolve().parents[3]
    path = base / "state" / "version_control.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _ts() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _sha(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8", errors="replace")).hexdigest()[:12]


class VersionControl:
    """File-backed version history for AI Employee system evolution.

    Snapshots are kept newest-first in memory; the file is written atomically
    on each mutation.

    Attributes
    ----------
    _snapshots : list[dict]
        Ordered list of version records (newest first).
    """

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or _default_state_path()
        self._snapshots: list[dict[str, Any]] = []
        self._load()
        logger.info("VersionControl ready — %d snapshots loaded", len(self._snapshots))

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load(self) -> None:
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            if isinstance(raw, dict) and "snapshots" in raw:
                self._snapshots = raw["snapshots"]
            elif isinstance(raw, list):
                self._snapshots = raw
        except Exception:
            self._snapshots = []

    def _save(self) -> None:
        payload = {
            "updated_at": _ts(),
            "count": len(self._snapshots),
            "snapshots": self._snapshots,
        }
        self._path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def create_snapshot(
        self,
        *,
        module: str,
        code: str,
        description: str = "",
        tag: str = "",
        author: str = "forge",
        previous_code: str = "",
    ) -> str:
        """Create a new version snapshot.

        Args:
            module:        Module path (relative to repo root), e.g. ``"core/orchestrator.py"``.
            code:          New source code (or diff payload).
            description:   Human-readable description of the change.
            tag:           Optional version tag (e.g. ``"v1.3"``).
            author:        Who created this snapshot.
            previous_code: Prior source for rollback (fetched from disk when blank).

        Returns:
            The unique snapshot ID (12-char SHA prefix).
        """
        vid = _sha(f"{module}|{code}|{_ts()}")
        record: dict[str, Any] = {
            "id": vid,
            "module": module,
            "description": description,
            "tag": tag,
            "author": author,
            "ts": _ts(),
            "code_sha": _sha(code),
            "code": code[:50_000],          # cap stored payload
            "rollback_code": previous_code[:50_000],
            "performance_score": None,
            "status": "pending",            # pending | deployed | rolled_back
        }
        with _LOCK:
            self._snapshots.insert(0, record)  # newest first
            # Trim when over limit
            if len(self._snapshots) > _MAX_SNAPSHOTS:
                self._snapshots = self._snapshots[:_MAX_SNAPSHOTS]
            self._save()
        logger.info("Snapshot created: %s  module=%s  tag=%s", vid, module, tag)
        return vid

    def set_status(self, snapshot_id: str, status: str) -> bool:
        """Update the deployment status of a snapshot."""
        with _LOCK:
            for snap in self._snapshots:
                if snap["id"] == snapshot_id:
                    snap["status"] = status
                    snap["updated_at"] = _ts()
                    self._save()
                    return True
        return False

    def set_performance_tag(self, snapshot_id: str, *, score: float) -> bool:
        """Attach a 0–1 performance score to a snapshot."""
        with _LOCK:
            for snap in self._snapshots:
                if snap["id"] == snapshot_id:
                    snap["performance_score"] = round(float(score), 4)
                    snap["updated_at"] = _ts()
                    self._save()
                    return True
        return False

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get(self, snapshot_id: str) -> dict[str, Any] | None:
        """Return a snapshot by ID, or None if not found."""
        with _LOCK:
            for snap in self._snapshots:
                if snap["id"] == snapshot_id:
                    return dict(snap)
        return None

    def list_versions(
        self,
        *,
        module: str | None = None,
        limit: int = 50,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return snapshots, optionally filtered by module or status."""
        with _LOCK:
            results = list(self._snapshots)
        if module:
            results = [s for s in results if s.get("module") == module]
        if status:
            results = [s for s in results if s.get("status") == status]
        return results[:limit]

    def rollback(self, snapshot_id: str) -> dict[str, Any]:
        """Apply the rollback_code from a snapshot back to disk.

        Returns a status dict with ``success``, ``module``, ``snapshot_id``.
        """
        snap = self.get(snapshot_id)
        if snap is None:
            return {"success": False, "error": f"Snapshot {snapshot_id!r} not found"}

        rollback_code = snap.get("rollback_code", "")
        module = snap.get("module", "")

        if not rollback_code:
            return {
                "success": False,
                "error": "No rollback_code stored for this snapshot",
                "snapshot_id": snapshot_id,
            }

        target = _resolve_module_path(module)
        if target is None:
            return {
                "success": False,
                "error": f"Cannot resolve module path: {module!r}",
            }

        try:
            target.write_text(rollback_code, encoding="utf-8")
            self.set_status(snapshot_id, "rolled_back")
            logger.info("Rolled back %s from snapshot %s", module, snapshot_id)
            return {"success": True, "module": module, "snapshot_id": snapshot_id, "ts": _ts()}
        except OSError as exc:
            return {"success": False, "error": str(exc)}

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def summary(self) -> dict[str, Any]:
        with _LOCK:
            snaps = list(self._snapshots)
        total = len(snaps)
        deployed = sum(1 for s in snaps if s.get("status") == "deployed")
        rolled_back = sum(1 for s in snaps if s.get("status") == "rolled_back")
        scores = [s["performance_score"] for s in snaps if s.get("performance_score") is not None]
        return {
            "total_snapshots": total,
            "deployed": deployed,
            "rolled_back": rolled_back,
            "avg_performance_score": round(sum(scores) / max(len(scores), 1), 4) if scores else None,
            "latest": snaps[0] if snaps else None,
            "ts": _ts(),
        }


# ── Module path resolver ──────────────────────────────────────────────────────

def _resolve_module_path(module: str) -> Path | None:
    """Attempt to resolve a module string to an absolute path."""
    repo_root = Path(__file__).resolve().parents[3]
    candidates = [
        repo_root / "runtime" / module,
        repo_root / module,
    ]
    for c in candidates:
        if c.exists():
            return c
    # Path doesn't exist yet (new module) — use runtime/ as base
    p = repo_root / "runtime" / module
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


# ── Singleton ─────────────────────────────────────────────────────────────────

_instance: VersionControl | None = None
_instance_lock = threading.Lock()


def get_version_control() -> VersionControl:
    """Return the process-wide VersionControl singleton."""
    global _instance
    with _instance_lock:
        if _instance is None:
            _instance = VersionControl()
    return _instance
