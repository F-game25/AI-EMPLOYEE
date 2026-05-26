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
        # Normalize remaining to days; urgency = priority * 10 * exp(-remaining_days * rate)
        # rate=0.15 → 7-day deadline scores ~14, 1-day scores ~86 (for priority=10)
        remaining_days = remaining / 86400.0
        decay_rate = 0.15 if remaining > 3 * 86400 else 0.5
        urgency = base_priority * 10 * math.exp(decay_rate * (-remaining_days))
        urgency = min(100.0, max(0.0, urgency))

    return UrgencyScore(
        initiative_id=initiative_id,
        base_priority=base_priority,
        time_remaining_s=max(0.0, remaining),
        urgency=round(urgency, 1),
    )
