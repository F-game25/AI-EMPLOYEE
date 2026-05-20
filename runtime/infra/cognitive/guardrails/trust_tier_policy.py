import logging
from .schema import TrustTier
from ..db import cognitive_conn

logger = logging.getLogger(__name__)

DEFAULT_TIERS: dict[str, str] = {
    "hr-manager": TrustTier.SUPERVISED,
    "lead-hunter-elite": TrustTier.SUPERVISED,
    "recruiter": TrustTier.SUPERVISED,
    "sales-closer-pro": TrustTier.ASSISTED,
    "crm-pipeline": TrustTier.AUTONOMOUS,
    "*": TrustTier.AUTONOMOUS,
}


def _ensure_table() -> None:
    with cognitive_conn() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS trust_tiers (
                tenant_id TEXT NOT NULL,
                agent_id TEXT NOT NULL,
                tier TEXT NOT NULL,
                PRIMARY KEY (tenant_id, agent_id)
            )
        """)


_ensure_table()


def get_tier(agent_id: str, tenant_id: str = "system") -> TrustTier:
    with cognitive_conn() as c:
        row = c.execute(
            "SELECT tier FROM trust_tiers WHERE tenant_id=? AND agent_id=?",
            (tenant_id, agent_id)
        ).fetchone()
    if row:
        return TrustTier(row["tier"])
    return TrustTier(DEFAULT_TIERS.get(agent_id, DEFAULT_TIERS["*"]))


def set_tier(agent_id: str, tier: TrustTier, tenant_id: str = "system") -> None:
    with cognitive_conn() as c:
        c.execute(
            "INSERT OR REPLACE INTO trust_tiers VALUES (?,?,?)",
            (tenant_id, agent_id, tier.value)
        )


def list_tiers(tenant_id: str = "system") -> dict:
    with cognitive_conn() as c:
        rows = c.execute("SELECT agent_id, tier FROM trust_tiers WHERE tenant_id=?", (tenant_id,)).fetchall()
    result = dict(DEFAULT_TIERS)
    result.update({r["agent_id"]: r["tier"] for r in rows})
    return result


_instance = None


def get_trust_policy():
    global _instance
    if _instance is None:
        _instance = type("TrustTierPolicy", (), {
            "get_tier": staticmethod(get_tier),
            "set_tier": staticmethod(set_tier),
            "list_tiers": staticmethod(list_tiers),
        })()
    return _instance
