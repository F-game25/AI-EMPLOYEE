"""WorkflowWatchdog — scan for stuck Temporal workflows and signal cancellation."""
from __future__ import annotations
import asyncio
import collections
import logging
import os
import time
from typing import Optional

logger = logging.getLogger(__name__)

_POLL_INTERVAL = 30     # seconds
_WORKFLOW_TIMEOUT = int(os.getenv("WORKFLOW_TIMEOUT_S", "3600"))    # 1hr default
_HEARTBEAT_TIMEOUT = int(os.getenv("HEARTBEAT_TIMEOUT_S", "300"))   # 5min

try:
    from temporalio.client import Client as TemporalClient
    _TEMPORAL_OK = True
except ImportError:
    _TEMPORAL_OK = False


_TERMINATED_CACHE_SIZE = 2000  # remember last N terminated IDs to avoid double-signal


class WorkflowWatchdog:
    def __init__(self):
        self._client: Optional[object] = None
        # Bounded deque prevents unbounded memory growth in long-running processes
        self._terminated: collections.deque[str] = collections.deque(
            maxlen=_TERMINATED_CACHE_SIZE
        )

    async def _connect(self) -> bool:
        if not _TEMPORAL_OK:
            return False
        if self._client:
            return True
        try:
            url = os.getenv("TEMPORAL_SERVER_URL", "localhost:7233")
            self._client = await TemporalClient.connect(url)
            logger.info("WorkflowWatchdog connected to Temporal at %s", url)
            return True
        except Exception as e:
            logger.debug("Temporal not available: %s", e)
            return False

    async def start(self) -> None:
        logger.info("WorkflowWatchdog starting (poll every %ds)", _POLL_INTERVAL)
        while True:
            await asyncio.sleep(_POLL_INTERVAL)
            if await self._connect():
                await self._scan()

    async def _scan(self) -> None:
        try:
            now = time.time()
            async for wf in self._client.list_workflows('WorkflowType!=""'):
                run_time = now - wf.start_time.timestamp() if wf.start_time else 0
                last_hb = getattr(wf, "close_time", None)
                # Check if workflow exceeds timeout
                if run_time > _WORKFLOW_TIMEOUT:
                    wid = wf.id
                    if wid not in self._terminated:
                        logger.warning("Terminating stuck workflow %s (ran %.0fs)", wid, run_time)
                        try:
                            handle = self._client.get_workflow_handle(wid)
                            await handle.terminate("Stuck — exceeded timeout")
                            self._terminated.append(wid)
                        except Exception as e:
                            logger.error("Failed to terminate %s: %s", wid, e)
        except Exception as e:
            logger.debug("Watchdog scan error: %s", e)

    def stats(self) -> dict:
        return {
            "temporal_available": _TEMPORAL_OK,
            "terminated_count": len(self._terminated),
            "poll_interval_s": _POLL_INTERVAL,
        }


_watchdog: Optional[WorkflowWatchdog] = None


def get_workflow_watchdog() -> WorkflowWatchdog:
    global _watchdog
    if _watchdog is None:
        _watchdog = WorkflowWatchdog()
    return _watchdog
