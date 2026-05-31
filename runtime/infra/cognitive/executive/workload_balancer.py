import asyncio
import logging
import time
from typing import Optional
from .schema import WorkloadState

logger = logging.getLogger(__name__)
_states: dict[str, WorkloadState] = {}


class WorkloadBalancer:
    def __init__(self):
        self._running = False

    async def start(self) -> None:
        self._running = True
        while self._running:
            await asyncio.sleep(30)
            self._poll()

    def _poll(self) -> None:
        try:
            from infra.healing.health_scorer import score_service
            for agent_id, state in list(_states.items()):
                hs = score_service(agent_id)
                utilization = max(0.0, 100.0 - hs.score)
                _states[agent_id] = WorkloadState(
                    agent_id=agent_id,
                    utilization_pct=utilization,
                    queue_depth=state.queue_depth,
                    active_tasks=state.active_tasks,
                    avg_latency_ms=hs.latency_score,
                    sampled_at=time.time(),
                )
                if utilization > 85:
                    self._emit_rebalance(agent_id, utilization)
        except Exception as e:
            logger.debug("Workload poll skipped: %s", e)

    def _emit_rebalance(self, agent_id: str, utilization: float) -> None:
        try:
            from core.bus import get_message_bus
            get_message_bus().publish_sync("notifications", {
                "event": "executive:rebalance",
                "agent_id": agent_id,
                "utilization": utilization,
            })
        except Exception:
            pass

    def register(self, agent_id: str) -> None:
        _states.setdefault(agent_id, WorkloadState(agent_id=agent_id))

    def get_all(self) -> list[dict]:
        import dataclasses
        return [dataclasses.asdict(s) for s in _states.values()]

    def stop(self) -> None:
        self._running = False


_instance: Optional[WorkloadBalancer] = None


def get_workload_balancer() -> WorkloadBalancer:
    global _instance
    if _instance is None:
        _instance = WorkloadBalancer()
    return _instance
