import logging
from .cycle_detector import get_cycles
from .urgency_engine import compute_urgency

logger = logging.getLogger(__name__)


def create_schedule(initiatives: list[dict], tenant_id: str) -> list[dict]:
    cycles = get_cycles(tenant_id)
    cycle_map = {c["workflow_type"]: c for c in cycles}

    scored = []
    for init in initiatives:
        urgency_score = 0.0
        if init.get("deadline"):
            u = compute_urgency(init["id"], init.get("priority", 5), init["deadline"])
            urgency_score = u.urgency
        scored.append((init, urgency_score))

    scored.sort(key=lambda x: -x[1])
    return [item[0] for item in scored[:10]]


def get_schedule(initiatives: list[dict], tenant_id: str) -> dict:
    schedule = create_schedule(initiatives, tenant_id)
    return {
        "schedule": schedule,
        "count": len(schedule),
        "tenant_id": tenant_id,
    }
