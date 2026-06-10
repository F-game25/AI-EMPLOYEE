"""TraceCollector — non-blocking trace capture for the live path.

LIVE-PATH GUARANTEE: ``start_trace``/``event``/``finalize`` only mutate in-memory
state (deque + dict) and return immediately. NO disk I/O, NO LLM, NO locks held
across I/O. A daemon background thread drains finalized traces to JSONL.

Persisted only on finalize (one scrubbed row per completed trace) at
``~/.ai-employee/evolution/traces/traces-YYYY-MM-DD.jsonl``.
"""
from __future__ import annotations

import threading
import time
import uuid
from collections import deque
from datetime import datetime, timezone
from typing import Any, Optional

from evolution import EVOLUTION_ENABLED, TRACES_DIR, ensure_dirs
from evolution.scrub import scrub


def _now_ms() -> float:
    return time.time() * 1000.0


def _iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class TraceCollector:
    """In-memory ring of live traces with a background JSONL flusher."""

    def __init__(self, *, max_active: int = 4096, flush_interval_s: float = 2.0):
        self._enabled = EVOLUTION_ENABLED
        self._active: dict[str, dict[str, Any]] = {}
        self._flush_q: deque[dict[str, Any]] = deque(maxlen=max_active)
        self._lock = threading.Lock()
        self._flush_interval_s = flush_interval_s
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        # observers receive finalized (in-memory) traces for offline processing.
        self._observers: list = []
        if self._enabled:
            self._start_flusher()

    # ── live path (must stay <5ms, no I/O) ───────────────────────────────────
    def start_trace(self, task_id: str, user_goal: str, task_type: str,
                    tenant_id: str = "") -> str:
        if not self._enabled:
            return ""
        trace_id = f"tr-{uuid.uuid4().hex[:16]}"
        rec = {
            "trace_id": trace_id,
            "tenant_id": tenant_id,
            "task_id": task_id,
            "user_goal": user_goal,
            "task_type": task_type,
            "started_at": _iso(),
            "_t0": _now_ms(),
            "events": [],
            "models_used": [],
            "tools_used": [],
            "errors": [],
            "outputs": [],
            "ended_at": None,
            "total_latency_ms": 0.0,
            "success": None,
            "quality_score": None,
        }
        with self._lock:
            self._active[trace_id] = rec
        return trace_id

    def event(self, trace_id: str, phase: str, payload: dict[str, Any] | None = None) -> None:
        """Append-only event. NON-BLOCKING — pure in-memory append."""
        if not self._enabled or not trace_id:
            return
        rec = self._active.get(trace_id)
        if rec is None:
            return
        ev = {"phase": phase, "t_ms": _now_ms() - rec["_t0"], "payload": payload or {}}
        # No lock: list.append is atomic under CPython GIL; this path is hot.
        rec["events"].append(ev)
        p = payload or {}
        if (m := p.get("model")):
            rec["models_used"].append(m)
        if (tool := p.get("tool")):
            rec["tools_used"].append(tool)
        if (err := p.get("error")):
            rec["errors"].append({"phase": phase, "error": err})

    def finalize(self, trace_id: str, outputs: list | None = None,
                 success: bool = True, quality_score: float | None = None) -> dict[str, Any] | None:
        if not self._enabled or not trace_id:
            return None
        with self._lock:
            rec = self._active.pop(trace_id, None)
        if rec is None:
            return None
        rec["ended_at"] = _iso()
        rec["total_latency_ms"] = _now_ms() - rec.pop("_t0")
        rec["outputs"] = outputs or []
        rec["success"] = bool(success)
        rec["quality_score"] = quality_score
        rec["models_used"] = sorted(set(rec["models_used"]))
        rec["tools_used"] = sorted(set(rec["tools_used"]))
        # Hand off to the background flusher; never block the caller on disk.
        self._flush_q.append(rec)
        for obs in tuple(self._observers):
            try:
                obs(rec)
            except Exception:  # observers must never break the live path
                pass
        return rec

    # ── observers (offline consumers, e.g. EvolutionController) ───────────────
    def add_observer(self, fn) -> None:
        self._observers.append(fn)

    # ── background flush (off the live path) ─────────────────────────────────
    def _start_flusher(self) -> None:
        self._thread = threading.Thread(
            target=self._flush_loop, name="evolution-trace-flush", daemon=True)
        self._thread.start()

    def _flush_loop(self) -> None:
        while not self._stop.wait(self._flush_interval_s):
            self._drain()

    def _drain(self) -> int:
        n = 0
        batch: list[dict[str, Any]] = []
        while self._flush_q:
            try:
                batch.append(self._flush_q.popleft())
            except IndexError:
                break
        if not batch:
            return 0
        ensure_dirs()
        import json
        path = TRACES_DIR / f"traces-{datetime.now(timezone.utc):%Y-%m-%d}.jsonl"
        with open(path, "a", encoding="utf-8") as fh:
            for rec in batch:
                fh.write(json.dumps(scrub(rec), ensure_ascii=False) + "\n")
                n += 1
        return n

    def flush_now(self) -> int:
        """Synchronously drain pending traces (tests / shutdown)."""
        return self._drain()

    def stop(self) -> None:
        self._stop.set()
        self._drain()


_singleton: Optional[TraceCollector] = None
_singleton_lock = threading.Lock()


def get_trace_collector() -> TraceCollector:
    global _singleton
    if _singleton is None:
        with _singleton_lock:
            if _singleton is None:
                _singleton = TraceCollector()
    return _singleton


__all__ = ["TraceCollector", "get_trace_collector"]
