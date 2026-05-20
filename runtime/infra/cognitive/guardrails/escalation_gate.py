import logging
from .trust_tier_policy import get_tier
from .schema import TrustTier, GuardrailViolation
from ..db import cognitive_conn

logger = logging.getLogger(__name__)

RISKY_ACTION_TYPES = frozenset({
    "hire", "fire", "send_offer", "financial_transfer", "delete_data",
    "publish_external", "mass_email", "system_config_change",
})


def _ensure_table() -> None:
    with cognitive_conn() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS guardrail_violations (
                id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                agent_id TEXT NOT NULL,
                violation_type TEXT NOT NULL,
                detail TEXT NOT NULL,
                occurred_at REAL NOT NULL
            )
        """)


_ensure_table()


def _record(v: GuardrailViolation) -> None:
    with cognitive_conn() as c:
        c.execute(
            "INSERT OR IGNORE INTO guardrail_violations VALUES (?,?,?,?,?,?)",
            (v.id, v.tenant_id, v.agent_id, v.violation_type, v.detail, v.occurred_at)
        )


def should_escalate(agent_id: str, action_type: str, tenant_id: str = "system") -> bool:
    tier = get_tier(agent_id, tenant_id)
    if tier == TrustTier.SUPERVISED:
        v = GuardrailViolation(
            tenant_id=tenant_id, agent_id=agent_id,
            violation_type="supervised_escalation", detail=f"action={action_type}"
        )
        _record(v)
        return True
    if tier == TrustTier.ASSISTED and action_type in RISKY_ACTION_TYPES:
        v = GuardrailViolation(
            tenant_id=tenant_id, agent_id=agent_id,
            violation_type="risky_action_escalation", detail=f"action={action_type}"
        )
        _record(v)
        return True
    return False


def list_violations(tenant_id: str, limit: int = 50) -> list[dict]:
    with cognitive_conn() as c:
        rows = c.execute(
            "SELECT * FROM guardrail_violations WHERE tenant_id=? ORDER BY occurred_at DESC LIMIT ?",
            (tenant_id, limit)
        ).fetchall()
    return [dict(r) for r in rows]
