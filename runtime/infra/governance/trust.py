"""Agent trust and reputation scoring system.

Trust score (0.0–1.0) is a rolling weighted average of:
  - Task success rate (weight 0.40)
  - Output accuracy vs validator consensus (weight 0.30)
  - Latency reliability — p95 within SLA (weight 0.15)
  - Hallucination detection rate — inverse (weight 0.15)

New agents start at 0.5 (neutral). Trust decays without recent executions.
Agents below TRUST_VETO_THRESHOLD are automatically vetoed and require
HITL approval for any further execution.
"""
from __future__ import annotations

import json
import logging
import math
import sqlite3
import time
from pathlib import Path
from threading import RLock
from typing import Any

logger = logging.getLogger("governance.trust")

TRUST_VETO_THRESHOLD   = 0.25   # auto-veto below this
TRUST_ESCALATE_THRESHOLD = 0.45  # escalate to human below this
TRUST_FULL_AUTONOMY    = 0.80   # no extra validation above this

_DB_PATH = Path.home() / ".ai-employee" / "governance.db"

_INIT_SQL = """
CREATE TABLE IF NOT EXISTS agent_trust (
    agent_id        TEXT PRIMARY KEY,
    tenant_id       TEXT NOT NULL,
    trust_score     REAL NOT NULL DEFAULT 0.5,
    executions      INTEGER NOT NULL DEFAULT 0,
    successes       INTEGER NOT NULL DEFAULT 0,
    failures        INTEGER NOT NULL DEFAULT 0,
    vetoes          INTEGER NOT NULL DEFAULT 0,
    hallucinations  INTEGER NOT NULL DEFAULT 0,
    last_execution  REAL NOT NULL DEFAULT 0.0,
    updated_at      REAL NOT NULL DEFAULT 0.0
);

CREATE TABLE IF NOT EXISTS trust_events (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ts              REAL NOT NULL,
    agent_id        TEXT NOT NULL,
    tenant_id       TEXT NOT NULL,
    event_type      TEXT NOT NULL,
    delta           REAL NOT NULL DEFAULT 0.0,
    new_score       REAL NOT NULL,
    context         TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_trust_tenant ON agent_trust(tenant_id);
CREATE INDEX IF NOT EXISTS idx_trust_events_agent ON trust_events(agent_id, ts);
"""

_WEIGHTS = {
    "success_rate":   0.40,
    "accuracy":       0.30,
    "latency_sla":    0.15,
    "no_hallucinate": 0.15,
}


class TrustLedger:
    def __init__(self, db_path: Path = _DB_PATH) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db_path = db_path
        self._lock = RLock()
        with self._connect() as conn:
            conn.executescript(_INIT_SQL)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._db_path), timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    def get_score(self, agent_id: str, tenant_id: str) -> float:
        with self._connect() as conn:
            row = conn.execute("SELECT trust_score FROM agent_trust WHERE agent_id=? AND tenant_id=?",
                               (agent_id, tenant_id)).fetchone()
        return row["trust_score"] if row else 0.5

    def get_profile(self, agent_id: str, tenant_id: str) -> dict:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM agent_trust WHERE agent_id=? AND tenant_id=?",
                               (agent_id, tenant_id)).fetchone()
        if not row:
            return {"agent_id": agent_id, "tenant_id": tenant_id, "trust_score": 0.5, "executions": 0}
        return dict(row)

    def record_outcome(
        self,
        agent_id: str,
        tenant_id: str,
        *,
        success: bool,
        accuracy: float = 1.0,      # 0-1 from validator
        latency_ms: float = 0.0,
        sla_ms: float = 30000.0,
        hallucination_detected: bool = False,
    ) -> float:
        now = time.time()
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT * FROM agent_trust WHERE agent_id=? AND tenant_id=?",
                               (agent_id, tenant_id)).fetchone()

            if row:
                execs = row["executions"]
                succ  = row["successes"] + (1 if success else 0)
                fail  = row["failures"]  + (0 if success else 1)
                hall  = row["hallucinations"] + (1 if hallucination_detected else 0)
                old_score = row["trust_score"]
            else:
                execs = 0
                succ  = 1 if success else 0
                fail  = 0 if success else 1
                hall  = 1 if hallucination_detected else 0
                old_score = 0.5

            new_execs = execs + 1

            # Component scores
            success_rate   = succ / new_execs
            latency_score  = 1.0 if latency_ms <= sla_ms else max(0.0, 1.0 - (latency_ms - sla_ms) / sla_ms)
            no_hall_score  = 1.0 - (hall / new_execs)

            # Ewma blending: new info weighted more at low execution counts
            alpha = min(0.3, 1.0 / max(1, math.sqrt(execs)))
            raw_score = (
                success_rate   * _WEIGHTS["success_rate"] +
                accuracy       * _WEIGHTS["accuracy"] +
                latency_score  * _WEIGHTS["latency_sla"] +
                no_hall_score  * _WEIGHTS["no_hallucinate"]
            )
            new_score = round((1 - alpha) * old_score + alpha * raw_score, 4)

            if row:
                conn.execute(
                    """UPDATE agent_trust SET trust_score=?, executions=?, successes=?,
                       failures=?, hallucinations=?, last_execution=?, updated_at=?
                       WHERE agent_id=? AND tenant_id=?""",
                    (new_score, new_execs, succ, fail, hall, now, now, agent_id, tenant_id),
                )
            else:
                conn.execute(
                    """INSERT INTO agent_trust
                       (agent_id, tenant_id, trust_score, executions, successes, failures,
                        vetoes, hallucinations, last_execution, updated_at)
                       VALUES(?,?,?,?,?,?,0,?,?,?)""",
                    (agent_id, tenant_id, new_score, new_execs, succ, fail, hall, now, now),
                )

            delta = new_score - old_score
            conn.execute(
                "INSERT INTO trust_events(ts, agent_id, tenant_id, event_type, delta, new_score, context) VALUES(?,?,?,?,?,?,?)",
                (now, agent_id, tenant_id, "outcome", delta, new_score,
                 json.dumps({"success": success, "accuracy": accuracy,
                             "hallucination": hallucination_detected})),
            )

        level = self._trust_level(new_score)
        if new_score < TRUST_VETO_THRESHOLD:
            logger.warning("VETO threshold reached: agent=%s score=%.3f", agent_id, new_score)
        return new_score

    def record_veto(self, agent_id: str, tenant_id: str, reason: str) -> None:
        now = time.time()
        with self._lock, self._connect() as conn:
            conn.execute("UPDATE agent_trust SET vetoes=vetoes+1, updated_at=? WHERE agent_id=? AND tenant_id=?",
                         (now, agent_id, tenant_id))
            score = self.get_score(agent_id, tenant_id)
            # Veto degrades trust by 0.1
            new_score = max(0.0, score - 0.10)
            conn.execute("UPDATE agent_trust SET trust_score=? WHERE agent_id=? AND tenant_id=?",
                         (new_score, agent_id, tenant_id))
            conn.execute(
                "INSERT INTO trust_events(ts, agent_id, tenant_id, event_type, delta, new_score, context) VALUES(?,?,?,?,?,?,?)",
                (now, agent_id, tenant_id, "veto", -0.10, new_score, json.dumps({"reason": reason})),
            )

    def list_agents(self, tenant_id: str) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM agent_trust WHERE tenant_id=? ORDER BY trust_score DESC",
                                (tenant_id,)).fetchall()
        return [dict(r) for r in rows]

    def get_events(self, agent_id: str, tenant_id: str, limit: int = 20) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT ts, event_type, delta, new_score, context FROM trust_events WHERE agent_id=? AND tenant_id=? ORDER BY ts DESC LIMIT ?",
                (agent_id, tenant_id, limit),
            ).fetchall()
        return [{"ts": r["ts"], "event_type": r["event_type"], "delta": r["delta"],
                 "new_score": r["new_score"], "context": json.loads(r["context"])} for r in rows]

    @staticmethod
    def _trust_level(score: float) -> str:
        if score >= TRUST_FULL_AUTONOMY:
            return "full_autonomy"
        if score >= TRUST_ESCALATE_THRESHOLD:
            return "supervised"
        if score >= TRUST_VETO_THRESHOLD:
            return "restricted"
        return "vetoed"


_ledger: TrustLedger | None = None

def get_trust_ledger() -> TrustLedger:
    global _ledger
    if _ledger is None:
        _ledger = TrustLedger()
    return _ledger
