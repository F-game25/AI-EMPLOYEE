"""Short-Term Cache — fast, TTL-based in-process memory.

Holds recent context, pending agent results, and transient signals that
expire automatically.  Nothing here is persisted to disk — the cache is
fully in-memory and resets on process restart.

Usage::

    from memory.short_term_cache import get_short_term_cache

    cache = get_short_term_cache()
    cache.set("last_task", {"input": "write email"}, ttl=300)  # 5-minute TTL
    value = cache.get("last_task")   # returns None after TTL expires
    cache.delete("last_task")
    cache.flush()                    # clear everything

Design notes
------------
- Thread-safe via a single RLock.
- Expired entries are lazily removed on ``get()`` and via a periodic
  sweep triggered every ``_SWEEP_INTERVAL`` writes.
- Maximum ``_MAX_ENTRIES`` entries; when full the entry closest to
  expiry is evicted.
"""
from __future__ import annotations

import threading
import time
from typing import Any

_DEFAULT_TTL: float = 300.0       # seconds — 5 minutes
_MAX_ENTRIES: int   = 500
_SWEEP_INTERVAL: int = 50         # sweep every N writes
_LOCK = threading.RLock()


def _now() -> float:
    return time.monotonic()


class ShortTermCache:
    """Thread-safe TTL cache for transient agent context."""

    def __init__(
        self,
        *,
        default_ttl: float = _DEFAULT_TTL,
        max_entries: int = _MAX_ENTRIES,
    ) -> None:
        # _store: key → {"value": Any, "expires_at": float}
        self._store: dict[str, dict[str, Any]] = {}
        self._default_ttl = default_ttl
        self._max_entries = max_entries
        self._write_count = 0

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def set(
        self,
        key: str,
        value: Any,
        *,
        ttl: float | None = None,
    ) -> None:
        """Store *value* under *key* for *ttl* seconds.

        Args:
            key:   Cache key.
            value: Arbitrary Python value (must be cheap to hold in memory).
            ttl:   Time-to-live in seconds.  Defaults to ``default_ttl``.
        """
        effective_ttl = ttl if ttl is not None else self._default_ttl
        with _LOCK:
            self._store[key] = {
                "value": value,
                "expires_at": _now() + max(0.0, float(effective_ttl)),
            }
            self._write_count += 1

            # Evict when full
            if len(self._store) > self._max_entries:
                self._evict_one()

            # Periodic sweep
            if self._write_count % _SWEEP_INTERVAL == 0:
                self._sweep()

    def extend(self, key: str, *, extra_ttl: float) -> bool:
        """Extend the TTL of an existing entry.  Returns False if missing/expired."""
        with _LOCK:
            entry = self._store.get(key)
            if entry is None or entry["expires_at"] < _now():
                self._store.pop(key, None)
                return False
            entry["expires_at"] += float(extra_ttl)
            return True

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get(self, key: str, default: Any = None) -> Any:
        """Return the cached value, or *default* if missing or expired."""
        with _LOCK:
            entry = self._store.get(key)
            if entry is None:
                return default
            if entry["expires_at"] < _now():
                del self._store[key]
                return default
            return entry["value"]

    def exists(self, key: str) -> bool:
        """Return True if *key* exists and has not expired."""
        with _LOCK:
            entry = self._store.get(key)
            if entry is None:
                return False
            if entry["expires_at"] < _now():
                del self._store[key]
                return False
            return True

    def ttl_remaining(self, key: str) -> float:
        """Return seconds until *key* expires, or 0 if missing/expired."""
        with _LOCK:
            entry = self._store.get(key)
            if entry is None:
                return 0.0
            remaining = entry["expires_at"] - _now()
            return max(0.0, remaining)

    # ------------------------------------------------------------------
    # Delete / flush
    # ------------------------------------------------------------------

    def delete(self, key: str) -> bool:
        """Remove *key*.  Returns True if it existed (and hadn't expired)."""
        with _LOCK:
            entry = self._store.pop(key, None)
            return entry is not None and entry["expires_at"] >= _now()

    def flush(self) -> int:
        """Clear all entries.  Returns the number removed."""
        with _LOCK:
            count = len(self._store)
            self._store.clear()
            return count

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def size(self) -> int:
        """Return number of live (non-expired) entries."""
        now = _now()
        with _LOCK:
            return sum(1 for e in self._store.values() if e["expires_at"] >= now)

    def keys(self) -> list[str]:
        """Return all live keys."""
        now = _now()
        with _LOCK:
            return [k for k, e in self._store.items() if e["expires_at"] >= now]

    def snapshot(self) -> dict[str, Any]:
        """Return a copy of all live entries (without internal metadata)."""
        now = _now()
        with _LOCK:
            return {
                k: e["value"]
                for k, e in self._store.items()
                if e["expires_at"] >= now
            }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _sweep(self) -> None:
        """Remove all expired entries (must be called with _LOCK held)."""
        now = _now()
        expired = [k for k, e in self._store.items() if e["expires_at"] < now]
        for k in expired:
            del self._store[k]

    def _evict_one(self) -> None:
        """Evict the entry with the smallest remaining TTL (held with _LOCK)."""
        if not self._store:
            return
        victim = min(self._store, key=lambda k: self._store[k]["expires_at"])
        del self._store[victim]


# ── Sentinel ──────────────────────────────────────────────────────────────────

class _SentinelType:
    def __repr__(self) -> str:
        return "<MISSING>"

_SENTINEL = _SentinelType()


# ── Singleton ─────────────────────────────────────────────────────────────────

_instance: ShortTermCache | None = None
_instance_lock = threading.Lock()


def get_short_term_cache() -> ShortTermCache:
    """Return the process-wide ShortTermCache singleton."""
    global _instance
    with _instance_lock:
        if _instance is None:
            _instance = ShortTermCache()
    return _instance
