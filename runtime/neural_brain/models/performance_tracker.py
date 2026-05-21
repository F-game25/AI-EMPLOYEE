"""Per-architecture model performance tracker.

Tracks latency and error rates in a thread-safe rolling window,
and ranks candidate models by a composite score for adaptive routing.
"""
from __future__ import annotations

import threading
from collections import deque
from typing import Any

_COST_MAP = {
    "ollama": 0.0,
    "openrouter": 0.5,
    "anthropic": 1.0,
    "sentence-transformers": 0.0,
    "runtime": 0.0,
}

_MAX_LATENCY_MS = 10_000.0
_WINDOW = 100


def _provider_cost(provider: str) -> float:
    for key, cost in _COST_MAP.items():
        if key in (provider or "").lower():
            return cost
    return 0.5


class ModelPerformanceTracker:
    """Thread-safe rolling performance stats per (arch, provider) key."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # key → deque of {"latency_ms": float, "ok": bool}
        self._windows: dict[str, deque[dict[str, Any]]] = {}

    def _key(self, arch: str, provider: str = "") -> str:
        return f"{arch}:{provider or 'unknown'}"

    def record(self, arch: str, provider: str, model: str, latency_ms: float, status: str) -> None:
        ok = status not in ("error", "failed", "timeout")
        key = self._key(arch, provider)
        with self._lock:
            if key not in self._windows:
                self._windows[key] = deque(maxlen=_WINDOW)
            self._windows[key].append({"latency_ms": latency_ms, "ok": ok})

    def get_stats(self, arch: str, provider: str = "") -> dict[str, Any]:
        key = self._key(arch, provider)
        with self._lock:
            window = list(self._windows.get(key, []))
        if not window:
            return {"avg_latency_ms": 0, "error_rate": 0.0, "call_count": 0}
        call_count = len(window)
        avg_latency = sum(e["latency_ms"] for e in window) / call_count
        error_rate = sum(1 for e in window if not e["ok"]) / call_count
        return {
            "avg_latency_ms": round(avg_latency, 1),
            "error_rate": round(error_rate, 3),
            "call_count": call_count,
        }

    def get_all_stats(self, arch: str) -> dict[str, Any]:
        """Aggregate stats across all providers for the given arch."""
        with self._lock:
            matching = {k: list(v) for k, v in self._windows.items() if k.startswith(f"{arch}:")}
        if not matching:
            return {"avg_latency_ms": 0, "error_rate": 0.0, "call_count": 0}
        all_entries = [e for entries in matching.values() for e in entries]
        if not all_entries:
            return {"avg_latency_ms": 0, "error_rate": 0.0, "call_count": 0}
        n = len(all_entries)
        return {
            "avg_latency_ms": round(sum(e["latency_ms"] for e in all_entries) / n, 1),
            "error_rate": round(sum(1 for e in all_entries if not e["ok"]) / n, 3),
            "call_count": n,
        }

    def score(self, arch: str, provider: str) -> float:
        """Composite score in [0,1] — higher is better."""
        stats = self.get_stats(arch, provider)
        norm_latency = min(1.0, stats["avg_latency_ms"] / _MAX_LATENCY_MS)
        norm_cost = _provider_cost(provider)
        accuracy_proxy = 1.0 - stats["error_rate"]
        return 0.5 * accuracy_proxy + 0.3 * (1.0 - norm_latency) + 0.2 * (1.0 - norm_cost)

    def rank_options(self, arch: str, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Return candidates sorted by composite score (best first).

        Each candidate dict must have at least a "provider" key.
        New/unseen candidates get a neutral score of 0.5 so they're
        tried before known-bad ones.
        """
        def _cand_score(c: dict[str, Any]) -> float:
            provider = c.get("provider", "")
            stats = self.get_stats(arch, provider)
            if stats["call_count"] == 0:
                return 0.5  # neutral for unseen candidates
            return self.score(arch, provider)

        return sorted(candidates, key=_cand_score, reverse=True)


_singleton: ModelPerformanceTracker | None = None
_singleton_lock = threading.Lock()


def get_tracker() -> ModelPerformanceTracker:
    global _singleton
    if _singleton is None:
        with _singleton_lock:
            if _singleton is None:
                _singleton = ModelPerformanceTracker()
    return _singleton
