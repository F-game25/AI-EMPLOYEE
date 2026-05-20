import time
import logging
from ..db import cognitive_conn

logger = logging.getLogger(__name__)
_DAILY_DEFAULT = 1_000_000  # tokens


def _ensure_table() -> None:
    with cognitive_conn() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS budget_usage (
                tenant_id TEXT NOT NULL,
                day TEXT NOT NULL,
                tokens_used INTEGER DEFAULT 0,
                PRIMARY KEY (tenant_id, day)
            )
        """)


_ensure_table()


def _today() -> str:
    import datetime
    return datetime.date.today().isoformat()


def record_usage(tenant_id: str, tokens: int) -> None:
    day = _today()
    with cognitive_conn() as c:
        c.execute(
            "INSERT INTO budget_usage(tenant_id, day, tokens_used) VALUES(?,?,?) "
            "ON CONFLICT(tenant_id, day) DO UPDATE SET tokens_used=tokens_used+?",
            (tenant_id, day, tokens, tokens)
        )
    used = get_used_today(tenant_id)
    limit = _DAILY_DEFAULT
    if used >= limit:
        _emit("executive:budget_exhausted", tenant_id, used, limit)
    elif used >= limit * 0.8:
        _emit("executive:budget_warning", tenant_id, used, limit)


def get_used_today(tenant_id: str) -> int:
    day = _today()
    with cognitive_conn() as c:
        row = c.execute(
            "SELECT tokens_used FROM budget_usage WHERE tenant_id=? AND day=?",
            (tenant_id, day)
        ).fetchone()
    return row["tokens_used"] if row else 0


def get_status(tenant_id: str) -> dict:
    used = get_used_today(tenant_id)
    limit = _DAILY_DEFAULT
    return {"tenant_id": tenant_id, "used": used, "limit": limit, "pct": round(used / limit * 100, 1)}


def _emit(event: str, tenant_id: str, used: int, limit: int) -> None:
    try:
        from core.bus import get_message_bus
        get_message_bus().publish_sync("notifications", {
            "event": event, "tenant_id": tenant_id, "used": used, "limit": limit
        })
    except Exception:
        pass


_instance = None


def get_budget_tracker():
    global _instance
    if _instance is None:
        _instance = type("BudgetTracker", (), {
            "record_usage": staticmethod(record_usage),
            "get_status": staticmethod(get_status),
        })()
    return _instance
