"""Shared utility helpers for AI Employee agents.

All functions in this module are pure and safe to import from any agent.
They carry no side effects and have no third-party dependencies.

Usage::

    import sys
    from pathlib import Path
    _utils = Path(__file__).parent.parent  # runtime/agents/
    if str(_utils) not in sys.path:
        sys.path.insert(0, str(_utils))
    from utils import now_iso, load_json_safe, save_json_safe, append_jsonl_safe
"""
from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("utils")

# ── Per-file write locks — prevents concurrent writes to the same path ─────────
_FILE_LOCKS: dict[str, threading.Lock] = {}
_FILE_LOCKS_META = threading.Lock()


def _get_file_lock(path: "str | Path") -> threading.Lock:
    key = str(path)
    with _FILE_LOCKS_META:
        if key not in _FILE_LOCKS:
            _FILE_LOCKS[key] = threading.Lock()
        return _FILE_LOCKS[key]


# ── Timestamp helpers ─────────────────────────────────────────────────────────

def now_iso() -> str:
    """Return current UTC time as an ISO-8601 string (no microseconds)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# Keep the private-prefixed alias that most agents currently use
_now_iso = now_iso


# ── JSON file helpers ─────────────────────────────────────────────────────────

def load_json_safe(path: "str | Path", default: Any = None) -> Any:
    """Load a JSON file and return its content, or *default* on any error.

    Args:
        path:    Path to the JSON file.
        default: Value to return if the file is missing or unparseable.
                 Defaults to None; pass ``{}`` or ``[]`` as appropriate.
    """
    p = Path(path)
    if not p.exists():
        return default
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.debug("load_json_safe: failed to read %s — %s", p, exc)
        return default


def save_json_safe(path: "str | Path", data: Any, *, indent: int = 2) -> bool:
    """Atomically write *data* as JSON to *path*.

    Creates parent directories if they do not exist.
    Uses a per-path threading lock to prevent concurrent write corruption.

    Returns:
        True on success, False on failure.
    """
    p = Path(path)
    lock = _get_file_lock(p)
    with lock:
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(data, indent=indent), encoding="utf-8")
            return True
        except Exception as exc:
            logger.warning("save_json_safe: failed to write %s — %s", p, exc)
            return False


def append_jsonl_safe(path: "str | Path", entry: dict, *, max_lines: int = 0) -> bool:
    """Append *entry* as a newline-delimited JSON record to *path*.

    Creates parent directories if they do not exist.
    Uses a per-path threading lock to prevent interleaved writes.

    Args:
        path:      Target JSONL file path.
        entry:     Dict to serialise as a single JSON line.
        max_lines: If > 0, trim the file to the last *max_lines* entries after
                   appending (O(n) — use only for small logs).

    Returns:
        True on success, False on failure.
    """
    p = Path(path)
    lock = _get_file_lock(p)
    with lock:
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            with open(p, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry) + "\n")
            if max_lines > 0 and p.stat().st_size > 0:
                try:
                    lines = p.read_text(encoding="utf-8").splitlines()
                    if len(lines) > max_lines:
                        p.write_text("\n".join(lines[-max_lines:]) + "\n", encoding="utf-8")
                except Exception:
                    pass
            return True
        except Exception as exc:
            logger.warning("append_jsonl_safe: failed to write %s — %s", p, exc)
            return False


def read_last_jsonl(path: "str | Path", n: int = 100) -> list[dict]:
    """Return the last *n* non-empty lines from a JSONL file as parsed dicts.

    Silently skips lines that fail to parse.
    """
    p = Path(path)
    if not p.exists():
        return []
    try:
        lines = [l for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
    except Exception:
        return []
    result = []
    for line in lines[-n:]:
        try:
            result.append(json.loads(line))
        except Exception:
            continue
    return result
