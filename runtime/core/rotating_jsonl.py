"""Size-bounded append-only JSONL writer with rotation.

Bounds disk usage for high-volume operational logs (telemetry, traces) that
otherwise grow without limit — see docs/SYSTEM_COHERENCE_PLAN.md C0, where a
stray ``telemetry.jsonl`` reached 134 MB. When the active file would exceed
``max_bytes`` it is rotated (``<path>`` → ``<path>.1`` → … → ``<path>.<backups>``)
and the oldest segment is discarded, so total disk is bounded by
``max_bytes * (backups + 1)``.

This mirrors ``logging.handlers.RotatingFileHandler`` but keeps the JSONL /
batched-write semantics the telemetry writers already use. Rotation is O(1)
amortized (a size check + occasional rename) — not a whole-file rewrite — so it
is safe on the hot telemetry path.

Reuse this for any append-only JSONL that can grow unbounded; do not re-roll a
new mechanism. The append+rotate critical section is guarded by BOTH a per-path
in-process lock (cheap thread serialization) AND an inter-process ``FileLock``
(fcntl, via a sidecar ``.lock`` that survives rotation) — because the two
telemetry modules that share one file can run in separate processes, where a
``threading.Lock`` alone would not serialize the size-check/rotate/append race.
The inter-process lock is best-effort: if it cannot be acquired the write still
proceeds (telemetry must never crash the caller) under the in-process lock.

Thresholds are env-configurable (never hardcode call sites):
  - ``JSONL_LOG_MAX_BYTES`` — active-segment cap (default 64 MiB)
  - ``JSONL_LOG_BACKUPS``   — rolled segments to keep (default 3)
"""
from __future__ import annotations

import json
import os
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable, Iterator

# 64 MiB active + 3 backups = 256 MiB worst-case per logical log.
_DEFAULT_MAX_BYTES = int(os.environ.get("JSONL_LOG_MAX_BYTES", str(64 * 1024 * 1024)))
_DEFAULT_BACKUPS = int(os.environ.get("JSONL_LOG_BACKUPS", "3"))

_LOCKS: dict[str, threading.Lock] = {}
_LOCKS_GUARD = threading.Lock()


def _lock_for(path: Path) -> threading.Lock:
    key = str(path)
    lk = _LOCKS.get(key)
    if lk is None:
        with _LOCKS_GUARD:
            lk = _LOCKS.setdefault(key, threading.Lock())
    return lk


@contextmanager
def _interprocess_lock(path: Path) -> Iterator[None]:
    """Best-effort inter-process exclusive lock around rotate+append.

    Uses ``core.file_lock.FileLock`` (fcntl on a sidecar ``<path>.lock`` that
    survives rotation). Degrades to a no-op if the lock module is unavailable or
    the lock cannot be acquired within the timeout — the caller still holds the
    in-process lock, and losing telemetry is preferable to crashing the hot path.
    """
    try:
        from core.file_lock import FileLock
    except Exception:
        yield
        return
    try:
        with FileLock(path, timeout=2.0):
            yield
    except Exception:
        yield


def _rotate(path: Path, backups: int) -> None:
    """Shift segments: drop ``.<backups>``, bump ``.i`` → ``.i+1``, ``path`` → ``.1``."""
    if backups <= 0:
        # No history kept — truncate the active file.
        try:
            path.unlink()
        except OSError:
            pass
        return
    oldest = path.with_name(f"{path.name}.{backups}")
    try:
        if oldest.exists():
            oldest.unlink()
    except OSError:
        pass
    for i in range(backups - 1, 0, -1):
        src = path.with_name(f"{path.name}.{i}")
        if src.exists():
            try:
                src.rename(path.with_name(f"{path.name}.{i + 1}"))
            except OSError:
                pass
    try:
        if path.exists():
            path.rename(path.with_name(f"{path.name}.1"))
    except OSError:
        pass


def _serialize(record: Any) -> str:
    return json.dumps(record, ensure_ascii=False, default=str) + "\n"


def _write(path: Path, lines: list[str], max_bytes: int, backups: int) -> None:
    if not lines:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    # Rotate per-record so a large batch never blows past the cap in one shot: the
    # active segment stays <= max_bytes after the batch, EXCEPT a single record
    # larger than max_bytes (a JSON line cannot be split — it is written in full,
    # and the next record triggers a rotation). Disk therefore stays bounded by
    # max_bytes * (backups + 1) + at-most-one-oversized-record.
    with _lock_for(path), _interprocess_lock(path):
        try:
            cur = path.stat().st_size if path.exists() else 0
        except OSError:
            cur = 0
        fh = path.open("a", encoding="utf-8")
        try:
            for line in lines:
                n = len(line.encode("utf-8"))
                if max_bytes > 0 and cur > 0 and cur + n > max_bytes:
                    fh.close()
                    _rotate(path, backups)
                    fh = path.open("a", encoding="utf-8")
                    cur = 0
                fh.write(line)
                cur += n
        finally:
            fh.close()


def append(
    path: Path | str,
    record: Any,
    *,
    max_bytes: int | None = None,
    backups: int | None = None,
) -> None:
    """Append one JSON record, rotating the file first if it would exceed the cap."""
    _write(
        Path(path),
        [_serialize(record)],
        _DEFAULT_MAX_BYTES if max_bytes is None else max_bytes,
        _DEFAULT_BACKUPS if backups is None else backups,
    )


def append_many(
    path: Path | str,
    records: Iterable[Any],
    *,
    max_bytes: int | None = None,
    backups: int | None = None,
) -> None:
    """Append a batch of JSON records under a single size check + lock (drain path)."""
    _write(
        Path(path),
        [_serialize(r) for r in records],
        _DEFAULT_MAX_BYTES if max_bytes is None else max_bytes,
        _DEFAULT_BACKUPS if backups is None else backups,
    )
