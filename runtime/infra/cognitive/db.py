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

_DEFAULT_DB_PATH = Path(os.path.expanduser("~/.ai-employee/cognitive.db"))

_COMMON_SCHEMA = """
CREATE TABLE IF NOT EXISTS objectives (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT DEFAULT '',
    priority INTEGER DEFAULT 5,
    parent_id TEXT,
    status TEXT DEFAULT 'active',
    source_agent TEXT,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_obj_tenant ON objectives(tenant_id, status);

CREATE TABLE IF NOT EXISTS contradictions (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    agent_a TEXT NOT NULL,
    agent_b TEXT NOT NULL,
    claim_a TEXT NOT NULL,
    claim_b TEXT NOT NULL,
    detected_at REAL NOT NULL,
    resolved INTEGER DEFAULT 0,
    resolution TEXT
);
CREATE INDEX IF NOT EXISTS idx_cont_tenant ON contradictions(tenant_id, resolved);
CREATE INDEX IF NOT EXISTS idx_cont_time ON contradictions(detected_at DESC);

CREATE TABLE IF NOT EXISTS wf_fingerprints (
    hash TEXT PRIMARY KEY,
    workflow_id TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    started_at REAL NOT NULL,
    expires_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_fp_tenant ON wf_fingerprints(tenant_id);

CREATE TABLE IF NOT EXISTS initiatives (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT DEFAULT '',
    status TEXT DEFAULT 'pending',
    priority INTEGER DEFAULT 5,
    estimated_cost_tokens INTEGER DEFAULT 0,
    actual_cost_tokens INTEGER DEFAULT 0,
    deadline REAL,
    dependencies TEXT DEFAULT '[]',
    assigned_agents TEXT DEFAULT '[]',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_init_tenant ON initiatives(tenant_id, status);

CREATE TABLE IF NOT EXISTS executive_decisions (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    decision_type TEXT NOT NULL,
    rationale TEXT NOT NULL,
    affected_initiatives TEXT DEFAULT '[]',
    affected_agents TEXT DEFAULT '[]',
    confidence REAL DEFAULT 0.8,
    decided_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ed_tenant ON executive_decisions(tenant_id);

CREATE TABLE IF NOT EXISTS budget_usage (
    tenant_id TEXT NOT NULL,
    day TEXT NOT NULL,
    tokens_used INTEGER DEFAULT 0,
    PRIMARY KEY (tenant_id, day)
);

CREATE TABLE IF NOT EXISTS trust_tiers (
    tenant_id TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    tier TEXT NOT NULL,
    PRIMARY KEY (tenant_id, agent_id)
);

CREATE TABLE IF NOT EXISTS guardrail_violations (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    violation_type TEXT NOT NULL,
    detail TEXT NOT NULL,
    occurred_at REAL NOT NULL
);
"""


def _resolve_db_path() -> Path:
    configured_path = os.getenv("COGNITIVE_DB_PATH")
    if configured_path:
        return Path(configured_path).expanduser()

    ai_home = os.getenv("AI_HOME")
    if ai_home:
        return Path(ai_home).expanduser() / "cognitive.db"

    return _DEFAULT_DB_PATH


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
    db_path = _resolve_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    c = sqlite3.connect(str(db_path), timeout=10, check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA busy_timeout=5000")
    c.execute("PRAGMA foreign_keys=ON")
    c.executescript(_COMMON_SCHEMA)

    return c


def get_db_path() -> Path:
    """Get cognitive database file path."""
    return _resolve_db_path()
