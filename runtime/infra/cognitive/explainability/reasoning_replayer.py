import logging
from typing import Optional

logger = logging.getLogger(__name__)


def replay(trace_id: str) -> Optional[dict]:
    try:
        from neural_brain.core.reasoning_trace import ReasoningTrace
        trace = ReasoningTrace.load(trace_id)
        if trace:
            return {"trace_id": trace_id, "steps": trace.steps if hasattr(trace, "steps") else [], "ok": True}
    except Exception as e:
        logger.debug("Reasoning replay unavailable: %s", e)
    return {"trace_id": trace_id, "steps": [], "ok": False, "reason": "trace_not_found"}
