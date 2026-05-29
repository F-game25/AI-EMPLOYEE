"""Privacy-safe telemetry — no PII, no content, only operational metrics."""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import threading
import time
import uuid
from collections import deque
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

logger = logging.getLogger("ai_employee.telemetry")

_SKIP_PATHS = {"/health", "/metrics", "/api/status"}

_STATE_DIR = Path(os.environ.get("AI_HOME", Path.home() / ".ai-employee")) / "state"

# ── HMAC helper ────────────────────────────────────────────────────────────────

def hash_tenant_id(tenant_id: str) -> str:
    """HMAC-SHA256 pseudonymisation — consistent but not reversible."""
    key = os.environ.get("TELEMETRY_HMAC_KEY", "telemetry-v1").encode()
    return hmac.new(key, tenant_id.encode(), hashlib.sha256).hexdigest()[:16]


# ── Event dataclass ────────────────────────────────────────────────────────────

@dataclass
class TelemetryEvent:
    request_id: str
    tenant_id_hash: str
    route_name: str
    method: str
    status_code: int
    latency_ms: float
    token_count: int = 0
    cost_usd_estimate: float = 0.0
    error_type: str = ""
    ts: str = ""

    def __post_init__(self):
        if not self.ts:
            self.ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ── Collector ──────────────────────────────────────────────────────────────────

class TelemetryCollector:
    def __init__(self, maxlen: int = 10_000) -> None:
        self._lock = threading.Lock()
        self._events: deque[TelemetryEvent] = deque(maxlen=maxlen)
        self._jsonl_path: Optional[Path] = None
        self._init_storage()

    def _init_storage(self) -> None:
        try:
            _STATE_DIR.mkdir(parents=True, exist_ok=True)
            self._jsonl_path = _STATE_DIR / "telemetry.jsonl"
        except Exception as exc:
            logger.warning("Telemetry storage init failed: %s", exc)

    def record(self, event: TelemetryEvent) -> None:
        with self._lock:
            self._events.append(event)
            if self._jsonl_path:
                try:
                    with self._jsonl_path.open("a") as fh:
                        fh.write(json.dumps(asdict(event)) + "\n")
                except Exception as exc:
                    logger.debug("Telemetry write failed: %s", exc)

    def update_tokens(self, request_id: str, tokens: int, cost: float) -> None:
        """Back-fill token/cost on the most recent matching event."""
        with self._lock:
            for evt in reversed(self._events):
                if evt.request_id == request_id:
                    evt.token_count = tokens
                    evt.cost_usd_estimate = cost
                    return

    def get_summary(self, window_minutes: int = 60) -> dict:
        cutoff_ts = time.time() - window_minutes * 60
        with self._lock:
            window = [
                e for e in self._events
                if _parse_ts(e.ts) >= cutoff_ts
            ]

        if not window:
            return {
                "total_requests": 0,
                "error_rate": 0.0,
                "avg_latency_ms": 0.0,
                "p95_latency_ms": 0.0,
                "total_tokens": 0,
                "total_cost_usd": 0.0,
                "top_routes": [],
            }

        latencies = sorted(e.latency_ms for e in window)
        errors = sum(1 for e in window if e.status_code >= 400)
        p95_idx = max(0, int(len(latencies) * 0.95) - 1)

        route_counts: dict[str, int] = {}
        for e in window:
            route_counts[e.route_name] = route_counts.get(e.route_name, 0) + 1
        top_routes = sorted(
            [{"route": r, "count": c} for r, c in route_counts.items()],
            key=lambda x: x["count"],
            reverse=True,
        )[:10]

        return {
            "total_requests": len(window),
            "error_rate": round(errors / len(window), 4),
            "avg_latency_ms": round(sum(latencies) / len(latencies), 2),
            "p95_latency_ms": round(latencies[p95_idx], 2),
            "total_tokens": sum(e.token_count for e in window),
            "total_cost_usd": round(sum(e.cost_usd_estimate for e in window), 6),
            "top_routes": top_routes,
        }


def _parse_ts(ts: str) -> float:
    """ISO8601 UTC string → epoch float, best-effort."""
    try:
        dt = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except Exception:
        return 0.0


# ── Singleton ──────────────────────────────────────────────────────────────────

_collector: Optional[TelemetryCollector] = None
_collector_lock = threading.Lock()


def get_collector() -> TelemetryCollector:
    global _collector
    with _collector_lock:
        if _collector is None:
            _collector = TelemetryCollector()
    return _collector


# ── Starlette middleware ───────────────────────────────────────────────────────

class PrivacyTelemetryMiddleware(BaseHTTPMiddleware):
    """Records per-request operational metrics — zero user content captured."""

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if path in _SKIP_PATHS:
            return await call_next(request)

        # Generate or reuse request_id
        if not getattr(request.state, "request_id", None):
            request.state.request_id = uuid.uuid4().hex[:12]
        req_id = request.state.request_id

        # Pseudonymise tenant
        raw_tenant = getattr(request.state, "tenant_id", "") or ""
        tenant_hash = hash_tenant_id(raw_tenant) if raw_tenant else "anonymous"

        t0 = time.monotonic()
        status_code = 500
        error_type = ""
        try:
            response = await call_next(request)
            status_code = response.status_code
            if status_code >= 400:
                error_type = f"http_{status_code}"
            return response
        except Exception as exc:
            error_type = type(exc).__name__
            raise
        finally:
            latency_ms = round((time.monotonic() - t0) * 1000, 2)
            get_collector().record(TelemetryEvent(
                request_id=req_id,
                tenant_id_hash=tenant_hash,
                route_name=path,
                method=request.method,
                status_code=status_code,
                latency_ms=latency_ms,
                error_type=error_type,
            ))
