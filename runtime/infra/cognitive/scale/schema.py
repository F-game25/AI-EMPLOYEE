from dataclasses import dataclass, field
from typing import Optional
import time


@dataclass
class CacheMetrics:
    hits: int = 0
    misses: int = 0
    evictions: int = 0
    entries_count: int = 0
    sample_time: float = field(default_factory=time.time)

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0.0


@dataclass
class PartitionStats:
    shard_id: str = ""
    node_count: int = 0
    edge_count: int = 0
    partition_key: str = ""
    created_at: float = field(default_factory=time.time)


@dataclass
class CompressionStats:
    original_event_count: int = 0
    compressed_event_count: int = 0
    bytes_saved: int = 0
    sample_time: float = field(default_factory=time.time)

    @property
    def compression_ratio(self) -> float:
        if self.original_event_count == 0:
            return 0.0
        return 1.0 - (self.compressed_event_count / self.original_event_count)


@dataclass
class WebSocketBatchMetrics:
    total_messages: int = 0
    batches_sent: int = 0
    avg_batch_size: float = 0.0
    max_batch_size: int = 0
    sample_time: float = field(default_factory=time.time)
