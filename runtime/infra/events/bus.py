"""Enterprise Event Bus — Python adapter.

Transport stack (first available wins):
  1. NATS JetStream  — via nats-py (pip install nats-py)
  2. Redis Streams   — via redis-py (pip install redis)
  3. In-process      — wraps existing SimpleMessageBus (always available)

All three implement EventTransport so call-sites are transport-agnostic.
The existing SimpleMessageBus is still used for in-process pub/sub and
JSONL persistence so zero existing behaviour is broken.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import secrets
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, List, Optional

from core.bus import get_message_bus  # existing bus — preserved

logger = logging.getLogger("enterprise_event_bus")

SCHEMA_VERSION = "1"

# ── Event type registry (mirrors schema.js) ───────────────────────────────────

class E:
    AGENT_STARTED             = "agent:started"
    AGENT_COMPLETED           = "agent:completed"
    AGENT_FAILED              = "agent:failed"
    AGENT_PAUSED              = "agent:paused"
    AGENT_RESUMED             = "agent:resumed"
    TASK_SUBMITTED            = "task:submitted"
    TASK_PLANNED              = "task:planned"
    TASK_EXECUTING            = "task:executing"
    TASK_COMPLETED            = "task:completed"
    TASK_FAILED               = "task:failed"
    TASK_CANCELLED            = "task:cancelled"
    NB_REASONING_STEP         = "nb:reasoning_step"
    NB_MODEL_CALL             = "nb:model_call"
    NB_MEMORY_WRITE           = "nb:memory_write"
    NB_GRAPH_UPDATE           = "nb:graph_update"
    SYSTEM_READY              = "system:ready"
    SYSTEM_DEGRADED           = "system:degraded"
    SYSTEM_STATUS             = "system:status"
    SECURITY_ALERT            = "security:alert"
    AUDIT_RECORD              = "audit:record"
    EVOLUTION_PATCH_PROPOSED  = "evolution:patch_proposed"
    EVOLUTION_PATCH_APPLIED   = "evolution:patch_applied"
    DLQ_POISONED              = "dlq:poisoned"

EVENT_TYPES = E

# ── Envelope ──────────────────────────────────────────────────────────────────

@dataclass
class EventEnvelope:
    type: str
    payload: dict[str, Any]
    id: str = field(default_factory=lambda: secrets.token_hex(16))
    schema_version: str = SCHEMA_VERSION
    source: str = "python-backend"
    tenant_id: str = "system"
    trace_id: str = field(default_factory=lambda: secrets.token_hex(16))
    correlation_id: Optional[str] = None
    priority: int = 5
    ts: int = field(default_factory=lambda: int(time.time() * 1000))

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "EventEnvelope":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})

def build_event(
    type_: str,
    payload: dict,
    *,
    tenant_id: str = "system",
    trace_id: Optional[str] = None,
    correlation_id: Optional[str] = None,
    source: str = "python-backend",
    priority: int = 5,
) -> EventEnvelope:
    return EventEnvelope(
        type=type_,
        payload=payload,
        source=source,
        tenant_id=tenant_id,
        trace_id=trace_id or secrets.token_hex(16),
        correlation_id=correlation_id,
        priority=priority,
    )

# ── Transport abstract base ───────────────────────────────────────────────────

Handler = Callable[[EventEnvelope], Awaitable[None]]

class EventTransport(ABC):
    name: str = "abstract"

    @abstractmethod
    async def connect(self) -> bool: ...
    @abstractmethod
    async def publish(self, subject: str, envelope: EventEnvelope) -> bool: ...
    @abstractmethod
    async def subscribe(self, subject: str, handler: Handler): ...
    @abstractmethod
    async def close(self): ...
    @property
    def connected(self) -> bool: return False

# ── In-process transport (wraps existing SimpleMessageBus) ────────────────────

class InProcessTransport(EventTransport):
    name = "in-process"

    def __init__(self):
        self._bus = get_message_bus()
        self._handlers: dict[str, list[Handler]] = {}
        self._connected = True

    async def connect(self) -> bool: return True

    async def publish(self, subject: str, envelope: EventEnvelope) -> bool:
        channel = _subject_to_channel(subject)
        await self._bus.publish(channel, envelope.to_dict())
        # Fan-out to local subscribers immediately
        for h in list(self._handlers.get(subject, [])):
            try: await h(envelope)
            except Exception as e:
                logger.error("In-process handler error: %s", e)
        return True

    async def subscribe(self, subject: str, handler: Handler):
        self._handlers.setdefault(subject, []).append(handler)

    async def close(self): pass
    @property
    def connected(self) -> bool: return True

# ── NATS transport ────────────────────────────────────────────────────────────

class NatsTransport(EventTransport):
    name = "nats"

    def __init__(self, servers: str | None = None):
        self._servers = servers or os.environ.get("NATS_SERVERS", "nats://localhost:4222")
        self._nc = None
        self._js = None

    async def connect(self) -> bool:
        try:
            import nats as nats_lib
            self._nc = await nats_lib.connect(self._servers)
            self._js = self._nc.jetstream()
            logger.info("NATS JetStream connected")
            return True
        except Exception as e:
            logger.debug("NATS unavailable: %s", e)
            return False

    async def publish(self, subject: str, envelope: EventEnvelope) -> bool:
        if not self._js:
            return False
        data = json.dumps(envelope.to_dict()).encode()
        headers = {
            "trace-id": envelope.trace_id,
            "tenant-id": envelope.tenant_id,
            "event-type": envelope.type,
        }
        await self._js.publish(subject, data, headers=headers)
        return True

    async def subscribe(self, subject: str, handler: Handler):
        if not self._js:
            return
        async def _cb(msg):
            try:
                evt = EventEnvelope.from_dict(json.loads(msg.data.decode()))
                await handler(evt)
                await msg.ack()
            except Exception as e:
                logger.warning("NATS handler error: %s", e)
                await msg.nak()
        await self._js.subscribe(subject, cb=_cb, durable=f"aie-{subject.replace('.', '-')}")

    async def close(self):
        if self._nc:
            await self._nc.drain()

    @property
    def connected(self) -> bool:
        return self._nc is not None and not self._nc.is_closed

# ── Redis Streams transport ───────────────────────────────────────────────────

class RedisStreamsTransport(EventTransport):
    name = "redis-streams"

    def __init__(self, url: str | None = None):
        self._url = url or os.environ.get("REDIS_URL", "redis://localhost:6379")
        self._client = None

    async def connect(self) -> bool:
        try:
            import redis.asyncio as aioredis
            self._client = aioredis.from_url(self._url, decode_responses=True)
            await self._client.ping()
            logger.info("Redis Streams connected")
            return True
        except Exception as e:
            logger.debug("Redis unavailable: %s", e)
            return False

    async def publish(self, subject: str, envelope: EventEnvelope) -> bool:
        if not self._client:
            return False
        key = f"aie:events:{subject}"
        await self._client.xadd(key, {"data": json.dumps(envelope.to_dict())}, maxlen=50000, approximate=True)
        return True

    async def subscribe(self, subject: str, handler: Handler):
        if not self._client:
            return
        key = f"aie:events:{subject}"
        group = f"aie-py-{subject.replace('.', '-')}"
        consumer = f"worker-{os.getpid()}"
        try:
            await self._client.xgroup_create(key, group, "$", mkstream=True)
        except Exception:
            pass  # group already exists

        async def _read_loop():
            while True:
                try:
                    results = await self._client.xreadgroup(
                        group, consumer, {key: ">"}, count=20, block=2000
                    )
                    if results:
                        for _, msgs in results:
                            for msg_id, msg in msgs:
                                try:
                                    evt = EventEnvelope.from_dict(json.loads(msg["data"]))
                                    await handler(evt)
                                    await self._client.xack(key, group, msg_id)
                                except Exception as e:
                                    logger.warning("Redis handler error: %s", e)
                except Exception:
                    await asyncio.sleep(1)

        asyncio.create_task(_read_loop())

    async def close(self):
        if self._client:
            await self._client.aclose()

    @property
    def connected(self) -> bool:
        return self._client is not None

# ── Dead-letter queue ─────────────────────────────────────────────────────────

class DeadLetterQueue:
    def __init__(self, max_size: int = 10000):
        self._entries: list[dict] = []
        self._max = max_size

    def push(self, envelope: EventEnvelope, reason: str, retry_count: int):
        if len(self._entries) >= self._max:
            self._entries.pop(0)
        self._entries.append({
            "envelope": envelope.to_dict(),
            "reason": reason,
            "retry_count": retry_count,
            "dlq_ts": int(time.time() * 1000),
        })

    def peek(self, n: int = 50) -> list[dict]:
        return self._entries[-n:]

    @property
    def size(self) -> int:
        return len(self._entries)

# ── Main EventBus ─────────────────────────────────────────────────────────────

class EventBus:
    _MAX_RETRIES = 3
    _RETRY_BASE_MS = 0.25

    def __init__(self):
        self._primary: Optional[EventTransport] = None
        self._secondary: Optional[EventTransport] = None
        self._fallback = InProcessTransport()
        self._dlq = DeadLetterQueue()
        self._stats = {"published": 0, "delivered": 0, "dlq": 0, "errors": 0}
        self._ready = False

    async def init(self) -> "EventBus":
        nats_t  = NatsTransport()
        redis_t = RedisStreamsTransport()
        nats_ok, redis_ok = await asyncio.gather(nats_t.connect(), redis_t.connect())

        if nats_ok:  self._primary   = nats_t
        if redis_ok: self._secondary = redis_t

        if not nats_ok and not redis_ok:
            logger.warning("NATS + Redis unavailable — in-process transport only (non-durable)")

        self._ready = True
        return self

    async def publish(
        self,
        type_: str,
        payload: dict,
        *,
        tenant_id: str = "system",
        trace_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
        priority: int = 5,
    ) -> Optional[EventEnvelope]:
        envelope = build_event(type_, payload, tenant_id=tenant_id,
                               trace_id=trace_id, correlation_id=correlation_id,
                               priority=priority)
        subject = _make_subject(type_, tenant_id)

        if self._primary and self._primary.connected:
            try: await self._primary.publish(subject, envelope)
            except Exception as e: logger.warning("NATS publish failed: %s", e)

        if self._secondary and self._secondary.connected:
            try: await self._secondary.publish(subject, envelope)
            except Exception: pass

        # Always deliver in-process
        await self._fallback.publish(subject, envelope)

        self._stats["published"] += 1
        return envelope

    async def publish_reliable(self, type_: str, payload: dict, **kwargs) -> Optional[EventEnvelope]:
        last_err = None
        for attempt in range(self._MAX_RETRIES):
            try:
                result = await self.publish(type_, payload, **kwargs)
                if result: return result
            except Exception as e:
                last_err = e
                await asyncio.sleep(self._RETRY_BASE_MS * (2 ** attempt))
        # DLQ
        envelope = build_event(type_, payload, **{k: v for k, v in kwargs.items()
                                                   if k in ("tenant_id", "trace_id", "correlation_id", "priority")})
        self._dlq.push(envelope, str(last_err) or "publish failed", self._MAX_RETRIES)
        self._stats["dlq"] += 1
        logger.error("Event [%s] sent to DLQ after %d retries", type_, self._MAX_RETRIES)
        return None

    def subscribe(self, type_: str, handler: Handler, *, tenant_id: str = "*"):
        subject = _make_subject(type_, tenant_id)

        async def _wrapped(env: EventEnvelope):
            if tenant_id != "*" and env.tenant_id != tenant_id:
                return
            self._stats["delivered"] += 1
            try: await handler(env)
            except Exception as e: logger.error("Handler error: %s", e)

        asyncio.ensure_future(self._fallback.subscribe(subject, _wrapped))
        if self._primary and self._primary.connected:
            asyncio.ensure_future(self._primary.subscribe(subject, _wrapped))

    @property
    def dlq(self) -> DeadLetterQueue: return self._dlq
    @property
    def stats(self) -> dict: return dict(self._stats)
    @property
    def transports(self) -> dict:
        return {
            "primary":   self._primary.name   if self._primary   else "none",
            "secondary": self._secondary.name if self._secondary else "none",
            "fallback":  self._fallback.name,
        }

    async def close(self):
        if self._primary:   await self._primary.close()
        if self._secondary: await self._secondary.close()

# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_subject(type_: str, tenant_id: str) -> str:
    safe = type_.replace(":", ".")
    return f"aie.{tenant_id}.{safe}" if tenant_id and tenant_id != "*" else f"aie.{safe}"

def _subject_to_channel(subject: str) -> str:
    """Map NATS subject back to a SimpleMessageBus channel."""
    if "agent" in subject: return "notifications"
    if "task"  in subject: return "tasks"
    if "audit" in subject: return "logs"
    return "notifications"

# ── Singleton ─────────────────────────────────────────────────────────────────

_bus: Optional[EventBus] = None

async def get_event_bus() -> EventBus:
    global _bus
    if _bus is None:
        _bus = EventBus()
        await _bus.init()
    return _bus
