import asyncio
import logging
from typing import Optional, Callable, Any
from dataclasses import dataclass
import time

logger = logging.getLogger(__name__)


@dataclass
class SubsystemState:
    id: str
    status: str  # running | failed | restarting | isolated
    task: Optional[asyncio.Task] = None
    failure_count: int = 0
    last_failure_time: Optional[float] = None
    restart_backoff_ms: int = 1000


class SubsystemIsolator:
    def __init__(self, max_restarts: int = 5, backoff_multiplier: float = 2.0):
        self.subsystems: dict[str, SubsystemState] = {}
        self.max_restarts = max_restarts
        self.backoff_multiplier = backoff_multiplier

    async def run_isolated(self, subsystem_id: str, coro: Callable[[], Any]) -> None:
        if subsystem_id not in self.subsystems:
            self.subsystems[subsystem_id] = SubsystemState(id=subsystem_id, status="running")

        state = self.subsystems[subsystem_id]

        try:
            state.status = "running"
            await coro()
        except Exception as e:
            state.failure_count += 1
            state.last_failure_time = time.time()
            state.status = "failed"
            logger.error(
                "Subsystem %s failed (attempt %d/%d): %s",
                subsystem_id,
                state.failure_count,
                self.max_restarts,
                e,
            )

            if state.failure_count < self.max_restarts:
                await self._schedule_restart(subsystem_id, coro)
            else:
                state.status = "isolated"
                logger.error("Subsystem %s isolated after %d failures", subsystem_id, self.max_restarts)

    async def _schedule_restart(self, subsystem_id: str, coro: Callable[[], Any]) -> None:
        state = self.subsystems[subsystem_id]
        backoff_ms = state.restart_backoff_ms * (self.backoff_multiplier ** (state.failure_count - 1))
        backoff_s = min(backoff_ms / 1000, 60)  # cap at 60 seconds

        logger.info("Restarting subsystem %s in %.1fs", subsystem_id, backoff_s)
        state.status = "restarting"

        await asyncio.sleep(backoff_s)
        await self.run_isolated(subsystem_id, coro)

    def get_status(self, subsystem_id: str) -> Optional[SubsystemState]:
        return self.subsystems.get(subsystem_id)

    def get_all_status(self) -> dict[str, SubsystemState]:
        return dict(self.subsystems)

    def is_healthy(self, subsystem_id: str) -> bool:
        state = self.subsystems.get(subsystem_id)
        return state is not None and state.status == "running"


_instance: Optional[SubsystemIsolator] = None


def get_subsystem_isolator() -> SubsystemIsolator:
    global _instance
    if _instance is None:
        _instance = SubsystemIsolator()
    return _instance
