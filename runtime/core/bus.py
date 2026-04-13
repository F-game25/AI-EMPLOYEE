from __future__ import annotations

import asyncio
import json
import os
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any


class SimpleMessageBus:
    """Lightweight in-process message bus with persistent JSONL history."""

    CHANNELS = ("tasks", "results", "notifications", "logs")

    def __init__(self, state_dir: Path | None = None, max_lines: int = 10_000) -> None:
        self._state_dir = state_dir or Path(os.environ.get("AI_EMPLOYEE_STATE_DIR", "state"))
        self._state_dir.mkdir(parents=True, exist_ok=True)
        self._path = self._state_dir / "bus.jsonl"
        self._max_lines = max_lines
        self._queues: dict[str, list[asyncio.Queue]] = {ch: [] for ch in self.CHANNELS}
        self._lock = Lock()

    async def publish(self, channel: str, message: dict[str, Any]) -> dict[str, Any]:
        if channel not in self._queues:
            raise ValueError(f"Unknown channel: {channel}")
        envelope = {
            "channel": channel,
            "message": message,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        with self._lock:
            self._persist(envelope)
        for queue in self._queues[channel]:
            await queue.put(envelope)
        return envelope

    async def subscribe(self, channel: str) -> asyncio.Queue:
        if channel not in self._queues:
            raise ValueError(f"Unknown channel: {channel}")
        queue: asyncio.Queue = asyncio.Queue()
        self._queues[channel].append(queue)
        return queue

    def publish_sync(self, channel: str, message: dict[str, Any]) -> dict[str, Any]:
        return asyncio.run(self.publish(channel, message))

    def _persist(self, envelope: dict[str, Any]) -> None:
        lines = deque(maxlen=self._max_lines)
        if self._path.exists():
            for line in self._path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    lines.append(line)
        lines.append(json.dumps(envelope, ensure_ascii=False))
        self._path.write_text("\n".join(lines) + "\n", encoding="utf-8")


_bus_instance: SimpleMessageBus | None = None


def get_message_bus() -> SimpleMessageBus:
    global _bus_instance
    if _bus_instance is None:
        _bus_instance = SimpleMessageBus()
    return _bus_instance
