"""Python -> Node WebSocket bridge.

The Node backend exposes POST /internal/events (localhost-only) which calls
broadcaster.broadcast(event, data). This module gives the Python runtime a
fire-and-forget ``emit(event, data)`` API that ships events to that endpoint
without blocking the caller.

Design notes:
- Bounded queue with drop-oldest semantics: if Node is down or slow, we never
  back-pressure cognitive code paths.
- Single daemon drain thread per process, started lazily on first emit.
- Works correctly from asyncio.to_thread() worker threads (no event loop needed).
- Failures are logged at DEBUG and otherwise swallowed — the dashboard is
  best-effort visibility, not a correctness boundary.
"""
from __future__ import annotations

import logging
import queue
import threading
from typing import Any

logger = logging.getLogger(__name__)

_QUEUE_SIZE = 1000
_TIMEOUT_S = 2.0

_sync_queue: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=_QUEUE_SIZE)
_drain_started = False
_drain_lock = threading.Lock()
_bridge_url: str | None = None

_dropped = 0
_sent = 0
_failed = 0


def _get_url() -> str:
    global _bridge_url
    if _bridge_url is None:
        from neural_brain.config import get_settings
        _bridge_url = get_settings().node_bridge_url
    return _bridge_url


def _ensure_drain_started() -> None:
    global _drain_started
    if _drain_started:
        return
    with _drain_lock:
        if _drain_started:
            return
        t = threading.Thread(target=_drain_loop, daemon=True, name="nb_bridge_drain")
        t.start()
        _drain_started = True


def _drain_loop() -> None:
    global _sent, _failed
    try:
        import httpx
    except ImportError:
        logger.warning("httpx not installed; NodeBridge drain disabled")
        return

    url = _get_url()
    client = httpx.Client(timeout=_TIMEOUT_S)
    while True:
        try:
            evt = _sync_queue.get(block=True, timeout=5.0)
        except queue.Empty:
            continue
        try:
            resp = client.post(url, json=evt)
            if resp.status_code >= 400:
                _failed += 1
                logger.debug("nb_bridge non-2xx %s: %s", resp.status_code, resp.text[:200])
            else:
                _sent += 1
        except Exception as exc:
            _failed += 1
            logger.debug("nb_bridge_failed: %s", exc)


def emit(event: str, data: dict[str, Any] | None = None) -> None:
    """Fire-and-forget event push. Safe to call from any thread or asyncio context.

    Also publishes to the central SimpleMessageBus (notifications channel) so
    all runtime subsystems receive nb:* events without additional wiring.
    """
    global _dropped
    _ensure_drain_started()
    payload = {"event": event, "data": data or {}}
    try:
        _sync_queue.put_nowait(payload)
    except queue.Full:
        try:
            _sync_queue.get_nowait()  # drop oldest
            _dropped += 1
            _sync_queue.put_nowait(payload)
        except Exception:
            _dropped += 1

    # Publish to central bus (best-effort; never blocks the caller)
    try:
        from core.bus import get_message_bus
        get_message_bus().publish_sync("notifications", {"event": event, **(data or {})})
    except Exception:
        pass


# ── Compatibility shim: keep NodeBridge class for any code that imports it ──

class NodeBridge:
    """Thin wrapper kept for API compatibility. State lives in module globals."""

    def __init__(self, url: str | None = None, *, queue_size: int = _QUEUE_SIZE, timeout_seconds: float = _TIMEOUT_S) -> None:
        global _bridge_url
        if url is not None:
            _bridge_url = url

    def emit(self, event: str, data: dict[str, Any] | None = None) -> None:
        emit(event, data)

    def stats(self) -> dict[str, Any]:
        return {
            "url": _bridge_url,
            "queued": _sync_queue.qsize(),
            "sent": _sent,
            "failed": _failed,
            "dropped": _dropped,
        }

    async def aclose(self) -> None:
        pass  # Drain thread is a daemon; process exit handles cleanup.


_singleton: NodeBridge | None = None
_singleton_lock = threading.Lock()


def get_bridge(url: str | None = None) -> NodeBridge:
    """Return the process-wide NodeBridge singleton."""
    global _singleton
    if _singleton is None:
        with _singleton_lock:
            if _singleton is None:
                _singleton = NodeBridge(url)
    return _singleton
