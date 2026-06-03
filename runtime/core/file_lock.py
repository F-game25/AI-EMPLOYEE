"""File-level locking for concurrent state file access.

Cross-platform: uses fcntl on Unix/macOS, msvcrt on Windows.
"""
from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ── Platform-specific lock primitives ────────────────────────────────────────
if sys.platform == 'win32':
    import msvcrt

    def _lock(fh):
        msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)

    def _unlock(fh):
        try:
            fh.seek(0)
            msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
        except Exception:
            pass
else:
    import fcntl

    def _lock(fh):
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

    def _unlock(fh):
        fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


class FileLock:
    """Context manager for exclusive file locking (cross-platform)."""

    def __init__(self, file_path: Path, timeout: float = 5.0):
        self.file_path = Path(file_path)
        self.timeout = timeout
        self._lock_file: Any = None

    def __enter__(self):
        lock_path = self.file_path.with_suffix(self.file_path.suffix + '.lock')
        try:
            self._lock_file = open(lock_path, 'w')
            _lock(self._lock_file)
            return self
        except (IOError, OSError) as e:
            if self._lock_file:
                self._lock_file.close()
            logger.warning("Could not acquire lock for %s: %s", self.file_path, e)
            raise

    def __exit__(self, *args):
        if self._lock_file:
            try:
                _unlock(self._lock_file)
                self._lock_file.close()
            except Exception as e:
                logger.warning("Error releasing lock: %s", e)


def read_json_safe(file_path: Path, default: Any = None, tenant_id: str = None) -> Any:
    """Read JSON file with lock protection. Optionally filters by tenant_id."""
    try:
        with FileLock(file_path):
            if file_path.exists():
                data = json.loads(file_path.read_text(encoding='utf-8'))
                if tenant_id and isinstance(data, dict) and "_tenant_data" in data:
                    return data.get("_tenant_data", {}).get(tenant_id, default or {})
                return data
    except Exception as e:
        logger.warning("Failed to read %s: %s", file_path, e)
    return default or {}


def write_json_safe(file_path: Path, data: Any, tenant_id: str = None) -> bool:
    """Write JSON file with lock protection. Optionally segregates data by tenant_id."""
    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with FileLock(file_path):
            if tenant_id:
                existing = {}
                if file_path.exists():
                    try:
                        existing = json.loads(file_path.read_text(encoding='utf-8'))
                    except Exception:
                        existing = {}
                if "_tenant_data" not in existing:
                    existing["_tenant_data"] = {}
                existing["_tenant_data"][tenant_id] = data
                file_path.write_text(json.dumps(existing, indent=2, ensure_ascii=False), encoding='utf-8')
            else:
                file_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')
            # chmod is a no-op on Windows — skip it
            if sys.platform != 'win32':
                try:
                    file_path.chmod(0o644)
                except Exception:
                    pass
        return True
    except Exception as e:
        logger.error("Failed to write %s: %s", file_path, e)
        return False
