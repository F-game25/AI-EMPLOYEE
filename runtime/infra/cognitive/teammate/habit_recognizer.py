import json
import time
import logging
import collections
from .schema import HabitPattern
from ..db import cognitive_conn

logger = logging.getLogger(__name__)
_window: dict[str, list] = {}


def _ensure_table() -> None:
    with cognitive_conn() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS user_habits (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                tenant_id TEXT NOT NULL,
                workflow_type TEXT NOT NULL,
                typical_hour INTEGER NOT NULL,
                frequency INTEGER DEFAULT 1,
                confidence REAL DEFAULT 0.5,
                detected_at REAL NOT NULL
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_uh_user ON user_habits(user_id, tenant_id)")


_ensure_table()


def record_event(user_id: str, tenant_id: str, workflow_type: str) -> None:
    key = f"{tenant_id}:{user_id}:{workflow_type}"
    hour = time.localtime().tm_hour
    now = time.time()
    _window.setdefault(key, []).append((now, hour))
    # Keep 7 days
    cutoff = now - 7 * 86400
    _window[key] = [(t, h) for t, h in _window[key] if t >= cutoff]

    events = _window[key]
    if len(events) >= 3:
        hour_counts = collections.Counter(h for _, h in events)
        common_hour, freq = hour_counts.most_common(1)[0]
        confidence = freq / len(events)
        if confidence >= 0.6:
            _store_habit(user_id, tenant_id, workflow_type, common_hour, freq, confidence)


def _store_habit(user_id: str, tenant_id: str, wf: str, hour: int, freq: int, conf: float) -> None:
    pattern = HabitPattern(user_id=user_id, tenant_id=tenant_id, workflow_type=wf,
                           typical_hour=hour, frequency=freq, confidence=conf)
    with cognitive_conn() as c:
        c.execute(
            "INSERT OR REPLACE INTO user_habits VALUES (?,?,?,?,?,?,?,?)",
            (pattern.id, user_id, tenant_id, wf, hour, freq, conf, pattern.detected_at)
        )


def get_habits(user_id: str, tenant_id: str) -> list[dict]:
    with cognitive_conn() as c:
        rows = c.execute(
            "SELECT * FROM user_habits WHERE user_id=? AND tenant_id=? ORDER BY confidence DESC",
            (user_id, tenant_id)
        ).fetchall()
    return [dict(r) for r in rows]
