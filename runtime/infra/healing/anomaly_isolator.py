"""AnomalyIsolator — quarantine degraded agents + track restored agents."""
from __future__ import annotations
import logging
import sqlite3
import time
from pathlib import Path
import os
from typing import Optional

from .schema import HealingEvent, HealingEventType
from .circuit_breaker import get_circuit_registry

logger = logging.getLogger(__name__)
_DB = Path(os.path.expanduser("~/.ai-employee/healing.db"))


def _conn() -> sqlite3.Connection:
    _DB.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(_DB), timeout=10)
    c.execute("""
        CREATE TABLE IF NOT EXISTS quarantined_agents (
            agent_id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            quarantined_at REAL NOT NULL,
            reason TEXT NOT NULL,
            restored_at REAL
        )
    """)
    c.commit()
    return c


class AnomalyIsolator:
    def quarantine(self, agent_id: str, tenant_id: str, reason: str) -> HealingEvent:
        now = time.time()
        with _conn() as c:
            c.execute("""
                INSERT INTO quarantined_agents (agent_id,tenant_id,quarantined_at,reason)
                VALUES (?,?,?,?)
                ON CONFLICT(agent_id) DO UPDATE SET
                  quarantined_at=excluded.quarantined_at, reason=excluded.reason,
                  restored_at=NULL
            """, (agent_id, tenant_id, now, reason))
        # Open circuit for this agent
        get_circuit_registry().record_failure(agent_id)
        evt = HealingEvent(
            event_type=HealingEventType.AGENT_QUARANTINED,
            service=agent_id, message=reason, ts=now
        )
        self._log_event(evt)
        logger.warning("Agent %s quarantined: %s", agent_id, reason)
        return evt

    def restore(self, agent_id: str, tenant_id: str) -> bool:
        now = time.time()
        with _conn() as c:
            cursor = c.execute(
                "UPDATE quarantined_agents SET restored_at=? WHERE agent_id=? AND tenant_id=? AND restored_at IS NULL",
                (now, agent_id, tenant_id)
            )
            if cursor.rowcount == 0:
                return False
        get_circuit_registry().force_closed(agent_id)
        evt = HealingEvent(
            event_type=HealingEventType.AGENT_RESTORED,
            service=agent_id, message="Manually restored", ts=now
        )
        self._log_event(evt)
        logger.info("Agent %s restored", agent_id)
        return True

    def is_quarantined(self, agent_id: str) -> bool:
        with _conn() as c:
            row = c.execute(
                "SELECT 1 FROM quarantined_agents WHERE agent_id=? AND restored_at IS NULL",
                (agent_id,)
            ).fetchone()
        return row is not None

    def list_quarantined(self, tenant_id: Optional[str] = None) -> list[dict]:
        with _conn() as c:
            if tenant_id:
                rows = c.execute(
                    "SELECT agent_id,tenant_id,quarantined_at,reason FROM quarantined_agents "
                    "WHERE tenant_id=? AND restored_at IS NULL", (tenant_id,)
                ).fetchall()
            else:
                rows = c.execute(
                    "SELECT agent_id,tenant_id,quarantined_at,reason FROM quarantined_agents "
                    "WHERE restored_at IS NULL"
                ).fetchall()
        return [{"agent_id": r[0], "tenant_id": r[1], "quarantined_at": r[2], "reason": r[3]}
                for r in rows]

    @staticmethod
    def _log_event(evt: HealingEvent) -> None:
        import json
        with _conn() as c:
            c.execute(
                "INSERT INTO healing_events (event_type,service,message,details,ts) VALUES (?,?,?,?,?)",
                (evt.event_type.value, evt.service, evt.message,
                 json.dumps(evt.details), evt.ts)
            )


_isolator = None


def get_anomaly_isolator() -> AnomalyIsolator:
    global _isolator
    if _isolator is None:
        _isolator = AnomalyIsolator()
    return _isolator
