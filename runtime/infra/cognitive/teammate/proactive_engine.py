import asyncio
import time
import logging
import json
from typing import Optional
from .schema import ProactiveInsight
from ..db import cognitive_conn

logger = logging.getLogger(__name__)


def _ensure_table() -> None:
    with cognitive_conn() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS proactive_insights (
                id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                user_id TEXT,
                title TEXT NOT NULL,
                body TEXT NOT NULL,
                insight_type TEXT NOT NULL,
                priority INTEGER DEFAULT 5,
                dismissed INTEGER DEFAULT 0,
                created_at REAL NOT NULL
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_pi_tenant ON proactive_insights(tenant_id, dismissed)")


_ensure_table()


def _store_insight(insight: ProactiveInsight) -> str:
    with cognitive_conn() as c:
        c.execute(
            "INSERT OR REPLACE INTO proactive_insights VALUES (?,?,?,?,?,?,?,?,?)",
            (insight.id, insight.tenant_id, insight.user_id, insight.title, insight.body,
             insight.insight_type, insight.priority, 0, insight.created_at)
        )
    return insight.id


def dismiss(insight_id: str) -> None:
    with cognitive_conn() as c:
        c.execute("UPDATE proactive_insights SET dismissed=1 WHERE id=?", (insight_id,))


def list_insights(tenant_id: str) -> list[dict]:
    with cognitive_conn() as c:
        rows = c.execute(
            "SELECT * FROM proactive_insights WHERE tenant_id=? AND dismissed=0 ORDER BY priority ASC, created_at DESC LIMIT 20",
            (tenant_id,)
        ).fetchall()
    return [dict(r) for r in rows]


class ProactiveEngine:
    def __init__(self):
        self._running = False

    async def start(self) -> None:
        self._running = True
        while self._running:
            await asyncio.sleep(900)  # 15 min
            try:
                self._run_cycle()
            except Exception as e:
                logger.warning("Proactive engine error: %s", e)

    def _run_cycle(self) -> None:
        # Check for blocked initiatives and surface insights
        try:
            from infra.cognitive.executive.initiative_manager import list_initiatives
            with cognitive_conn() as c:
                tenants = c.execute("SELECT DISTINCT tenant_id FROM proactive_insights").fetchall()
            for row in tenants:
                tid = row["tenant_id"]
                blocked = list_initiatives(tid, "blocked")
                if blocked:
                    insight = ProactiveInsight(
                        tenant_id=tid,
                        user_id=None,
                        title=f"{len(blocked)} initiative(s) blocked",
                        body=f"Blocked initiatives: {', '.join(i['title'] for i in blocked[:3])}",
                        insight_type="blocked_initiative",
                        priority=2,
                    )
                    _store_insight(insight)
                    self._broadcast(tid, insight)
        except Exception as e:
            logger.debug("Proactive cycle skipped: %s", e)

    def _broadcast(self, tenant_id: str, insight: ProactiveInsight) -> None:
        try:
            from core.bus import get_message_bus
            import dataclasses
            get_message_bus().publish_sync("notifications", {
                "event": "teammate:proactive_insight",
                "tenant_id": tenant_id,
                "insight": dataclasses.asdict(insight),
            })
        except Exception:
            pass

    def stop(self) -> None:
        self._running = False


_instance: Optional[ProactiveEngine] = None


def get_proactive_engine() -> ProactiveEngine:
    global _instance
    if _instance is None:
        _instance = ProactiveEngine()
    return _instance
