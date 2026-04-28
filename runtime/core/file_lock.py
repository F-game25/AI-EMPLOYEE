"""File-level locking for concurrent state file access.

Prevents concurrent writes to shared JSON state files (deals.json, tasks.json, etc.)
using fcntl locks (Unix) with fallback for non-blocking writes.
"""
from __future__ import annotations

import fcntl
import json
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class FileLock:
    """Context manager for exclusive file locking."""

    def __init__(self, file_path: Path, timeout: float = 5.0):
        self.file_path = Path(file_path)
        self.timeout = timeout
        self._lock_file: Any = None

    def __enter__(self):
        lock_path = self.file_path.with_suffix(self.file_path.suffix + '.lock')
        try:
            self._lock_file = open(lock_path, 'w')
            fcntl.flock(self._lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return self
        except (IOError, OSError) as e:
            if self._lock_file:
                self._lock_file.close()
            logger.warning(f"Could not acquire lock for {self.file_path}: {e}")
            raise

    def __exit__(self, *args):
        if self._lock_file:
            try:
                fcntl.flock(self._lock_file.fileno(), fcntl.LOCK_UN)
                self._lock_file.close()
            except Exception as e:
                logger.warning(f"Error releasing lock: {e}")


def read_json_safe(file_path: Path, default: Any = None) -> Any:
    """Read JSON file with lock protection."""
    try:
        with FileLock(file_path):
            if file_path.exists():
                return json.loads(file_path.read_text(encoding='utf-8'))
    except Exception as e:
        logger.warning(f"Failed to read {file_path}: {e}")
    return default or {}


def write_json_safe(file_path: Path, data: Any) -> bool:
    """Write JSON file with lock protection. Returns True on success."""
    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with FileLock(file_path):
            file_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')
            file_path.chmod(0o644)
        return True
    except Exception as e:
        logger.error(f"Failed to write {file_path}: {e}")
        return False
