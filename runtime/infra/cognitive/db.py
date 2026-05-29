"""Cognitive infrastructure SQLite database factory.

Provides centralized SQLite connection with:
- WAL mode (write-ahead logging) for concurrency
- Row factory for dict-like access
- Foreign key constraints enabled
- Busy timeout for contention handling
"""
import sqlite3
import os
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_DB_PATH = Path(os.path.expanduser("~/.ai-employee/cognitive.db"))


def cognitive_conn() -> sqlite3.Connection:
    """Get SQLite connection to cognitive database.

    Returns:
        sqlite3.Connection: Connected and configured database connection.

    Configuration:
        - WAL mode: enables concurrent reads
        - Row factory: dict-like row access
        - Timeout: 5s busy timeout
        - Foreign keys: enabled
    """
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    c = sqlite3.connect(str(_DB_PATH), timeout=10, check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA busy_timeout=5000")
    c.execute("PRAGMA foreign_keys=ON")

    return c


def get_db_path() -> Path:
    """Get cognitive database file path."""
    return _DB_PATH
