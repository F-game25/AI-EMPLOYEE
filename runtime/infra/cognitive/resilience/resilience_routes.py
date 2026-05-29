from fastapi import APIRouter, Request
import logging

from .event_prioritizer import get_event_prioritizer
from .subsystem_isolator import get_subsystem_isolator
from .adaptive_throttler import get_adaptive_throttler
from .load_shedder import get_load_shedder
from .backpressure_propagator import get_backpressure_propagator

router = APIRouter()
logger = logging.getLogger(__name__)


def _tenant(req: Request) -> str:
    return getattr(req.state, "tenant_id", None) or req.headers.get("X-Tenant-Id", "system")


@router.get("/status")
async def resilience_status(req: Request):
    throttler = get_adaptive_throttler()
    isolator = get_subsystem_isolator()
    return {
        "degradation_level": throttler.degradation_level.value,
        "system_load": throttler.get_status(),
        "subsystems": {k: {"status": v.status, "failures": v.failure_count}
                       for k, v in isolator.get_all_status().items()},
    }


@router.get("/events")
async def get_resilience_events(req: Request):
    prioritizer = get_event_prioritizer()
    return {"event_stats": prioritizer.get_stats()}


@router.get("/degradation")
async def get_degradation(req: Request):
    throttler = get_adaptive_throttler()
    return throttler.get_status()


@router.get("/queue-depths")
async def get_queue_depths(req: Request):
    propagator = get_backpressure_propagator()
    return {
        "states": {
            subsys_id: {
                "queue_depth": state.queue_depth,
                "is_backpressured": state.is_backpressured,
                "threshold_high": state.threshold_high,
                "threshold_clear": state.threshold_clear,
            }
            for subsys_id, state in propagator.get_all_states().items()
        }
    }


@router.post("/emergency-stop")
async def emergency_stop(req: Request):
    try:
        from core.bus import get_message_bus
        get_message_bus().publish_sync("notifications", {
            "event": "resilience:emergency_stop",
            "tenant_id": _tenant(req),
        })
        return {"status": "emergency_stop_initiated"}
    except Exception as e:
        logger.warning("emergency stop failed: %s", type(e).__name__)
        return {"error": "emergency stop failed"}


@router.post("/resume")
async def resume(req: Request):
    try:
        from core.bus import get_message_bus
        get_message_bus().publish_sync("notifications", {
            "event": "resilience:resume",
            "tenant_id": _tenant(req),
        })
        return {"status": "resume_initiated"}
    except Exception as e:
        logger.warning("resume failed: %s", type(e).__name__)
        return {"error": "resume failed"}
