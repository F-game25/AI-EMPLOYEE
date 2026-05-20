import logging
import time
from typing import Optional, Any
from .schema import CacheMetrics

logger = logging.getLogger(__name__)


class AdaptiveCache:
    def __init__(self, max_entries: int = 1000, ttl_s: float = 60.0):
        self.max_entries = max_entries
        self.ttl_s = ttl_s
        self.cache: dict[str, tuple[Any, float]] = {}
        self.metrics = CacheMetrics()

    def get(self, key: str) -> Optional[Any]:
        if key in self.cache:
            value, timestamp = self.cache[key]
            if time.time() - timestamp < self.ttl_s:
                self.metrics.hits += 1
                return value
            else:
                del self.cache[key]

        self.metrics.misses += 1
        return None

    def set(self, key: str, value: Any) -> None:
        if len(self.cache) >= self.max_entries:
            self._evict_oldest()

        self.cache[key] = (value, time.time())
        self.metrics.entries_count = len(self.cache)

    def _evict_oldest(self) -> None:
        if not self.cache:
            return

        oldest_key = min(self.cache.keys(), key=lambda k: self.cache[k][1])
        del self.cache[oldest_key]
        self.metrics.evictions += 1

    def invalidate(self, key: str) -> None:
        if key in self.cache:
            del self.cache[key]
            self.metrics.entries_count = len(self.cache)

    def invalidate_pattern(self, pattern: str) -> int:
        matching_keys = [k for k in self.cache.keys() if pattern in k]
        for key in matching_keys:
            del self.cache[key]
        self.metrics.entries_count = len(self.cache)
        return len(matching_keys)

    def clear(self) -> None:
        self.cache.clear()
        self.metrics.entries_count = 0

    def get_metrics(self) -> dict:
        return {
            "hits": self.metrics.hits,
            "misses": self.metrics.misses,
            "hit_rate": round(self.metrics.hit_rate, 4),
            "entries": self.metrics.entries_count,
            "evictions": self.metrics.evictions,
        }


_instance: Optional[AdaptiveCache] = None


def get_adaptive_cache() -> AdaptiveCache:
    global _instance
    if _instance is None:
        _instance = AdaptiveCache()
    return _instance
