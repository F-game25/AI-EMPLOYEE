import collections
import time
import logging

logger = logging.getLogger(__name__)

_THRESHOLD = 100  # events/s per channel
_SUPPRESS_S = 10
_window: dict[str, collections.deque] = {}
_suppressed: dict[str, float] = {}


def check(channel: str, tenant_id: str) -> bool:
    key = f"{tenant_id}:{channel}"
    now = time.time()

    # Check suppression
    if key in _suppressed:
        if now < _suppressed[key]:
            return False  # still suppressed
        del _suppressed[key]

    _window.setdefault(key, collections.deque())
    q = _window[key]
    q.append(now)
    # Keep only last 1s
    while q and q[0] < now - 1.0:
        q.popleft()

    if len(q) >= _THRESHOLD:
        _suppressed[key] = now + _SUPPRESS_S
        _emit_storm(channel, tenant_id, len(q))
        return False  # suppress
    return True


def _emit_storm(channel: str, tenant_id: str, rate: int) -> None:
    logger.warning("Event storm detected: %s/%s rate=%d/s", tenant_id, channel, rate)
    try:
        from core.bus import get_message_bus
        get_message_bus().publish_sync("notifications", {
            "event": "guardrail:event_storm",
            "channel": channel,
            "tenant_id": tenant_id,
            "rate": rate,
        })
    except Exception:
        pass


def get_suppressions() -> dict:
    now = time.time()
    return {k: v - now for k, v in _suppressed.items() if v > now}
