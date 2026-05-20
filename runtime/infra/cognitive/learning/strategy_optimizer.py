import json
import logging
from ..db import cognitive_conn

logger = logging.getLogger(__name__)


def _ensure_table() -> None:
    with cognitive_conn() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS strategy_preferences (
                seq_key TEXT NOT NULL,
                tenant_id TEXT NOT NULL,
                confidence REAL DEFAULT 0.5,
                sample_count INTEGER DEFAULT 1,
                PRIMARY KEY (seq_key, tenant_id)
            )
        """)


_ensure_table()


def record_ordering(initiative_ids: list[str], quality_score: float, tenant_id: str) -> None:
    if len(initiative_ids) < 2:
        return
    seq_key = "->".join(initiative_ids[:3])
    with cognitive_conn() as c:
        row = c.execute(
            "SELECT confidence, sample_count FROM strategy_preferences WHERE seq_key=? AND tenant_id=?",
            (seq_key, tenant_id)
        ).fetchone()
        if row:
            new_conf = (row["confidence"] * row["sample_count"] + quality_score) / (row["sample_count"] + 1)
            c.execute(
                "UPDATE strategy_preferences SET confidence=?, sample_count=sample_count+1 WHERE seq_key=? AND tenant_id=?",
                (new_conf, seq_key, tenant_id)
            )
        else:
            c.execute(
                "INSERT INTO strategy_preferences VALUES (?,?,?,?)",
                (seq_key, tenant_id, quality_score, 1)
            )


def get_preferences(tenant_id: str) -> list[dict]:
    with cognitive_conn() as c:
        rows = c.execute(
            "SELECT * FROM strategy_preferences WHERE tenant_id=? AND confidence>0.7 ORDER BY confidence DESC LIMIT 20",
            (tenant_id,)
        ).fetchall()
    return [dict(r) for r in rows]
