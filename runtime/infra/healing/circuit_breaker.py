"""SQLite-backed circuit breaker — CLOSED / OPEN / HALF_OPEN per service."""
from __future__ import annotations
import logging
import os
import sqlite3
import time
from pathlib import Path
from typing import Optional

from .schema import CircuitBreakerState, CircuitState, HealingEvent, HealingEventType

logger = logging.getLogger(__name__)
_DB = Path(os.path.expanduser("~/.ai-employee/healing.db"))


def _conn() -> sqlite3.Connection:
    _DB.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(_DB), timeout=10)
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA busy_timeout=5000")
    c.execute("""
        CREATE TABLE IF NOT EXISTS circuit_states (
            service TEXT PRIMARY KEY,
            state TEXT NOT NULL DEFAULT 'closed',
            failure_count INTEGER NOT NULL DEFAULT 0,
            success_count INTEGER NOT NULL DEFAULT 0,
            last_probe REAL NOT NULL DEFAULT 0,
            last_state_change REAL NOT NULL DEFAULT 0,
            threshold INTEGER NOT NULL DEFAULT 5,
            half_open_timeout REAL NOT NULL DEFAULT 30
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS healing_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type TEXT NOT NULL,
            service TEXT NOT NULL,
            message TEXT NOT NULL,
            details TEXT NOT NULL DEFAULT '{}',
            ts REAL NOT NULL
        )
    """)
    c.commit()
    return c


class CircuitBreakerRegistry:
    def get(self, service: str) -> CircuitBreakerState:
        with _conn() as c:
            row = c.execute(
                "SELECT state,failure_count,success_count,last_probe,last_state_change,threshold,half_open_timeout "
                "FROM circuit_states WHERE service=?", (service,)
            ).fetchone()
        if not row:
            return CircuitBreakerState(service=service)
        return CircuitBreakerState(
            service=service,
            state=CircuitState(row[0]),
            failure_count=row[1], success_count=row[2],
            last_probe=row[3], last_state_change=row[4],
            threshold=row[5], half_open_timeout=row[6],
        )

    def _save(self, s: CircuitBreakerState) -> None:
        with _conn() as c:
            c.execute("""
                INSERT INTO circuit_states
                  (service,state,failure_count,success_count,last_probe,last_state_change,threshold,half_open_timeout)
                VALUES (?,?,?,?,?,?,?,?)
                ON CONFLICT(service) DO UPDATE SET
                  state=excluded.state,
                  failure_count=excluded.failure_count,
                  success_count=excluded.success_count,
                  last_probe=excluded.last_probe,
                  last_state_change=excluded.last_state_change,
                  threshold=excluded.threshold,
                  half_open_timeout=excluded.half_open_timeout
            """, (s.service, s.state.value, s.failure_count, s.success_count,
                  s.last_probe, s.last_state_change, s.threshold, s.half_open_timeout))

    def record_failure(self, service: str) -> CircuitBreakerState:
        with sqlite3.connect(str(_DB), timeout=10) as c:
            c.execute("BEGIN EXCLUSIVE")
            row = c.execute(
                "SELECT state,failure_count,threshold,half_open_timeout FROM circuit_states WHERE service=?",
                (service,)
            ).fetchone()
            if not row:
                state, fc, threshold, hot = "closed", 0, 5, 30.0
            else:
                state, fc, threshold, hot = row
            fc += 1
            now = time.time()
            new_state = state
            if state == "closed" and fc >= threshold:
                new_state = "open"
                self._log_event(c, HealingEventType.CIRCUIT_OPENED, service, f"Failure threshold {threshold} reached")
            c.execute("""
                INSERT INTO circuit_states
                  (service,state,failure_count,success_count,last_probe,last_state_change,threshold,half_open_timeout)
                VALUES (?,?,?,0,0,?,?,?)
                ON CONFLICT(service) DO UPDATE SET
                  state=excluded.state, failure_count=excluded.failure_count,
                  last_state_change=CASE WHEN excluded.state!=circuit_states.state THEN ? ELSE circuit_states.last_state_change END,
                  threshold=excluded.threshold, half_open_timeout=excluded.half_open_timeout
            """, (service, new_state, fc, now, threshold, hot, now))
        return self.get(service)

    def record_success(self, service: str) -> CircuitBreakerState:
        s = self.get(service)
        now = time.time()
        if s.state == CircuitState.HALF_OPEN:
            s.state = CircuitState.CLOSED
            s.failure_count = 0
            s.success_count = 0
            s.last_state_change = now
            with _conn() as c:
                self._log_event(c, HealingEventType.CIRCUIT_CLOSED, service, "Probe succeeded, circuit closed")
        elif s.state == CircuitState.CLOSED:
            s.failure_count = max(0, s.failure_count - 1)
        self._save(s)
        return s

    def maybe_probe(self, service: str) -> bool:
        """If OPEN and timeout elapsed, transition to HALF_OPEN and return True (allow probe)."""
        s = self.get(service)
        if s.state != CircuitState.OPEN:
            return s.state != CircuitState.OPEN  # CLOSED/HALF_OPEN → allow
        if time.time() - s.last_state_change >= s.half_open_timeout:
            s.state = CircuitState.HALF_OPEN
            s.last_probe = time.time()
            self._save(s)
            return True
        return False

    def force_closed(self, service: str) -> None:
        s = self.get(service)
        s.state = CircuitState.CLOSED
        s.failure_count = 0
        s.last_state_change = time.time()
        self._save(s)

    def list_all(self) -> list[dict]:
        with _conn() as c:
            rows = c.execute(
                "SELECT service,state,failure_count,last_state_change FROM circuit_states"
            ).fetchall()
        return [{"service": r[0], "state": r[1], "failure_count": r[2],
                 "last_state_change": r[3]} for r in rows]

    @staticmethod
    def _log_event(c, event_type: HealingEventType, service: str, message: str) -> None:
        import json
        c.execute(
            "INSERT INTO healing_events (event_type,service,message,details,ts) VALUES (?,?,?,?,?)",
            (event_type.value, service, message, "{}", time.time())
        )


_registry: Optional[CircuitBreakerRegistry] = None


def get_circuit_registry() -> CircuitBreakerRegistry:
    global _registry
    if _registry is None:
        _registry = CircuitBreakerRegistry()
    return _registry
