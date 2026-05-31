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

CREATE TABLE IF NOT EXISTS outcome_records (
    id TEXT PRIMARY KEY,
    workflow_id TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    success INTEGER NOT NULL,
    quality_score REAL NOT NULL,
    duration_ms REAL NOT NULL,
    cost_tokens INTEGER DEFAULT 0,
    user_feedback INTEGER,
    recorded_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_or_agent ON outcome_records(agent_id, tenant_id, recorded_at);

CREATE TABLE IF NOT EXISTS effectiveness_scores (
    agent_id TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    score REAL DEFAULT 1.0,
    sample_count INTEGER DEFAULT 0,
    trend TEXT DEFAULT 'stable',
    computed_at REAL NOT NULL,
    PRIMARY KEY (agent_id, tenant_id)
);

CREATE TABLE IF NOT EXISTS routing_suggestions (
    id TEXT PRIMARY KEY,
    task_type TEXT NOT NULL,
    from_agent TEXT NOT NULL,
    to_agent TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    confidence REAL NOT NULL,
    sample_size INTEGER NOT NULL,
    quality_delta REAL NOT NULL,
    suggested_at REAL NOT NULL,
    accepted INTEGER
);

CREATE TABLE IF NOT EXISTS strategy_preferences (
    seq_key TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    confidence REAL DEFAULT 0.5,
    sample_count INTEGER DEFAULT 1,
    PRIMARY KEY (seq_key, tenant_id)
);

CREATE TABLE IF NOT EXISTS teammate_identity (
    tenant_id TEXT PRIMARY KEY,
    name TEXT DEFAULT 'Aeternus',
    persona_summary TEXT NOT NULL,
    operational_focus TEXT DEFAULT 'general',
    expertise_areas TEXT DEFAULT '[]',
    interaction_count INTEGER DEFAULT 0,
    formed_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS conversation_memory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    summary TEXT NOT NULL,
    topic TEXT,
    recorded_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_cm_user ON conversation_memory(user_id, tenant_id, recorded_at);

CREATE TABLE IF NOT EXISTS user_habits (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    workflow_type TEXT NOT NULL,
    typical_hour INTEGER NOT NULL,
    frequency INTEGER DEFAULT 1,
    confidence REAL DEFAULT 0.5,
    detected_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_uh_user ON user_habits(user_id, tenant_id);

CREATE TABLE IF NOT EXISTS comm_profiles (
    user_id TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    prefers_brief INTEGER DEFAULT 0,
    technical_depth INTEGER DEFAULT 1,
    formality INTEGER DEFAULT 1,
    emoji_ok INTEGER DEFAULT 0,
    sample_count INTEGER DEFAULT 0,
    PRIMARY KEY (user_id, tenant_id)
);

CREATE TABLE IF NOT EXISTS proactive_insights (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    user_id TEXT,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    insight_type TEXT NOT NULL,
    priority INTEGER DEFAULT 5,
    dismissed INTEGER DEFAULT 0,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_pi_tenant ON proactive_insights(tenant_id, dismissed);

CREATE TABLE IF NOT EXISTS deadlines (
    id TEXT PRIMARY KEY,
    initiative_id TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    deadline_ts REAL NOT NULL,
    priority INTEGER DEFAULT 5,
    status TEXT DEFAULT 'pending',
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_dl_tenant ON deadlines(tenant_id, status);

CREATE TABLE IF NOT EXISTS op_cycles (
    workflow_type TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    period_days INTEGER NOT NULL,
    confidence REAL NOT NULL,
    last_peak REAL NOT NULL,
    detected_at REAL NOT NULL,
    PRIMARY KEY (workflow_type, tenant_id)
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
