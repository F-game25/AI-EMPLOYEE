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
new mechanism. A per-path in-process lock makes append+rotate atomic, which also
serializes the two telemetry modules that share one file.

Thresholds are env-configurable (never hardcode call sites):
  - ``JSONL_LOG_MAX_BYTES`` — active-segment cap (default 64 MiB)
  - ``JSONL_LOG_BACKUPS``   — rolled segments to keep (default 3)
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any, Iterable

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
    payload = "".join(lines)
    incoming = len(payload.encode("utf-8"))
    with _lock_for(path):
        try:
            if max_bytes > 0 and path.exists() and path.stat().st_size + incoming > max_bytes:
                _rotate(path, backups)
        except OSError:
            pass
        with path.open("a", encoding="utf-8") as fh:
            fh.write(payload)


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
