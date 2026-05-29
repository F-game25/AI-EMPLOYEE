"""Append-only, hash-chained audit log stored in SQLite."""

import hashlib
import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

_DB_PATH = Path.home() / ".ai-employee" / "state" / "audit_chain.db"
_GENESIS = "GENESIS"

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS audit_chain (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          TEXT    NOT NULL,
    tenant_id   TEXT    NOT NULL,
    actor       TEXT    NOT NULL,
    action      TEXT    NOT NULL,
    resource    TEXT    NOT NULL,
    outcome     TEXT    NOT NULL,
    meta        TEXT    NOT NULL,
    prev_hash   TEXT    NOT NULL,
    entry_hash  TEXT    NOT NULL
)
"""

_CREATE_IDX_TENANT = "CREATE INDEX IF NOT EXISTS idx_tenant ON audit_chain(tenant_id)"


def _compute_hash(prev_hash: str, ts: str, tenant_id: str, actor: str,
                  action: str, resource: str, outcome: str, meta: str) -> str:
    payload = f"{prev_hash}|{ts}|{tenant_id}|{actor}|{action}|{resource}|{outcome}|{meta}"
    return hashlib.sha256(payload.encode()).hexdigest()


class AuditDB:
    def __init__(self, db_path: Path = _DB_PATH):
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(_CREATE_TABLE)
            conn.execute(_CREATE_IDX_TENANT)

    def append(
        self,
        tenant_id: str,
        actor: str,
        action: str,
        resource: str,
        outcome: str,
        meta: Optional[dict] = None,
    ) -> str:
        """Insert a new chained entry and return its entry_hash."""
        ts = datetime.now(timezone.utc).isoformat()
        meta_str = json.dumps(meta or {}, separators=(",", ":"))

        with self._lock:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT entry_hash FROM audit_chain ORDER BY id DESC LIMIT 1"
                ).fetchone()
                prev_hash = row["entry_hash"] if row else _GENESIS

                entry_hash = _compute_hash(
                    prev_hash, ts, tenant_id, actor, action, resource, outcome, meta_str
                )
                conn.execute(
                    """
                    INSERT INTO audit_chain
                        (ts, tenant_id, actor, action, resource, outcome, meta, prev_hash, entry_hash)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (ts, tenant_id, actor, action, resource, outcome, meta_str, prev_hash, entry_hash),
                )
        return entry_hash

    def verify_chain(self, tenant_id: Optional[str] = None) -> tuple[bool, str]:
        """Walk rows in insertion order, recompute hashes, detect tampering.

        If tenant_id is given, only rows for that tenant are checked; the
        prev_hash chain still uses global row ordering so cross-tenant
        tampering (row removal/reordering) is still detected.
        """
        with self._connect() as conn:
            all_rows = conn.execute(
                "SELECT * FROM audit_chain ORDER BY id ASC"
            ).fetchall()

        expected_prev = _GENESIS
        for row in all_rows:
            computed = _compute_hash(
                row["prev_hash"],
                row["ts"],
                row["tenant_id"],
                row["actor"],
                row["action"],
                row["resource"],
                row["outcome"],
                row["meta"],
            )
            if row["prev_hash"] != expected_prev:
                return False, f"tampered at id={row['id']} (prev_hash mismatch)"
            if row["entry_hash"] != computed:
                return False, f"tampered at id={row['id']} (entry_hash mismatch)"
            expected_prev = row["entry_hash"]

        if tenant_id is not None:
            # Secondary per-tenant check: every row for this tenant must be intact
            tenant_rows = [r for r in all_rows if r["tenant_id"] == tenant_id]
            for row in tenant_rows:
                computed = _compute_hash(
                    row["prev_hash"],
                    row["ts"],
                    row["tenant_id"],
                    row["actor"],
                    row["action"],
                    row["resource"],
                    row["outcome"],
                    row["meta"],
                )
                if row["entry_hash"] != computed:
                    return False, f"tampered at id={row['id']}"

        return True, "ok"


_singleton: Optional[AuditDB] = None
_singleton_lock = threading.Lock()


def get_audit_db() -> AuditDB:
    """Return the module-level singleton AuditDB."""
    global _singleton
    if _singleton is None:
        with _singleton_lock:
            if _singleton is None:
                _singleton = AuditDB()
    return _singleton
