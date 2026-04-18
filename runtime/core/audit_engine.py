"""Central audit engine — records every system event with structured metadata and risk scoring.

All agents, forge operations, memory mutations, and economy actions should call
``get_audit_engine().record(...)`` so that every action is traceable and auditable.

Risk scores
-----------
0.0 – 0.25  LOW    informational / read-only events
0.25 – 0.60 MEDIUM state mutations, config changes
0.60 – 1.0  HIGH   forge deploys, memory deletes, permission overrides
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
import uuid
from collections import deque
from pathlib import Path
from typing import Any


# ── risk classification ──────────────────────────────────────────────────────

_HIGH_RISK_ACTIONS = frozenset(
    {
        "forge_deploy",
        "forge_rollback",
        "memory_delete",
        "memory_rollback",
        "permission_override",
        "economy_withdraw",
        "agent_stop_all",
        "security_strict_mode",
    }
)
_MEDIUM_RISK_ACTIONS = frozenset(
    {
        "forge_submit",
        "forge_approve",
        "memory_write",
        "config_change",
        "agent_mode_change",
        "economy_action",
        "tool_execution",
    }
)


def _classify_risk(action: str) -> float:
    if action in _HIGH_RISK_ACTIONS:
        return 0.85
    if action in _MEDIUM_RISK_ACTIONS:
        return 0.45
    return 0.10


# ── anomaly thresholds ───────────────────────────────────────────────────────

_ANOMALY_HIGH_RISK_WINDOW = 60        # seconds
_ANOMALY_HIGH_RISK_COUNT = 5          # events at risk >= 0.6 within window → flag


class AuditEngine:
    """Stores structured audit records and detects behavioural anomalies."""

    def __init__(self, db_path: Path | None = None, max_cache: int = 5000) -> None:
        self._db_path = db_path or self._default_path()
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._cache: deque[dict[str, Any]] = deque(maxlen=max_cache)
        self._anomalies: deque[dict[str, Any]] = deque(maxlen=200)
        self._init_db()

    # ── public API ────────────────────────────────────────────────────────────

    def record(
        self,
        *,
        actor: str,
        action: str,
        input_data: dict[str, Any] | None = None,
        output_data: dict[str, Any] | None = None,
        risk_score: float | None = None,
        trace_id: str = "",
        meta: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Persist one audit record and return it.

        Parameters
        ----------
        actor:       who triggered the action (agent id, "system", "user")
        action:      action identifier (snake_case verb)
        input_data:  sanitised copy of the action's input payload
        output_data: sanitised copy of the action's output
        risk_score:  override auto-classified risk (0.0–1.0)
        trace_id:    optional distributed trace id for correlation
        meta:        free-form supplemental data
        """
        score = float(risk_score) if risk_score is not None else _classify_risk(action)
        score = max(0.0, min(1.0, score))
        event: dict[str, Any] = {
            "id": f"audit-{uuid.uuid4().hex[:12]}",
            "ts": self._ts(),
            "actor": str(actor),
            "action": str(action),
            "input": input_data or {},
            "output": output_data or {},
            "risk_score": score,
            "trace_id": trace_id,
            "meta": meta or {},
        }
        with self._lock:
            self._cache.appendleft(event)
        self._persist(event)
        if score >= 0.6:
            self._check_anomaly(event)
        return event

    def recent(self, limit: int = 100, *, actor: str = "", action: str = "", min_risk: float = 0.0) -> list[dict[str, Any]]:
        """Return recent audit records, optionally filtered."""
        with self._lock:
            cached = list(self._cache)
        results: list[dict[str, Any]] = []
        for evt in cached:
            if actor and evt["actor"] != actor:
                continue
            if action and evt["action"] != action:
                continue
            if evt["risk_score"] < min_risk:
                continue
            results.append(evt)
            if len(results) >= limit:
                break
        if results:
            return results
        return self._query_db(limit=limit, actor=actor, action=action, min_risk=min_risk)

    def anomalies(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._anomalies)[:limit]

    def stats(self) -> dict[str, Any]:
        recent = self.recent(1000)
        by_actor: dict[str, int] = {}
        by_action: dict[str, int] = {}
        risk_buckets = {"low": 0, "medium": 0, "high": 0}
        for evt in recent:
            by_actor[evt["actor"]] = by_actor.get(evt["actor"], 0) + 1
            by_action[evt["action"]] = by_action.get(evt["action"], 0) + 1
            score = evt["risk_score"]
            if score < 0.25:
                risk_buckets["low"] += 1
            elif score < 0.6:
                risk_buckets["medium"] += 1
            else:
                risk_buckets["high"] += 1
        return {
            "total": len(recent),
            "by_actor": by_actor,
            "by_action": by_action,
            "risk_distribution": risk_buckets,
            "anomalies": len(self._anomalies),
        }

    # ── internal helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _ts() -> str:
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    @staticmethod
    def _default_path() -> Path:
        ai_home = os.environ.get("AI_HOME")
        base = Path(ai_home) if ai_home else Path(__file__).resolve().parents[3]
        return base / "state" / "audit_log.db"

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS audit_log (
                    id TEXT PRIMARY KEY,
                    ts TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    action TEXT NOT NULL,
                    input TEXT NOT NULL,
                    output TEXT NOT NULL,
                    risk_score REAL NOT NULL,
                    trace_id TEXT NOT NULL DEFAULT '',
                    meta TEXT NOT NULL DEFAULT '{}'
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_actor ON audit_log (actor)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_log (action)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit_log (ts)")

    def _persist(self, event: dict[str, Any]) -> None:
        try:
            with self._conn() as conn:
                conn.execute(
                    "INSERT OR IGNORE INTO audit_log (id, ts, actor, action, input, output, risk_score, trace_id, meta) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        event["id"],
                        event["ts"],
                        event["actor"],
                        event["action"],
                        json.dumps(event["input"], ensure_ascii=False),
                        json.dumps(event["output"], ensure_ascii=False),
                        event["risk_score"],
                        event["trace_id"],
                        json.dumps(event["meta"], ensure_ascii=False),
                    ),
                )
        except Exception:
            pass  # persistence is best-effort; never crash the caller

    def _query_db(
        self,
        *,
        limit: int,
        actor: str,
        action: str,
        min_risk: float,
    ) -> list[dict[str, Any]]:
        try:
            clauses: list[str] = ["1=1"]
            params: list[Any] = []
            if actor:
                clauses.append("actor = ?")
                params.append(actor)
            if action:
                clauses.append("action = ?")
                params.append(action)
            if min_risk > 0.0:
                clauses.append("risk_score >= ?")
                params.append(min_risk)
            params.append(limit)
            where = " AND ".join(clauses)
            with self._conn() as conn:
                rows = conn.execute(
                    f"SELECT id, ts, actor, action, input, output, risk_score, trace_id, meta "
                    f"FROM audit_log WHERE {where} ORDER BY ts DESC LIMIT ?",
                    params,
                ).fetchall()
            out: list[dict[str, Any]] = []
            for row in rows:
                out.append(
                    {
                        "id": row["id"],
                        "ts": row["ts"],
                        "actor": row["actor"],
                        "action": row["action"],
                        "input": json.loads(row["input"] or "{}"),
                        "output": json.loads(row["output"] or "{}"),
                        "risk_score": row["risk_score"],
                        "trace_id": row["trace_id"],
                        "meta": json.loads(row["meta"] or "{}"),
                    }
                )
            return out
        except Exception:
            return []

    def _check_anomaly(self, event: dict[str, Any]) -> None:
        now = time.time()
        # parse ts back to epoch for windowing
        with self._lock:
            recent_high = [
                e for e in self._cache
                if e["risk_score"] >= 0.6
                and (now - self._parse_epoch(e["ts"])) <= _ANOMALY_HIGH_RISK_WINDOW
            ]
        if len(recent_high) >= _ANOMALY_HIGH_RISK_COUNT:
            anomaly: dict[str, Any] = {
                "id": f"anom-{uuid.uuid4().hex[:8]}",
                "ts": self._ts(),
                "type": "high_risk_burst",
                "severity": "high",
                "trigger_event": event["id"],
                "count": len(recent_high),
                "window_seconds": _ANOMALY_HIGH_RISK_WINDOW,
            }
            with self._lock:
                # deduplicate: don't add if the same burst was already flagged in the last 30s
                last = list(self._anomalies)[:1]
                if last and last[0]["type"] == "high_risk_burst":
                    last_epoch = self._parse_epoch(last[0]["ts"])
                    if now - last_epoch < 30:
                        return
                self._anomalies.appendleft(anomaly)

    @staticmethod
    def _parse_epoch(ts: str) -> float:
        try:
            import calendar
            t = time.strptime(ts, "%Y-%m-%dT%H:%M:%SZ")
            return float(calendar.timegm(t))
        except Exception:
            return 0.0


# ── singleton ─────────────────────────────────────────────────────────────────

_instance: AuditEngine | None = None
_instance_lock = threading.Lock()


def get_audit_engine() -> AuditEngine:
    global _instance
    with _instance_lock:
        if _instance is None:
            _instance = AuditEngine()
    return _instance
