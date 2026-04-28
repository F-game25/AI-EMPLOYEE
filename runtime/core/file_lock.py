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


def read_json_safe(file_path: Path, default: Any = None, tenant_id: str = None) -> Any:
    """Read JSON file with lock protection. Optionally filters by tenant_id."""
    try:
        with FileLock(file_path):
            if file_path.exists():
                data = json.loads(file_path.read_text(encoding='utf-8'))
                # If tenant_id provided and data is a dict with _tenant_data, filter by tenant
                if tenant_id and isinstance(data, dict) and "_tenant_data" in data:
                    return data.get("_tenant_data", {}).get(tenant_id, default or {})
                return data
    except Exception as e:
        logger.warning(f"Failed to read {file_path}: {e}")
    return default or {}


def write_json_safe(file_path: Path, data: Any, tenant_id: str = None) -> bool:
    """Write JSON file with lock protection. Optionally segregates data by tenant_id.

    If tenant_id is provided, stores data in _tenant_data[tenant_id] structure.
    Returns True on success.
    """
    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with FileLock(file_path):
            if tenant_id:
                # Read existing data, merge with tenant-specific write
                existing = {}
                if file_path.exists():
                    try:
                        existing = json.loads(file_path.read_text(encoding='utf-8'))
                    except Exception:
                        existing = {}

                # Ensure _tenant_data structure exists
                if "_tenant_data" not in existing:
                    existing["_tenant_data"] = {}

                # Update tenant data
                existing["_tenant_data"][tenant_id] = data
                file_path.write_text(json.dumps(existing, indent=2, ensure_ascii=False), encoding='utf-8')
            else:
                # Write directly (backward compatible for non-tenant code)
                file_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')

            file_path.chmod(0o644)
        return True
    except Exception as e:
        logger.error(f"Failed to write {file_path}: {e}")
        return False
