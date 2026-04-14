from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any, Callable


class EventStream:
    """Real-time event stream with SQLite persistence and subscriptions."""

    def __init__(self, db_path: Path | None = None, max_events: int = 2000) -> None:
        self._db_path = db_path or self._default_path()
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._events: deque[dict[str, Any]] = deque(maxlen=max_events)
        self._subs: list[Callable[[dict[str, Any]], None]] = []
        self._init_db()

    @staticmethod
    def _default_path() -> Path:
        ai_home = os.environ.get("AI_HOME")
        base = Path(ai_home) if ai_home else Path(__file__).resolve().parents[3]
        return base / "state" / "observability_events.db"

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS event_stream (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    trace_id TEXT NOT NULL DEFAULT '',
                    payload TEXT NOT NULL
                )
                """
            )

    @staticmethod
    def _ts() -> str:
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    def subscribe(self, callback: Callable[[dict[str, Any]], None]) -> None:
        with self._lock:
            self._subs.append(callback)

    def publish(self, event_type: str, payload: dict[str, Any] | None = None, *, trace_id: str = "") -> dict[str, Any]:
        event = {
            "ts": self._ts(),
            "event_type": event_type,
            "trace_id": trace_id,
            "payload": payload or {},
        }
        with self._lock:
            self._events.appendleft(event)
            with self._conn() as conn:
                conn.execute(
                    "INSERT INTO event_stream (ts, event_type, trace_id, payload) VALUES (?, ?, ?, ?)",
                    (event["ts"], event_type, trace_id, json.dumps(event["payload"], ensure_ascii=False)),
                )
            subscribers = list(self._subs)
        for cb in subscribers:
            try:
                cb(event)
            except Exception:
                continue
        return event

    def recent(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._lock:
            cached = list(self._events)[:limit]
        if cached:
            return cached
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT ts, event_type, trace_id, payload FROM event_stream ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        out: list[dict[str, Any]] = []
        for row in rows:
            out.append(
                {
                    "ts": row["ts"],
                    "event_type": row["event_type"],
                    "trace_id": row["trace_id"],
                    "payload": json.loads(row["payload"] or "{}"),
                }
            )
        return out

    def stats(self) -> dict[str, Any]:
        recent = self.recent(1000)
        by_type: dict[str, int] = {}
        for item in recent:
            event_type = item.get("event_type", "unknown")
            by_type[event_type] = by_type.get(event_type, 0) + 1
        return {
            "events": len(recent),
            "by_type": by_type,
        }


_instance: EventStream | None = None
_instance_lock = threading.Lock()


def get_event_stream() -> EventStream:
    global _instance
    with _instance_lock:
        if _instance is None:
            _instance = EventStream()
    return _instance
