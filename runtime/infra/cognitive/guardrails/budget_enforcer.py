import logging
from ..executive.budget_tracker import get_used_today

logger = logging.getLogger(__name__)
_DAILY_DEFAULT = 1_000_000


def check_budget(tenant_id: str) -> dict:
    used = get_used_today(tenant_id)
    pct = used / _DAILY_DEFAULT * 100
    return {"ok": pct < 100, "used": used, "limit": _DAILY_DEFAULT, "pct": round(pct, 1)}


def enforce(tenant_id: str) -> bool:
    result = check_budget(tenant_id)
    if not result["ok"]:
        logger.warning("Budget exhausted for tenant %s: %d/%d tokens", tenant_id, result["used"], result["limit"])
    return result["ok"]
