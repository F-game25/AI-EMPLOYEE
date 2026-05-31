import asyncio
import logging
import time
from typing import Optional
from .schema import ExecutiveDecision
from .initiative_manager import list_initiatives
from ..db import cognitive_conn

logger = logging.getLogger(__name__)


def _ensure_table() -> None:
    with cognitive_conn() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS executive_decisions (
                id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                decision_type TEXT NOT NULL,
                rationale TEXT NOT NULL,
                affected_initiatives TEXT DEFAULT '[]',
                affected_agents TEXT DEFAULT '[]',
                confidence REAL DEFAULT 0.8,
                decided_at REAL NOT NULL
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_ed_tenant ON executive_decisions(tenant_id)")


_ensure_table()


def _store_decision(d: ExecutiveDecision) -> None:
    import json
    _ensure_table()
    with cognitive_conn() as c:
        c.execute(
            "INSERT OR REPLACE INTO executive_decisions VALUES (?,?,?,?,?,?,?,?)",
            (d.id, d.tenant_id, d.decision_type, d.rationale,
             json.dumps(d.affected_initiatives), json.dumps(d.affected_agents),
             d.confidence, d.decided_at)
        )


def list_decisions(tenant_id: str, limit: int = 20) -> list[dict]:
    import json
    _ensure_table()
    with cognitive_conn() as c:
        rows = c.execute(
            "SELECT * FROM executive_decisions WHERE tenant_id=? ORDER BY decided_at DESC LIMIT ?",
            (tenant_id, limit)
        ).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        d["affected_initiatives"] = json.loads(d["affected_initiatives"])
        d["affected_agents"] = json.loads(d["affected_agents"])
        result.append(d)
    return result


async def plan_next(tenant_id: str) -> Optional[ExecutiveDecision]:
    initiatives = list_initiatives(tenant_id, "pending")
    if not initiatives:
        return None
    top3 = sorted(initiatives, key=lambda x: x["priority"])[:3]
    try:
        from core.orchestrator import LLMClient
        client = LLMClient()
        summary = "\n".join(f"- [{i['priority']}] {i['title']}" for i in top3)
        resp = await client.complete(
            prompt=f"Rank these initiatives for execution order. Return JSON array of ids:\n{summary}",
            system="You are an executive AI. Respond with a JSON array of initiative IDs in recommended order.",
        )
        rationale = f"LLM strategic recommendation for {len(top3)} initiatives"
    except Exception as e:
        logger.debug("Strategic planner LLM skipped: %s", e)
        resp = None
        rationale = "Default priority ordering"

    decision = ExecutiveDecision(
        tenant_id=tenant_id,
        decision_type="schedule",
        rationale=rationale,
        affected_initiatives=[i["id"] for i in top3],
        confidence=0.75 if resp else 0.5,
    )
    _store_decision(decision)
    try:
        from core.bus import get_message_bus
        import dataclasses
        get_message_bus().publish_sync("notifications", {
            "event": "executive:plan_updated",
            "tenant_id": tenant_id,
            "decision": dataclasses.asdict(decision),
        })
    except Exception:
        pass
    return decision
