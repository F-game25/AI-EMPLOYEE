"""KnowledgeScheduler — passive idle-research and knowledge maintenance.

Runs as asyncio background task:
- Every KNOWLEDGE_ACQUISITION_INTERVAL_S seconds (default 3600):
  1. Pick a topic from the pending queue or generate one from recent activity
  2. Run AutoResearchAgent to gather info
  3. Add to KnowledgeVault with confidence score
  4. Broadcast 'knowledge:new_entry' event via bus
- Every 24h: prune low-confidence entries (< 0.3 after 7 days)
"""
from __future__ import annotations

import asyncio
import heapq
import logging
import os
import time
from typing import Optional

from .knowledge_vault import KnowledgeVault, get_knowledge_vault

logger = logging.getLogger(__name__)

_INTERVAL = int(os.environ.get('KNOWLEDGE_ACQUISITION_INTERVAL_S', 3600))
_PRUNE_INTERVAL = 86400  # 24 h


class KnowledgeScheduler:
    def __init__(self, vault: KnowledgeVault = None, bus=None):
        self._vault = vault or get_knowledge_vault()
        self._bus = bus
        self._queue: list[tuple[int, float, str]] = []  # (neg_priority, enqueue_ts, topic)
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._prune_task: Optional[asyncio.Task] = None
        self._last_prune = 0.0

    # ── public ─────────────────────────────────────────────────────────────────

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._research_loop())
        self._prune_task = asyncio.create_task(self._prune_loop())
        logger.info('KnowledgeScheduler started (interval=%ds)', _INTERVAL)

    def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
        if self._prune_task:
            self._prune_task.cancel()

    def queue_topic(self, topic: str, priority: int = 5) -> None:
        """Add a topic to the research queue. Higher priority = researched sooner."""
        heapq.heappush(self._queue, (-priority, time.monotonic(), topic))
        logger.info('KnowledgeScheduler: queued topic "%s" (priority %d)', topic, priority)

    # ── loops ──────────────────────────────────────────────────────────────────

    async def _research_loop(self) -> None:
        while self._running:
            try:
                await asyncio.sleep(_INTERVAL)
                if self._running:
                    await self._research_cycle()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning('KnowledgeScheduler research cycle error: %s', exc)

    async def _prune_loop(self) -> None:
        while self._running:
            try:
                await asyncio.sleep(_PRUNE_INTERVAL)
                if self._running:
                    n = self._vault.prune_low_confidence(threshold=0.3, older_than_days=7)
                    if n:
                        logger.info('KnowledgeScheduler: pruned %d low-confidence entries', n)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning('KnowledgeScheduler prune error: %s', exc)

    async def _research_cycle(self) -> None:
        topic = self._pick_topic()
        if not topic:
            logger.debug('KnowledgeScheduler: no topic to research')
            return

        logger.info('KnowledgeScheduler: researching "%s"', topic)
        content, confidence, source = await self._run_research(topic)
        if not content:
            return

        slug = self._vault.add_entry(
            title=topic,
            content=content,
            source=source,
            confidence=confidence,
            tags=['auto-research'],
        )
        logger.info('KnowledgeScheduler: stored entry "%s" (slug=%s, conf=%.2f)', topic, slug, confidence)
        self._emit('knowledge:new_entry', {'slug': slug, 'title': topic, 'confidence': confidence})

    # ── helpers ────────────────────────────────────────────────────────────────

    def _pick_topic(self) -> Optional[str]:
        if self._queue:
            _, _, topic = heapq.heappop(self._queue)
            return topic
        # Fall back to pending-review entries that need refinement
        pending = self._vault.list_pending_review()
        if pending:
            entry = min(pending, key=lambda e: e.get('confidence', 1.0))
            return entry.get('title')
        return None

    async def _run_research(self, topic: str) -> tuple[str, float, str]:
        """Run research via AutoResearchAgent. Returns (content, confidence, source)."""
        try:
            from core.auto_research_agent import AutoResearchAgent
            agent = AutoResearchAgent()
            result = await asyncio.get_event_loop().run_in_executor(
                None, lambda: agent.research(topic)
            )
            if isinstance(result, dict):
                content = result.get('summary', result.get('content', ''))
                confidence = float(result.get('confidence', 0.6))
                source = result.get('source', 'auto-research')
                return content, confidence, source
            return str(result), 0.6, 'auto-research'
        except Exception as exc:
            logger.warning('KnowledgeScheduler: research failed for "%s": %s', topic, exc)
            return '', 0.0, ''

    def _emit(self, event: str, data: dict) -> None:
        if not self._bus:
            return
        try:
            self._bus.publish('notifications', {'event': event, **data})
        except Exception:
            pass


# Singleton
_scheduler_instance: Optional[KnowledgeScheduler] = None


def get_knowledge_scheduler(vault: KnowledgeVault = None, bus=None) -> KnowledgeScheduler:
    global _scheduler_instance
    if _scheduler_instance is None:
        _scheduler_instance = KnowledgeScheduler(vault=vault, bus=bus)
    return _scheduler_instance
