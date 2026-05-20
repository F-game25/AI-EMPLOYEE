import math
import time
import logging
from .schema import UrgencyScore

logger = logging.getLogger(__name__)


def compute_urgency(initiative_id: str, base_priority: int, deadline_ts: float) -> UrgencyScore:
    now = time.time()
    remaining = deadline_ts - now
    if remaining <= 0:
        urgency = 100.0
    else:
        decay_rate = 0.01 if remaining > 3 * 86400 else 0.05  # faster decay in last 3 days
        urgency = base_priority * 10 * math.exp(decay_rate * (-remaining))
        urgency = min(100.0, max(0.0, urgency))

    return UrgencyScore(
        initiative_id=initiative_id,
        base_priority=base_priority,
        time_remaining_s=max(0.0, remaining),
        urgency=round(urgency, 1),
    )
