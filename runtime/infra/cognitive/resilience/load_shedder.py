import logging
from typing import Optional
from .schema import EventTier

logger = logging.getLogger(__name__)


class LoadShedder:
    def __init__(self):
        self.queue_depth_thresholds = {
            10000: {EventTier.P3},                       # >10k: drop P3
            50000: {EventTier.P3, EventTier.P2},        # >50k: drop P2+P3
            100000: {EventTier.P3, EventTier.P2, EventTier.P1},  # >100k: drop except P0
        }
        self.stats = {"total_shed": 0, "shed_by_tier": {}}

    def should_shed(self, tier: EventTier, queue_depth: int) -> bool:
        for threshold, tiers_to_drop in sorted(self.queue_depth_thresholds.items(), reverse=True):
            if queue_depth > threshold and tier in tiers_to_drop:
                self._log_shed(tier, queue_depth)
                return True
        return False

    def _log_shed(self, tier: EventTier, queue_depth: int) -> None:
        self.stats["total_shed"] += 1
        if tier not in self.stats["shed_by_tier"]:
            self.stats["shed_by_tier"][tier] = 0
        self.stats["shed_by_tier"][tier] += 1
        logger.warning("Shedding event tier %s at queue_depth=%d", tier.value, queue_depth)

    def get_stats(self) -> dict:
        return {
            "total_shed": self.stats["total_shed"],
            "shed_by_tier": {k: v for k, v in self.stats["shed_by_tier"].items()},
        }


_instance: Optional[LoadShedder] = None


def get_load_shedder() -> LoadShedder:
    global _instance
    if _instance is None:
        _instance = LoadShedder()
    return _instance
