import logging
from typing import Optional

logger = logging.getLogger(__name__)


class ReasoningLineageTracker:
    def __init__(self):
        self.traces: dict[str, list[dict]] = {}

    def record_step(self, trace_id: str, step_index: int, step_data: dict) -> None:
        if trace_id not in self.traces:
            self.traces[trace_id] = []

        self.traces[trace_id].append({
            "index": step_index,
            "type": step_data.get("type", "unknown"),
            "input": step_data.get("input", ""),
            "output": step_data.get("output", ""),
            "duration_ms": step_data.get("duration_ms", 0),
            "timestamp": step_data.get("timestamp", 0),
        })

    def get_trace(self, trace_id: str) -> list[dict]:
        return self.traces.get(trace_id, [])

    def get_from_neural_brain(self, trace_id: str) -> list[dict]:
        try:
            from neural_brain.core.reasoning_trace import get_trace
            return get_trace(trace_id) or []
        except Exception as e:
            logger.warning("Failed to load reasoning trace from neural_brain: %s", e)
            return []

    def clear_trace(self, trace_id: str) -> None:
        if trace_id in self.traces:
            del self.traces[trace_id]


_instance: Optional[ReasoningLineageTracker] = None


def get_reasoning_lineage_tracker() -> ReasoningLineageTracker:
    global _instance
    if _instance is None:
        _instance = ReasoningLineageTracker()
    return _instance
