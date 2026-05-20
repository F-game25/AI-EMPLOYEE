"""Autonomy loop detector.

Monitors agent trigger chains and detects cycles using DFS.
Maintains per-tenant directed graph of agent triggers.
Auto-resets graph every 60s to prevent stale edges.
"""
import asyncio
import collections
import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)

_MAX_EDGES = 500  # max edges per tenant


class LoopDetector:
    """Detects recursive/cyclic agent trigger chains."""

    def __init__(self):
        self._graph: dict[str, set[str]] = {}  # tenant:agent -> {tenant:agent}
        self._detected: collections.deque = collections.deque(maxlen=100)
        self._running = False
        self._lock = asyncio.Lock()

    def add_trigger(self, source_agent: str, triggered_agent: str, tenant_id: str) -> bool:
        """Add trigger edge and check for cycles.

        Returns True if cycle detected, False otherwise.
        """
        key = f"{tenant_id}:{source_agent}"
        target = f"{tenant_id}:{triggered_agent}"

        self._graph.setdefault(key, set()).add(target)

        # Prune old edges if graph too large
        if len(self._graph) > _MAX_EDGES:
            oldest = next(iter(self._graph))
            del self._graph[oldest]

        # Check for cycle from source
        if self._detect_cycle(key):
            record = {
                "source": source_agent,
                "target": triggered_agent,
                "tenant": tenant_id,
                "ts": time.time(),
            }
            self._detected.append(record)
            logger.warning(f"Loop detected: {source_agent} -> {triggered_agent} (tenant={tenant_id})")

            try:
                from core.bus import get_message_bus
                get_message_bus().publish_sync("notifications", {
                    "event": "cognitive:loop_detected",
                    "tenant_id": tenant_id,
                    "agents": [source_agent, triggered_agent],
                })
            except Exception as e:
                logger.debug(f"Bus publish failed: {e}")
            return True
        return False

    def _detect_cycle(self, start: str) -> bool:
        """DFS-based cycle detection in agent graph."""
        visited: set = set()
        stack: set = set()

        def dfs(node: str) -> bool:
            visited.add(node)
            stack.add(node)
            for neighbor in self._graph.get(node, set()):
                if neighbor not in visited:
                    if dfs(neighbor):
                        return True
                elif neighbor in stack:
                    return True
            stack.discard(node)
            return False

        return dfs(start)

    def get_detected(self) -> list[dict]:
        """Get list of detected cycles."""
        return list(self._detected)

    async def start(self) -> None:
        """Start background graph cleanup loop.

        Clears graph every 60s to avoid stale edges and unbounded growth.
        """
        self._running = True
        while self._running:
            try:
                await asyncio.sleep(60)
                self._graph.clear()
                logger.debug(f"Loop detector graph cleared ({len(self._detected)} cycles in window)")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Loop detector error: {e}")

    def stop(self) -> None:
        """Stop background loop."""
        self._running = False


_instance: Optional[LoopDetector] = None


def get_loop_detector() -> LoopDetector:
    """Get singleton loop detector instance."""
    global _instance
    if _instance is None:
        _instance = LoopDetector()
    return _instance
