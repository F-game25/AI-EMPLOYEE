import logging
from typing import Optional
from collections import defaultdict
import time
from .schema import CompressionStats

logger = logging.getLogger(__name__)


class EventCompressor:
    def __init__(self, frequency_threshold: int = 5, window_s: float = 1.0):
        self.frequency_threshold = frequency_threshold
        self.window_s = window_s
        self.event_counts: defaultdict[str, list] = defaultdict(list)
        self.compression_stats = CompressionStats()

    def record_event(self, event_type: str, agent_id: str = "unknown") -> dict:
        key = f"{event_type}:{agent_id}"
        now = time.time()

        self.event_counts[key].append(now)
        self._cleanup_old_events(key, now)

        count = len(self.event_counts[key])
        if count >= self.frequency_threshold:
            self.compression_stats.original_event_count += count
            self.compression_stats.compressed_event_count += 1
            self.compression_stats.bytes_saved += count * 50

            self.event_counts[key].clear()

            return {
                "type": event_type,
                "agent_id": agent_id,
                "count": count,
                "period_s": self.window_s,
                "compressed": True,
            }

        return {
            "type": event_type,
            "agent_id": agent_id,
            "compressed": False,
        }

    def _cleanup_old_events(self, key: str, now: float) -> None:
        self.event_counts[key] = [
            ts for ts in self.event_counts[key]
            if now - ts < self.window_s
        ]

    def get_stats(self) -> dict:
        return {
            "original_event_count": self.compression_stats.original_event_count,
            "compressed_event_count": self.compression_stats.compressed_event_count,
            "bytes_saved": self.compression_stats.bytes_saved,
            "compression_ratio": round(self.compression_stats.compression_ratio, 4),
        }


_instance: Optional[EventCompressor] = None


def get_event_compressor() -> EventCompressor:
    global _instance
    if _instance is None:
        _instance = EventCompressor()
    return _instance
