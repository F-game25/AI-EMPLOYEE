import asyncio
import logging
from typing import Optional, Any, Callable
from collections import deque
import time
from .schema import WebSocketBatchMetrics

logger = logging.getLogger(__name__)


class WebSocketBatcher:
    def __init__(self, batch_window_ms: float = 50.0, max_batch_size: int = 50):
        self.batch_window_ms = batch_window_ms
        self.max_batch_size = max_batch_size
        self.message_queue: deque[Any] = deque()
        self.metrics = WebSocketBatchMetrics()
        self._flushing = False

    async def enqueue_message(self, message: Any) -> None:
        self.message_queue.append(message)
        self.metrics.total_messages += 1

        if len(self.message_queue) >= self.max_batch_size:
            await self.flush()

    async def flush(self, handler: Optional[Callable[[list[Any]], Any]] = None) -> list[Any]:
        if self._flushing or not self.message_queue:
            return []

        self._flushing = True
        batch = []
        while self.message_queue and len(batch) < self.max_batch_size:
            batch.append(self.message_queue.popleft())

        if handler:
            try:
                await handler(batch)
            except Exception as e:
                logger.warning("Failed to flush batch: %s", e)
                for msg in batch:
                    self.message_queue.appendleft(msg)

        self.metrics.batches_sent += 1
        if self.metrics.batches_sent > 0:
            self.metrics.avg_batch_size = self.metrics.total_messages / self.metrics.batches_sent
        self.metrics.max_batch_size = max(self.metrics.max_batch_size, len(batch))

        self._flushing = False
        return batch

    async def start_auto_flush(self, handler: Callable[[list[Any]], Any]) -> None:
        while True:
            await asyncio.sleep(self.batch_window_ms / 1000)
            if self.message_queue:
                await self.flush(handler)

    def get_metrics(self) -> dict:
        return {
            "total_messages": self.metrics.total_messages,
            "batches_sent": self.metrics.batches_sent,
            "avg_batch_size": round(self.metrics.avg_batch_size, 2),
            "max_batch_size": self.metrics.max_batch_size,
            "pending_messages": len(self.message_queue),
        }


_instance: Optional[WebSocketBatcher] = None


def get_ws_batcher() -> WebSocketBatcher:
    global _instance
    if _instance is None:
        _instance = WebSocketBatcher()
    return _instance
