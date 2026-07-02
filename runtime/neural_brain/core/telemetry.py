"""Telemetry — structured event log for all user actions, errors, agent events, security.

All telemetry is:
  - Written to state/telemetry.jsonl (append-only)
  - In-memory ring buffer (last 10 000 events)
  - Queryable by category, user, time range
  - Accessible via admin API
"""
from __future__ import annotations

import logging
import os
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, asdict
from enum import Enum
from pathlib import Path
from typing import Any

from core.state_paths import canonical_state_dir
from core import rotating_jsonl

logger = logging.getLogger(__name__)

_BUFFER_SIZE = 10_000
# Canonical state tree (honours STATE_DIR / AI_HOME). Was relative Path("state/…")
# which resolved to CWD-relative ./state — repo-local split-brain (134MB stray log).
# See docs/SYSTEM_COHERENCE_PLAN.md C0.
_LOG_PATH = canonical_state_dir() / "telemetry.jsonl"


class TelemetryCategory(str, Enum):
    USER_ACTION = "user_action"
    SECURITY = "security"
    AGENT = "agent"
    FORGE = "forge"
    ERROR = "error"
    PERFORMANCE = "performance"
    AUTH = "auth"
    SYSTEM = "system"


@dataclass
class TelemetryRecord:
    id: str
    ts: float
    category: str
    event_type: str
    user_id: str
    source: str
    payload: dict
    duration_ms: float | None = None
    trace_id: str | None = None
    error: str | None = None


class TelemetryLogger:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._buffer: deque[TelemetryRecord] = deque(maxlen=_BUFFER_SIZE)
        self._file_lock = threading.Lock()
        self._writer_thread = threading.Thread(target=self._drain_loop, daemon=True, name="telemetry_drain")
        self._write_queue: deque[TelemetryRecord] = deque()
        self._running = True
        _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        self._writer_thread.start()
        # Subscribe to all events for auto-capture
        self._subscribe()
        logger.info("TelemetryLogger started — log: %s", _LOG_PATH)

    # ── Public API ────────────────────────────────────────────────────────────

    def log(
        self,
        *,
        category: TelemetryCategory | str,
        event_type: str,
        user_id: str = "system",
        source: str = "system",
        payload: dict | None = None,
        duration_ms: float | None = None,
        trace_id: str | None = None,
        error: str | None = None,
    ) -> str:
        record = TelemetryRecord(
            id=str(uuid.uuid4()),
            ts=time.time(),
            category=str(category),
            event_type=event_type,
            user_id=user_id,
            source=source,
            payload=payload or {},
            duration_ms=duration_ms,
            trace_id=trace_id,
            error=error,
        )
        with self._lock:
            self._buffer.append(record)
        with self._file_lock:
            self._write_queue.append(record)
        return record.id

    def query(
        self,
        *,
        category: str | None = None,
        event_type: str | None = None,
        user_id: str | None = None,
        since_ts: float | None = None,
        limit: int = 200,
        errors_only: bool = False,
    ) -> list[dict]:
        with self._lock:
            records = list(self._buffer)

        if since_ts:
            records = [r for r in records if r.ts >= since_ts]
        if category:
            records = [r for r in records if r.category == category]
        if event_type:
            records = [r for r in records if r.event_type == event_type]
        if user_id:
            records = [r for r in records if r.user_id == user_id]
        if errors_only:
            records = [r for r in records if r.error or r.category == TelemetryCategory.ERROR]

        return [asdict(r) for r in records[-limit:]]

    def get_summary(self, window_s: float = 3600) -> dict:
        cutoff = time.time() - window_s
        with self._lock:
            recent = [r for r in self._buffer if r.ts >= cutoff]

        by_category: dict[str, int] = {}
        errors = 0
        for r in recent:
            by_category[r.category] = by_category.get(r.category, 0) + 1
            if r.error or r.category == TelemetryCategory.ERROR:
                errors += 1

        avg_latency = None
        perf = [r.duration_ms for r in recent if r.duration_ms is not None]
        if perf:
            avg_latency = sum(perf) / len(perf)

        return {
            "window_s": window_s,
            "total_events": len(recent),
            "errors": errors,
            "error_rate": round(errors / max(len(recent), 1), 4),
            "by_category": by_category,
            "avg_latency_ms": round(avg_latency, 1) if avg_latency else None,
        }

    def get_top_errors(self, limit: int = 20) -> list[dict]:
        with self._lock:
            error_records = [r for r in self._buffer if r.error or r.category == TelemetryCategory.ERROR]
        by_type: dict[str, dict] = {}
        for r in error_records:
            key = r.event_type
            if key not in by_type:
                by_type[key] = {"event_type": key, "count": 0, "last_error": "", "last_ts": 0}
            by_type[key]["count"] += 1
            by_type[key]["last_error"] = r.error or ""
            by_type[key]["last_ts"] = max(by_type[key]["last_ts"], r.ts)
        return sorted(by_type.values(), key=lambda x: x["count"], reverse=True)[:limit]

    # ── Event bus auto-capture ────────────────────────────────────────────────

    def _subscribe(self) -> None:
        try:
            from neural_brain.utils.event_bus import subscribe
            subscribe(None, self._on_event)  # wildcard
        except Exception as e:
            logger.debug("Telemetry: event bus subscribe failed: %s", e)

    def _on_event(self, event: dict) -> None:
        event_type = event.get("type", "unknown")
        source = event.get("source", "system")
        payload = event.get("payload", {})
        user_id = payload.get("user_id", "system")

        category = self._categorize(event_type)
        error = payload.get("error") if "error" in payload else None

        self.log(
            category=category,
            event_type=event_type,
            user_id=user_id,
            source=source,
            payload={k: v for k, v in payload.items() if k not in ("password", "token", "secret")},
            error=error,
            trace_id=event.get("trace_id"),
        )

    @staticmethod
    def _categorize(event_type: str) -> str:
        if event_type.startswith("auth:") or event_type.startswith("security:"):
            return TelemetryCategory.SECURITY
        if event_type.startswith("agent:"):
            return TelemetryCategory.AGENT
        if event_type.startswith("nb:forge") or event_type.startswith("forge:"):
            return TelemetryCategory.FORGE
        if event_type.startswith("system:error") or event_type.startswith("system:degraded"):
            return TelemetryCategory.ERROR
        if event_type.startswith("blacklight:"):
            return TelemetryCategory.SECURITY
        return TelemetryCategory.SYSTEM

    # ── File drain ────────────────────────────────────────────────────────────

    def _drain_loop(self) -> None:
        while self._running:
            time.sleep(2)
            self._flush()

    def _flush(self) -> None:
        with self._file_lock:
            if not self._write_queue:
                return
            records = list(self._write_queue)
            self._write_queue.clear()
        try:
            # Size-bounded batch append (C0 disk-growth backlog): the file is
            # otherwise unbounded — a stray copy reached 134MB. One size check +
            # rotation per drain batch keeps disk capped on the hot path.
            rotating_jsonl.append_many(_LOG_PATH, (asdict(r) for r in records))
        except Exception as e:
            logger.warning("Telemetry write error: %s", e)


# ── Singleton ─────────────────────────────────────────────────────────────────
_telemetry: TelemetryLogger | None = None
_lock = threading.Lock()


def get_telemetry() -> TelemetryLogger:
    global _telemetry
    if _telemetry is None:
        with _lock:
            if _telemetry is None:
                _telemetry = TelemetryLogger()
    return _telemetry


def log(*, category: TelemetryCategory | str, event_type: str, **kwargs) -> str:
    return get_telemetry().log(category=category, event_type=event_type, **kwargs)
