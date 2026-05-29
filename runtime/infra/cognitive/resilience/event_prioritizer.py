import asyncio
import logging
from typing import Optional, Callable, Any
from collections import defaultdict
from .schema import EventTier

logger = logging.getLogger(__name__)


class EventPrioritizer:
    def __init__(self, max_queue_sizes: dict[str, int] = None):
        if max_queue_sizes is None:
            max_queue_sizes = {
                EventTier.P0: 1000,
                EventTier.P1: 5000,
                EventTier.P2: 10000,
                EventTier.P3: 50000,
            }
        self.max_queue_sizes = max_queue_sizes
        self.queues: dict[str, asyncio.Queue[Any]] = {}
        self.stats: dict[str, dict] = defaultdict(lambda: {"total": 0, "dropped": 0})

        for tier in EventTier:
            self.queues[tier.value] = asyncio.Queue(maxsize=max_queue_sizes[tier])

    async def enqueue(self, tier: EventTier, event: Any) -> bool:
        if tier not in [t.value for t in EventTier]:
            logger.warning("Invalid tier: %s", tier)
            return False

        try:
            self.queues[tier].put_nowait(event)
            self.stats[tier]["total"] += 1
            return True
        except asyncio.QueueFull:
            self.stats[tier]["dropped"] += 1
            logger.warning("Queue full for tier %s, dropping event", tier)
            return False

    async def process_queues(self, handler: Callable[[EventTier, Any], Any], degradation_factor: float = 1.0) -> None:
        while True:
            for tier in [EventTier.P0, EventTier.P1, EventTier.P2, EventTier.P3]:
                if tier == EventTier.P3 and degradation_factor > 0.7:
                    continue
                if tier == EventTier.P2 and degradation_factor > 0.85:
                    continue

                try:
                    event = self.queues[tier.value].get_nowait()
                    await handler(tier, event)
                except asyncio.QueueEmpty:
                    pass

            await asyncio.sleep(0.1)

    def get_stats(self) -> dict[str, dict]:
        return {
            tier: {
                "total": self.stats[tier]["total"],
                "dropped": self.stats[tier]["dropped"],
                "queue_size": self.queues[tier].qsize(),
            }
            for tier in [t.value for t in EventTier]
        }


_instance: Optional[EventPrioritizer] = None


def get_event_prioritizer() -> EventPrioritizer:
    global _instance
    if _instance is None:
        _instance = EventPrioritizer()
    return _instance
