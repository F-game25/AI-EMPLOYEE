import logging
from .schema import EffectivenessScore
from .outcome_tracker import get_recent
from ..db import cognitive_conn
import time

logger = logging.getLogger(__name__)
_ALPHA = 0.1  # EMA smoothing
_DEGRADE_THRESHOLD = 0.6
_PROMOTE_THRESHOLD = 0.9
_MIN_SAMPLES = 10


def _ensure_table() -> None:
    with cognitive_conn() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS effectiveness_scores (
                agent_id TEXT NOT NULL,
                tenant_id TEXT NOT NULL,
                score REAL DEFAULT 1.0,
                sample_count INTEGER DEFAULT 0,
                trend TEXT DEFAULT 'stable',
                computed_at REAL NOT NULL,
                PRIMARY KEY (agent_id, tenant_id)
            )
        """)


_ensure_table()


def compute(agent_id: str, tenant_id: str) -> EffectivenessScore:
    outcomes = get_recent(tenant_id, agent_id, limit=50)
    if not outcomes:
        return EffectivenessScore(agent_id=agent_id, tenant_id=tenant_id, score=1.0, sample_count=0, trend="stable")

    with cognitive_conn() as c:
        row = c.execute(
            "SELECT score FROM effectiveness_scores WHERE agent_id=? AND tenant_id=?",
            (agent_id, tenant_id)
        ).fetchone()
    ema = row["score"] if row else 1.0

    for o in reversed(outcomes):
        ema = _ALPHA * o["quality_score"] + (1 - _ALPHA) * ema

    prev_ema = row["score"] if row else 1.0
    trend = "stable"
    if ema > prev_ema + 0.05:
        trend = "improving"
    elif ema < prev_ema - 0.05:
        trend = "degrading"

    now = time.time()
    with cognitive_conn() as c:
        c.execute(
            "INSERT OR REPLACE INTO effectiveness_scores VALUES (?,?,?,?,?,?)",
            (agent_id, tenant_id, ema, len(outcomes), trend, now)
        )

    if len(outcomes) >= _MIN_SAMPLES:
        if ema < _DEGRADE_THRESHOLD:
            _emit("learning:agent_degraded", agent_id, tenant_id, ema)
        elif ema > _PROMOTE_THRESHOLD:
            _emit("learning:agent_promoted", agent_id, tenant_id, ema)

    return EffectivenessScore(agent_id=agent_id, tenant_id=tenant_id, score=round(ema, 3),
                              sample_count=len(outcomes), trend=trend)


def _emit(event: str, agent_id: str, tenant_id: str, score: float) -> None:
    try:
        from core.bus import get_message_bus
        get_message_bus().publish_sync("notifications", {
            "event": event, "agent_id": agent_id, "tenant_id": tenant_id, "score": score
        })
    except Exception:
        pass


def get_all_scores(tenant_id: str) -> list[dict]:
    with cognitive_conn() as c:
        rows = c.execute(
            "SELECT * FROM effectiveness_scores WHERE tenant_id=? ORDER BY score ASC",
            (tenant_id,)
        ).fetchall()
    return [dict(r) for r in rows]


_instance = None


def get_reinforcement_engine():
    global _instance
    if _instance is None:
        _instance = type("ReinforcementEngine", (), {
            "compute": staticmethod(compute),
            "get_all_scores": staticmethod(get_all_scores),
        })()
    return _instance
