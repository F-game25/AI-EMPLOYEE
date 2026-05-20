import json
import time
import logging
from typing import Optional
from .schema import TeammateIdentity
from ..db import cognitive_conn

logger = logging.getLogger(__name__)


def _ensure_table() -> None:
    with cognitive_conn() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS teammate_identity (
                tenant_id TEXT PRIMARY KEY,
                name TEXT DEFAULT 'Aeternus',
                persona_summary TEXT NOT NULL,
                operational_focus TEXT DEFAULT 'general',
                expertise_areas TEXT DEFAULT '[]',
                interaction_count INTEGER DEFAULT 0,
                formed_at REAL NOT NULL,
                updated_at REAL NOT NULL
            )
        """)


_ensure_table()


def get_or_create(tenant_id: str) -> TeammateIdentity:
    with cognitive_conn() as c:
        row = c.execute("SELECT * FROM teammate_identity WHERE tenant_id=?", (tenant_id,)).fetchone()
    if row:
        d = dict(row)
        d["expertise_areas"] = json.loads(d["expertise_areas"])
        return TeammateIdentity(**d)
    identity = TeammateIdentity(tenant_id=tenant_id)
    _save(identity)
    return identity


def _save(identity: TeammateIdentity) -> None:
    with cognitive_conn() as c:
        c.execute(
            "INSERT OR REPLACE INTO teammate_identity VALUES (?,?,?,?,?,?,?,?)",
            (identity.tenant_id, identity.name, identity.persona_summary,
             identity.operational_focus, json.dumps(identity.expertise_areas),
             identity.interaction_count, identity.formed_at, identity.updated_at)
        )


def increment_interaction(tenant_id: str) -> None:
    with cognitive_conn() as c:
        c.execute(
            "UPDATE teammate_identity SET interaction_count=interaction_count+1, updated_at=? WHERE tenant_id=?",
            (time.time(), tenant_id)
        )


def update_persona(tenant_id: str, summary: str) -> None:
    with cognitive_conn() as c:
        c.execute(
            "UPDATE teammate_identity SET persona_summary=?, updated_at=? WHERE tenant_id=?",
            (summary, time.time(), tenant_id)
        )


_instance = None


def get_identity_manager():
    global _instance
    if _instance is None:
        _instance = type("IdentityManager", (), {
            "get_or_create": staticmethod(get_or_create),
            "increment_interaction": staticmethod(increment_interaction),
            "update_persona": staticmethod(update_persona),
        })()
    return _instance
