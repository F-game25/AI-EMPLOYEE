"""Canonical typed event bus for AETERNUS NEXUS.

Every module in the system publishes and subscribes through this single layer.
No other inter-module communication is allowed.

Event contract (enforced at publish time):
    {
        "type":      str,              # e.g. "nb:reasoning_step"
        "source":    str,              # "neural_brain"|"agent"|"forge"|"system"|"blacklight"
        "payload":   dict,
        "timestamp": float,            # unix epoch ms
        "trace_id":  str,              # uuid for distributed tracing
    }

Features:
- Thread-safe pub/sub with per-subscriber queues
- Bounded buffer (drop-oldest) per subscriber
- Background drain thread → NodeBridge (WebSocket) + SimpleMessageBus
- Retry with exponential backoff for bridge delivery
- Drop detection counter
"""
from __future__ import annotations

import logging
import queue
import threading
import time
import uuid
from collections import defaultdict
from typing import Any, Callable

logger = logging.getLogger(__name__)

VALID_SOURCES = frozenset({"neural_brain", "agent", "forge", "system", "blacklight"})

_QUEUE_MAXSIZE = 500
_DRAIN_TIMEOUT = 5.0
_BRIDGE_RETRY_MAX = 3
_BRIDGE_RETRY_BACKOFF = 0.2


class Event(dict):
    """Typed event dict with validation."""

    REQUIRED = ("type", "source", "payload", "timestamp", "trace_id")

    @classmethod
    def create(cls, type: str, source: str, payload: dict | None = None, trace_id: str | None = None) -> "Event":
        if source not in VALID_SOURCES:
            source = "system"
        e = cls({
            "type": type,
            "source": source,
            "payload": payload or {},
            "timestamp": time.time() * 1000,
            "trace_id": trace_id or str(uuid.uuid4()),
        })
        return e

    def validate(self) -> bool:
        return all(k in self for k in self.REQUIRED)


class EventBus:
    """Process-wide event bus.

    Usage:
        bus = get_event_bus()
        bus.subscribe("nb:reasoning_step", my_handler)   # handler(event: Event)
        bus.publish("nb:reasoning_step", source="neural_brain", payload={...})
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        # event_type → list of (handler_fn, subscriber_queue)
        self._subscribers: dict[str, list[tuple[Callable, queue.Queue]]] = defaultdict(list)
        # wildcard subscribers receive ALL events
        self._wildcard: list[tuple[Callable, queue.Queue]] = []
        self._drop_count = 0
        self._publish_count = 0
        self._drain_started = False
        self._drain_lock = threading.Lock()
        # outbound queue → NodeBridge + bus
        self._outbound: queue.Queue[Event] = queue.Queue(maxsize=2000)

    # ── Publish ──────────────────────────────────────────────────────────

    def publish(
        self,
        type: str,
        *,
        source: str = "system",
        payload: dict | None = None,
        trace_id: str | None = None,
    ) -> Event:
        """Publish a typed event. Non-blocking. Returns the created Event."""
        event = Event.create(type=type, source=source, payload=payload, trace_id=trace_id)
        self._dispatch(event)
        self._ensure_drain_started()
        try:
            self._outbound.put_nowait(event)
        except queue.Full:
            self._outbound.get_nowait()
            self._drop_count += 1
            self._outbound.put_nowait(event)
        self._publish_count += 1
        return event

    def publish_event(self, event: Event) -> None:
        """Publish a pre-built Event object."""
        if not event.validate():
            logger.warning("EventBus: invalid event dropped: %s", event)
            return
        self._dispatch(event)
        self._ensure_drain_started()
        try:
            self._outbound.put_nowait(event)
        except queue.Full:
            self._outbound.get_nowait()
            self._drop_count += 1
            self._outbound.put_nowait(event)
        self._publish_count += 1

    # ── Subscribe ────────────────────────────────────────────────────────

    def subscribe(self, event_type: str | None, handler: Callable[[Event], None]) -> None:
        """Register a handler for event_type. Use None for wildcard (all events)."""
        q: queue.Queue = queue.Queue(maxsize=_QUEUE_MAXSIZE)
        with self._lock:
            if event_type is None:
                self._wildcard.append((handler, q))
            else:
                self._subscribers[event_type].append((handler, q))
        # Start a delivery thread for this subscriber
        t = threading.Thread(
            target=self._deliver_loop,
            args=(handler, q),
            daemon=True,
            name=f"eb_deliver_{event_type or 'wildcard'}",
        )
        t.start()

    # ── Internal dispatch ─────────────────────────────────────────────────

    def _dispatch(self, event: Event) -> None:
        with self._lock:
            targets = list(self._subscribers.get(event["type"], []))
            targets += list(self._wildcard)
        for _, q in targets:
            try:
                q.put_nowait(event)
            except queue.Full:
                q.get_nowait()
                self._drop_count += 1
                q.put_nowait(event)

    def _deliver_loop(self, handler: Callable, q: queue.Queue) -> None:
        while True:
            try:
                event = q.get(block=True, timeout=_DRAIN_TIMEOUT)
                try:
                    handler(event)
                except Exception as e:
                    logger.debug("EventBus handler error: %s", e)
            except queue.Empty:
                continue

    # ── Outbound drain → NodeBridge + SimpleMessageBus ───────────────────

    def _ensure_drain_started(self) -> None:
        if self._drain_started:
            return
        with self._drain_lock:
            if self._drain_started:
                return
            t = threading.Thread(target=self._drain_loop, daemon=True, name="eb_drain")
            t.start()
            self._drain_started = True

    def _drain_loop(self) -> None:
        while True:
            try:
                event = self._outbound.get(block=True, timeout=_DRAIN_TIMEOUT)
            except queue.Empty:
                continue
            self._forward_to_bridge(event)
            self._forward_to_bus(event)

    def _forward_to_bridge(self, event: Event) -> None:
        """Forward to Node WebSocket via NodeBridge (with retry)."""
        for attempt in range(_BRIDGE_RETRY_MAX):
            try:
                from neural_brain.api.node_bridge import emit as _nb_emit
                _nb_emit(event["type"], event["payload"])
                return
            except Exception as e:
                if attempt < _BRIDGE_RETRY_MAX - 1:
                    time.sleep(_BRIDGE_RETRY_BACKOFF * (2 ** attempt))
                else:
                    logger.debug("EventBus bridge forward failed after retries: %s", e)

    def _forward_to_bus(self, event: Event) -> None:
        """Forward to SimpleMessageBus notifications channel."""
        try:
            from core.bus import get_message_bus
            get_message_bus().publish_sync("notifications", {
                "event": event["type"],
                "source": event["source"],
                **event["payload"],
            })
        except Exception:
            pass

    # ── Stats ─────────────────────────────────────────────────────────────

    def stats(self) -> dict:
        return {
            "published": self._publish_count,
            "dropped": self._drop_count,
            "outbound_queue_size": self._outbound.qsize(),
        }


# ── Process-wide singleton ────────────────────────────────────────────────────

_bus_instance: EventBus | None = None
_bus_lock = threading.Lock()


def get_event_bus() -> EventBus:
    global _bus_instance
    if _bus_instance is None:
        with _bus_lock:
            if _bus_instance is None:
                _bus_instance = EventBus()
    return _bus_instance


# Convenience shorthand
def publish(type: str, *, source: str = "system", payload: dict | None = None, trace_id: str | None = None) -> Event:
    return get_event_bus().publish(type, source=source, payload=payload, trace_id=trace_id)


def subscribe(event_type: str | None, handler: Callable[[Event], None]) -> None:
    get_event_bus().subscribe(event_type, handler)
