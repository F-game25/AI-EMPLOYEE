import json
import logging
import time
from .schema import RoutingAdjustment
from ..db import cognitive_conn

logger = logging.getLogger(__name__)
_MIN_MARGIN = 0.2
_MIN_SAMPLES = 50


def _ensure_table() -> None:
    with cognitive_conn() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS routing_suggestions (
                id TEXT PRIMARY KEY,
                task_type TEXT NOT NULL,
                from_agent TEXT NOT NULL,
                to_agent TEXT NOT NULL,
                tenant_id TEXT NOT NULL,
                confidence REAL NOT NULL,
                sample_size INTEGER NOT NULL,
                quality_delta REAL NOT NULL,
                suggested_at REAL NOT NULL,
                accepted INTEGER
            )
        """)


_ensure_table()


def generate_suggestions(tenant_id: str) -> list[RoutingAdjustment]:
    with cognitive_conn() as c:
        rows = c.execute(
            """SELECT agent_id, AVG(quality_score) as avg_q, COUNT(*) as cnt
               FROM outcome_records WHERE tenant_id=?
               GROUP BY agent_id HAVING cnt >= 10""",
            (tenant_id,)
        ).fetchall()

    if len(rows) < 2:
        return []

    suggestions = []
    agents = {r["agent_id"]: {"avg_q": r["avg_q"], "cnt": r["cnt"]} for r in rows}
    agent_ids = list(agents.keys())

    for i, a in enumerate(agent_ids):
        for b in agent_ids[i+1:]:
            delta = agents[b]["avg_q"] - agents[a]["avg_q"]
            if delta > _MIN_MARGIN and agents[b]["cnt"] >= 20:
                s = RoutingAdjustment(
                    task_type="general",
                    from_agent=a,
                    to_agent=b,
                    tenant_id=tenant_id,
                    confidence=min(0.95, delta * 2),
                    sample_size=agents[b]["cnt"],
                    quality_delta=round(delta, 3),
                )
                suggestions.append(s)
                with cognitive_conn() as c:
                    c.execute(
                        "INSERT OR IGNORE INTO routing_suggestions VALUES (?,?,?,?,?,?,?,?,?,?)",
                        (s.id, s.task_type, s.from_agent, s.to_agent, tenant_id,
                         s.confidence, s.sample_size, s.quality_delta, s.suggested_at, None)
                    )
    return suggestions


def list_suggestions(tenant_id: str) -> list[dict]:
    with cognitive_conn() as c:
        rows = c.execute(
            "SELECT * FROM routing_suggestions WHERE tenant_id=? AND accepted IS NULL ORDER BY quality_delta DESC",
            (tenant_id,)
        ).fetchall()
    return [dict(r) for r in rows]


def accept(suggestion_id: str, accept: bool) -> None:
    with cognitive_conn() as c:
        c.execute(
            "UPDATE routing_suggestions SET accepted=? WHERE id=?",
            (1 if accept else 0, suggestion_id)
        )
