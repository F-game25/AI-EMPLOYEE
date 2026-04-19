"""Data Lifecycle Manager — automatic TTL, configurable retention, and purge scheduling.

Applies to all persistent stores in the ASCEND AI runtime:

  ┌─────────────────────────────────────────────────────────────────────────┐
  │  Store                 │ Default TTL │ Backing format                   │
  │────────────────────────────────────────────────────────────────────────│
  │  audit_log             │  90 days    │ SQLite  (state/audit_log.db)      │
  │  observability_events  │  30 days    │ SQLite  (state/observability_…db) │
  │  chat_history          │  60 days    │ JSONL   (state/chatlog.jsonl)     │
  │  activity_log          │  30 days    │ JSONL   (state/activity_log.jsonl)│
  │  memory_index          │ 365 days    │ JSON    (state/memory_index.json) │
  └─────────────────────────────────────────────────────────────────────────┘

────────────────────────────────────────────────────────────────
CONFIGURATION
────────────────────────────────────────────────────────────────

All TTLs can be overridden via environment variables (days as integers):

  LIFECYCLE_TTL_AUDIT_LOG             (default 90)
  LIFECYCLE_TTL_OBSERVABILITY_EVENTS  (default 30)
  LIFECYCLE_TTL_CHAT_HISTORY          (default 60)
  LIFECYCLE_TTL_ACTIVITY_LOG          (default 30)
  LIFECYCLE_TTL_MEMORY_INDEX          (default 365)

Set to 0 to disable purging for that store.

────────────────────────────────────────────────────────────────
PUBLIC API
────────────────────────────────────────────────────────────────

::

    from core.data_lifecycle_manager import get_lifecycle_manager, RetentionPolicy

    mgr = get_lifecycle_manager()

    # Run a full purge pass across all stores
    report = mgr.purge_all()

    # Purge a specific store
    result = mgr.purge("chat_history")

    # Get the current retention policies
    policies = mgr.get_policies()

    # Override a TTL at runtime (days; 0 = disabled)
    mgr.set_ttl("memory_index", days=180)

────────────────────────────────────────────────────────────────
ARCHITECTURE
────────────────────────────────────────────────────────────────

Each store has a ``StoreHandler`` that knows how to:

  1. Locate the backing file/db via environment-aware path resolution
  2. Count records older than the TTL cutoff
  3. Delete those records and return a ``PurgeResult``

All operations are thread-safe.  The manager also exposes a lightweight
``PurgeScheduler`` that runs purges in a background daemon thread at a
configurable interval (default: every 24 hours).  The scheduler is purely
opt-in and is **not** started automatically — call ``mgr.start_scheduler()``
to activate it.
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("ai_employee.data_lifecycle")

# ── Default TTLs (days) ───────────────────────────────────────────────────────

_DEFAULT_TTLS: dict[str, int] = {
    "audit_log":            90,
    "observability_events": 30,
    "chat_history":         60,
    "activity_log":         30,
    "memory_index":         365,
}

_ENV_KEYS: dict[str, str] = {
    "audit_log":            "LIFECYCLE_TTL_AUDIT_LOG",
    "observability_events": "LIFECYCLE_TTL_OBSERVABILITY_EVENTS",
    "chat_history":         "LIFECYCLE_TTL_CHAT_HISTORY",
    "activity_log":         "LIFECYCLE_TTL_ACTIVITY_LOG",
    "memory_index":         "LIFECYCLE_TTL_MEMORY_INDEX",
}


# ── Data structures ───────────────────────────────────────────────────────────

@dataclass
class RetentionPolicy:
    """Per-store retention configuration."""
    store_id:      str
    ttl_days:      int          # 0 = disabled (no auto-purge)
    store_type:    str          # "sqlite" | "jsonl" | "json"
    description:   str          = ""

    @property
    def enabled(self) -> bool:
        return self.ttl_days > 0

    def cutoff_epoch(self) -> float:
        """Return the Unix timestamp before which records are expired."""
        return time.time() - (self.ttl_days * 86400)

    def cutoff_iso(self) -> str:
        """Return an ISO-8601 string matching the cutoff for SQL comparisons."""
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(self.cutoff_epoch()))

    def to_dict(self) -> dict[str, Any]:
        return {
            "store_id":     self.store_id,
            "ttl_days":     self.ttl_days,
            "store_type":   self.store_type,
            "description":  self.description,
            "enabled":      self.enabled,
            "cutoff_iso":   self.cutoff_iso() if self.enabled else None,
        }


@dataclass
class PurgeResult:
    """Result of a single purge operation."""
    store_id:       str
    deleted:        int          = 0
    retained:       int          = 0
    skipped:        bool         = False   # TTL disabled or file absent
    error:          str          = ""
    duration_ms:    float        = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "store_id":    self.store_id,
            "deleted":     self.deleted,
            "retained":    self.retained,
            "skipped":     self.skipped,
            "error":       self.error,
            "duration_ms": self.duration_ms,
        }


# ── Path resolution ───────────────────────────────────────────────────────────

def _state_dir() -> Path:
    ai_home = os.environ.get("AI_HOME", "")
    base = Path(ai_home) if ai_home else Path(__file__).resolve().parents[3]
    return base / "state"


def _default_db_path(filename: str) -> Path:
    return _state_dir() / filename


def _default_jsonl_path(filename: str) -> Path:
    return _state_dir() / filename


def _default_json_path(filename: str) -> Path:
    return _state_dir() / filename


# ── Store handlers ────────────────────────────────────────────────────────────

class _SqliteHandler:
    """Handler for SQLite-backed stores.

    Expects a ``ts`` column containing ISO-8601 timestamps (``%Y-%m-%dT%H:%M:%SZ``).
    """

    def __init__(self, db_path: Path, table: str, ts_column: str = "ts") -> None:
        self._db_path   = db_path
        self._table     = table
        self._ts_col    = ts_column

    def count_total(self) -> int:
        if not self._db_path.exists():
            return 0
        try:
            with self._conn() as conn:
                row = conn.execute(f"SELECT COUNT(*) FROM {self._table}").fetchone()
                return int(row[0]) if row else 0
        except Exception:
            return 0

    def purge(self, policy: RetentionPolicy) -> PurgeResult:
        t0 = time.monotonic()
        result = PurgeResult(store_id=policy.store_id)
        if not policy.enabled:
            result.skipped = True
            return result
        if not self._db_path.exists():
            result.skipped = True
            return result
        try:
            cutoff = policy.cutoff_iso()
            with self._conn() as conn:
                cursor = conn.execute(
                    f"DELETE FROM {self._table} WHERE {self._ts_col} < ?",
                    (cutoff,),
                )
                result.deleted = cursor.rowcount
            result.retained = max(0, self.count_total())
        except Exception as exc:
            result.error = str(exc)
            logger.warning("Lifecycle purge error (%s): %s", policy.store_id, exc)
        result.duration_ms = round((time.monotonic() - t0) * 1000, 2)
        return result

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._db_path))
        conn.row_factory = sqlite3.Row
        return conn


class _JsonlHandler:
    """Handler for JSONL log files.

    Each line must be a JSON object with a ``ts`` key holding an ISO-8601
    timestamp.  Lines that are not valid JSON or lack a ``ts`` field are
    treated as retained (never purged) to avoid losing data.
    """

    def __init__(self, path: Path) -> None:
        self._path = path

    def count_total(self) -> int:
        if not self._path.exists():
            return 0
        try:
            return sum(1 for _ in self._path.read_text(encoding="utf-8", errors="replace").splitlines() if _.strip())
        except Exception:
            return 0

    def purge(self, policy: RetentionPolicy) -> PurgeResult:
        t0 = time.monotonic()
        result = PurgeResult(store_id=policy.store_id)
        if not policy.enabled:
            result.skipped = True
            return result
        if not self._path.exists():
            result.skipped = True
            return result
        try:
            cutoff = policy.cutoff_epoch()
            raw = self._path.read_text(encoding="utf-8", errors="replace")
            lines = [l for l in raw.splitlines() if l.strip()]
            kept: list[str] = []
            deleted = 0
            for line in lines:
                try:
                    obj = json.loads(line)
                    ts_str = obj.get("ts") or obj.get("timestamp") or ""
                    ts_epoch = _parse_iso(ts_str)
                    if ts_epoch is not None and ts_epoch < cutoff:
                        deleted += 1
                        continue
                except Exception:
                    pass  # Malformed lines are always kept
                kept.append(line)
            # Atomically replace the file
            new_content = "\n".join(kept)
            if new_content:
                new_content += "\n"
            self._path.write_text(new_content, encoding="utf-8")
            result.deleted  = deleted
            result.retained = len(kept)
        except Exception as exc:
            result.error = str(exc)
            logger.warning("Lifecycle purge error (%s): %s", policy.store_id, exc)
        result.duration_ms = round((time.monotonic() - t0) * 1000, 2)
        return result


class _MemoryIndexHandler:
    """Handler for the JSON memory index (state/memory_index.json).

    Memory entries are expired based on their ``last_used`` timestamp.
    """

    def __init__(self, path: Path) -> None:
        self._path = path

    def count_total(self) -> int:
        if not self._path.exists():
            return 0
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
            memories = payload.get("memories", []) if isinstance(payload, dict) else payload
            return len(memories) if isinstance(memories, list) else 0
        except Exception:
            return 0

    def purge(self, policy: RetentionPolicy) -> PurgeResult:
        t0 = time.monotonic()
        result = PurgeResult(store_id=policy.store_id)
        if not policy.enabled:
            result.skipped = True
            return result
        if not self._path.exists():
            result.skipped = True
            return result
        try:
            cutoff = policy.cutoff_epoch()
            raw = self._path.read_text(encoding="utf-8")
            payload = json.loads(raw)
            memories: list[dict[str, Any]] = (
                payload.get("memories", []) if isinstance(payload, dict) else payload
            )
            if not isinstance(memories, list):
                result.skipped = True
                return result

            kept: list[dict[str, Any]] = []
            deleted = 0
            for m in memories:
                ts_epoch = _parse_iso(m.get("last_used") or m.get("ts"))
                if ts_epoch is not None and ts_epoch < cutoff:
                    deleted += 1
                else:
                    kept.append(m)

            updated: dict[str, Any] = (
                {**payload, "memories": kept, "updated_at": _iso_now()}
                if isinstance(payload, dict)
                else {"memories": kept, "updated_at": _iso_now()}
            )
            self._path.write_text(json.dumps(updated, indent=2), encoding="utf-8")
            result.deleted  = deleted
            result.retained = len(kept)
        except Exception as exc:
            result.error = str(exc)
            logger.warning("Lifecycle purge error (%s): %s", policy.store_id, exc)
        result.duration_ms = round((time.monotonic() - t0) * 1000, 2)
        return result


# ── Utilities ─────────────────────────────────────────────────────────────────

def _parse_iso(value: str | None) -> Optional[float]:
    if not value:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return time.mktime(time.strptime(value[:19], fmt[:len(fmt)]))
        except Exception:
            continue
    return None


def _iso_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _ttl_from_env(store_id: str, default: int) -> int:
    env_key = _ENV_KEYS.get(store_id, "")
    raw = os.environ.get(env_key, "").strip()
    if raw.isdigit():
        return int(raw)
    return default


# ── Background scheduler ──────────────────────────────────────────────────────

class PurgeScheduler:
    """Runs ``mgr.purge_all()`` periodically in a background daemon thread."""

    def __init__(self, manager: "DataLifecycleManager", interval_hours: float = 24.0) -> None:
        self._manager  = manager
        self._interval = interval_hours * 3600
        self._thread:  Optional[threading.Thread] = None
        self._stop_evt = threading.Event()

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_evt.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="lifecycle-purge-scheduler",
            daemon=True,
        )
        self._thread.start()
        logger.info("DataLifecycle scheduler started (interval=%.1fh)", self._interval / 3600)

    def stop(self) -> None:
        self._stop_evt.set()

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def _run(self) -> None:
        while not self._stop_evt.is_set():
            try:
                self._manager.purge_all()
            except Exception as exc:
                logger.warning("Lifecycle scheduler purge error: %s", exc)
            self._stop_evt.wait(timeout=self._interval)


# ── DataLifecycleManager ──────────────────────────────────────────────────────

class DataLifecycleManager:
    """Central data lifecycle manager.

    Maintains one ``RetentionPolicy`` per store and a matching handler that
    knows how to purge that store.  All public methods are thread-safe.

    Usage::

        mgr = get_lifecycle_manager()
        report = mgr.purge_all()   # returns {store_id: PurgeResult, ...}
    """

    def __init__(self, *, state_dir: Optional[Path] = None) -> None:
        self._lock      = threading.RLock()
        self._sdir      = state_dir or _state_dir()
        self._policies: dict[str, RetentionPolicy] = {}
        self._handlers: dict[str, Any]             = {}
        self._scheduler: Optional[PurgeScheduler]  = None
        self._last_run:  Optional[str]             = None
        self._build_stores()

    # ── Setup ─────────────────────────────────────────────────────────────────

    def _build_stores(self) -> None:
        sdir = self._sdir

        self._register(
            store_id   = "audit_log",
            ttl_days   = _ttl_from_env("audit_log", _DEFAULT_TTLS["audit_log"]),
            store_type = "sqlite",
            description= "Audit events in state/audit_log.db",
            handler    = _SqliteHandler(sdir / "audit_log.db", "audit_log"),
        )
        self._register(
            store_id   = "observability_events",
            ttl_days   = _ttl_from_env("observability_events", _DEFAULT_TTLS["observability_events"]),
            store_type = "sqlite",
            description= "Event stream in state/observability_events.db",
            handler    = _SqliteHandler(sdir / "observability_events.db", "event_stream"),
        )
        self._register(
            store_id   = "chat_history",
            ttl_days   = _ttl_from_env("chat_history", _DEFAULT_TTLS["chat_history"]),
            store_type = "jsonl",
            description= "Chat messages in state/chatlog.jsonl",
            handler    = _JsonlHandler(sdir / "chatlog.jsonl"),
        )
        self._register(
            store_id   = "activity_log",
            ttl_days   = _ttl_from_env("activity_log", _DEFAULT_TTLS["activity_log"]),
            store_type = "jsonl",
            description= "Activity events in state/activity_log.jsonl",
            handler    = _JsonlHandler(sdir / "activity_log.jsonl"),
        )
        self._register(
            store_id   = "memory_index",
            ttl_days   = _ttl_from_env("memory_index", _DEFAULT_TTLS["memory_index"]),
            store_type = "json",
            description= "Agent memory entries in state/memory_index.json",
            handler    = _MemoryIndexHandler(sdir / "memory_index.json"),
        )

    def _register(
        self,
        *,
        store_id:   str,
        ttl_days:   int,
        store_type: str,
        description: str,
        handler:    Any,
    ) -> None:
        self._policies[store_id] = RetentionPolicy(
            store_id   = store_id,
            ttl_days   = ttl_days,
            store_type = store_type,
            description= description,
        )
        self._handlers[store_id] = handler

    # ── Public API ────────────────────────────────────────────────────────────

    def get_policies(self) -> dict[str, dict[str, Any]]:
        """Return all retention policies as plain dicts."""
        with self._lock:
            return {sid: p.to_dict() for sid, p in self._policies.items()}

    def get_policy(self, store_id: str) -> Optional[dict[str, Any]]:
        """Return the policy for one store, or None if unknown."""
        with self._lock:
            p = self._policies.get(store_id)
            return p.to_dict() if p else None

    def set_ttl(self, store_id: str, *, days: int) -> bool:
        """Override the TTL for a store at runtime.

        Args:
            store_id: One of the known store IDs.
            days:     New TTL in days (0 = disabled).

        Returns:
            True if the store was found and updated, False otherwise.
        """
        with self._lock:
            policy = self._policies.get(store_id)
            if policy is None:
                return False
            policy.ttl_days = max(0, int(days))
            return True

    def purge(self, store_id: str) -> PurgeResult:
        """Purge a single store, returning a :class:`PurgeResult`.

        Returns a skipped result if the store_id is not registered.
        """
        with self._lock:
            policy  = self._policies.get(store_id)
            handler = self._handlers.get(store_id)
        if policy is None or handler is None:
            return PurgeResult(store_id=store_id, skipped=True, error="unknown store")
        result = handler.purge(policy)
        if result.deleted > 0 or result.error:
            logger.info(
                "Lifecycle purge [%s]: deleted=%d retained=%d duration=%.1fms%s",
                store_id, result.deleted, result.retained, result.duration_ms,
                f" error={result.error}" if result.error else "",
            )
        return result

    def purge_all(self) -> dict[str, PurgeResult]:
        """Purge all registered stores.

        Returns a dict of ``store_id → PurgeResult``.
        """
        with self._lock:
            store_ids = list(self._policies.keys())
        results: dict[str, PurgeResult] = {}
        for sid in store_ids:
            results[sid] = self.purge(sid)
        self._last_run = _iso_now()
        total_deleted = sum(r.deleted for r in results.values())
        logger.info("Lifecycle purge_all: %d records deleted across %d stores", total_deleted, len(store_ids))
        return results

    def status(self) -> dict[str, Any]:
        """Return a health snapshot: policies + scheduler state + last run time."""
        with self._lock:
            policies = {sid: p.to_dict() for sid, p in self._policies.items()}
            sch_running = self._scheduler.is_running() if self._scheduler else False
        return {
            "policies":    policies,
            "last_run":    self._last_run,
            "scheduler":   {"running": sch_running},
            "store_count": len(policies),
        }

    # ── Scheduler ─────────────────────────────────────────────────────────────

    def start_scheduler(self, *, interval_hours: float = 24.0) -> None:
        """Start the background purge scheduler.

        Safe to call multiple times — only one thread is ever running.
        """
        with self._lock:
            if self._scheduler is None:
                self._scheduler = PurgeScheduler(self, interval_hours=interval_hours)
            if not self._scheduler.is_running():
                self._scheduler._interval = interval_hours * 3600
                self._scheduler.start()

    def stop_scheduler(self) -> None:
        """Stop the background purge scheduler (if running)."""
        with self._lock:
            sch = self._scheduler
        if sch is not None:
            sch.stop()

    def scheduler_running(self) -> bool:
        with self._lock:
            return self._scheduler is not None and self._scheduler.is_running()


# ── Singleton ─────────────────────────────────────────────────────────────────

_manager_instance: Optional[DataLifecycleManager] = None
_manager_lock = threading.Lock()


def get_lifecycle_manager() -> DataLifecycleManager:
    """Return the process-wide :class:`DataLifecycleManager` singleton."""
    global _manager_instance
    with _manager_lock:
        if _manager_instance is None:
            _manager_instance = DataLifecycleManager()
    return _manager_instance
