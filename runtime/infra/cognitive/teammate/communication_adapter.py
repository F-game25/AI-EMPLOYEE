import json
import logging
from ..db import cognitive_conn

logger = logging.getLogger(__name__)


def _ensure_table() -> None:
    with cognitive_conn() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS comm_profiles (
                user_id TEXT NOT NULL,
                tenant_id TEXT NOT NULL,
                prefers_brief INTEGER DEFAULT 0,
                technical_depth INTEGER DEFAULT 1,
                formality INTEGER DEFAULT 1,
                emoji_ok INTEGER DEFAULT 0,
                sample_count INTEGER DEFAULT 0,
                PRIMARY KEY (user_id, tenant_id)
            )
        """)


_ensure_table()


def update_from_response(user_id: str, tenant_id: str, response_length: int, has_technical: bool) -> None:
    with cognitive_conn() as c:
        row = c.execute(
            "SELECT * FROM comm_profiles WHERE user_id=? AND tenant_id=?",
            (user_id, tenant_id)
        ).fetchone()
        if row:
            n = row["sample_count"] + 1
            brief = 1 if (row["prefers_brief"] * row["sample_count"] + (1 if response_length < 100 else 0)) / n > 0.6 else 0
            depth = min(3, row["technical_depth"] + (1 if has_technical else 0))
            c.execute(
                "UPDATE comm_profiles SET prefers_brief=?, technical_depth=?, sample_count=? WHERE user_id=? AND tenant_id=?",
                (brief, depth, n, user_id, tenant_id)
            )
        else:
            c.execute(
                "INSERT INTO comm_profiles VALUES (?,?,?,?,?,?,?)",
                (user_id, tenant_id, 1 if response_length < 100 else 0, 1 if has_technical else 0, 1, 0, 1)
            )


def get_profile(user_id: str, tenant_id: str) -> dict:
    with cognitive_conn() as c:
        row = c.execute(
            "SELECT * FROM comm_profiles WHERE user_id=? AND tenant_id=?",
            (user_id, tenant_id)
        ).fetchone()
    return dict(row) if row else {"user_id": user_id, "tenant_id": tenant_id, "prefers_brief": False, "technical_depth": 1}
