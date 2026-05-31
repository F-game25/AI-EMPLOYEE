import logging
import time
from typing import Optional, Dict
from .schema import BackpressureState

logger = logging.getLogger(__name__)


class BackpressurePropagator:
    def __init__(self):
        self.backpressure_states: Dict[str, BackpressureState] = {}

    def check_and_emit(self, subsystem_id: str, queue_depth: int, queue_max: int = 10000) -> bool:
        if subsystem_id not in self.backpressure_states:
            self.backpressure_states[subsystem_id] = BackpressureState(
                subsystem_id=subsystem_id,
                queue_max_depth=queue_max,
            )

        state = self.backpressure_states[subsystem_id]
        state.queue_depth = queue_depth
        state.timestamp = time.time()

        threshold_high = state.threshold_high * state.queue_max_depth
        threshold_clear = state.threshold_clear * state.queue_max_depth

        if not state.is_backpressured and queue_depth > threshold_high:
            state.is_backpressured = True
            state.backpressure_triggered_at = time.time()
            logger.warning(
                "Backpressure triggered for %s: queue_depth=%d (threshold=%.0f)",
                subsystem_id,
                queue_depth,
                threshold_high,
            )
            self._emit_backpressure_signal(subsystem_id, "slow_down")
            return True

        elif state.is_backpressured and queue_depth < threshold_clear:
            state.is_backpressured = False
            logger.info(
                "Backpressure cleared for %s: queue_depth=%d (threshold=%.0f)",
                subsystem_id,
                queue_depth,
                threshold_clear,
            )
            self._emit_backpressure_signal(subsystem_id, "resume")
            return False

        return state.is_backpressured

    def _emit_backpressure_signal(self, subsystem_id: str, signal: str) -> None:
        try:
            from core.bus import get_message_bus
            get_message_bus().publish_sync("notifications", {
                "event": f"backpressure:{signal}",
                "subsystem_id": subsystem_id,
            })
        except Exception as e:
            logger.warning("Failed to emit backpressure signal: %s", e)

    def is_backpressured(self, subsystem_id: str) -> bool:
        state = self.backpressure_states.get(subsystem_id)
        return state is not None and state.is_backpressured

    def get_state(self, subsystem_id: str) -> Optional[BackpressureState]:
        return self.backpressure_states.get(subsystem_id)

    def get_all_states(self) -> Dict[str, BackpressureState]:
        return dict(self.backpressure_states)


_instance: Optional[BackpressurePropagator] = None


def get_backpressure_propagator() -> BackpressurePropagator:
    global _instance
    if _instance is None:
        _instance = BackpressurePropagator()
    return _instance
