"""Background scheduler — periodically refresh pinned standing topics."""
import asyncio
import logging
import time
from typing import Optional

log = logging.getLogger(__name__)

SCHEDULE_INTERVALS = {
    'every_30m': 30 * 60,
    'every_1h':   1 * 60 * 60,
    'every_6h':   6 * 60 * 60,
    'every_24h': 24 * 60 * 60,
    'manual':    None,
}


class TopicScheduler:
    def __init__(self):
        self._task: Optional[asyncio.Task] = None
        self._running = False
        self._last_runs: dict = {}

    async def start(self):
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        log.info("TopicScheduler started")

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()

    async def _loop(self):
        while self._running:
            try:
                await self._tick()
            except Exception as e:
                log.error(f"TopicScheduler tick error: {e}")
            await asyncio.sleep(60)

    async def _tick(self):
        try:
            from memory.topic_intelligence import list_topics
            from core.learning_orchestrator import execute_learning
        except Exception as e:
            log.debug(f"scheduler deps not ready: {e}")
            return

        now = time.time()
        for topic in list_topics(pinned_only=True):
            schedule = topic.get('schedule', 'manual')
            interval = SCHEDULE_INTERVALS.get(schedule)
            if interval is None:
                continue
            last = self._last_runs.get(topic['id'], topic.get('last_studied', 0))
            if (now - last) < interval:
                continue
            try:
                log.info(f"Auto-refresh pinned topic: {topic['id']}")
                await execute_learning(
                    topic=topic['label'],
                    scope=topic.get('scope', ''),
                    depth='normal',
                    verification_level='normal',
                    schedule_recurring=False,
                )
                self._last_runs[topic['id']] = now
            except Exception as e:
                log.warning(f"Auto-refresh failed for {topic['id']}: {e}")


_singleton: Optional[TopicScheduler] = None


def get_scheduler() -> TopicScheduler:
    global _singleton
    if _singleton is None:
        _singleton = TopicScheduler()
    return _singleton
