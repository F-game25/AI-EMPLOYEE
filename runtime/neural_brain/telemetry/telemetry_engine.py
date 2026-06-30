"""Telemetry Engine — local-first, privacy-preserving metric collection.

Architecture:
  1. Subscribe to ALL system events via EventBus (wildcard)
  2. Each event → Sanitizer.sanitize_event() → if not None → ring buffer
  3. Every 24h (configurable): bundle → sign with KeyManager → export if CONNECTED
  4. Export is fire-and-forget with timeout; failure is silent (never blocks user)
  5. Local stats always available via get_stats() regardless of export setting

What is collected (sanitized metadata only):
  - error_type counts by category
  - model call latency + success rate per arch
  - agent failure counts
  - forge failure counts
  - system bottleneck events (degraded/recovered)
  - security event counts (no content)

What is NEVER collected:
  - User prompts, responses, memory content
  - User IDs (replaced with anon tokens)
  - IP addresses
  - File paths or usernames
  - Any text string longer than 64 chars
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import struct
import threading
import time
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

from core.state_paths import canonical_state_dir

logger = logging.getLogger(__name__)

_BUNDLE_INTERVAL_S  = int(os.getenv("TELEMETRY_BUNDLE_INTERVAL_S", str(24 * 3600)))  # 24h
_EXPORT_TIMEOUT_S   = int(os.getenv("TELEMETRY_EXPORT_TIMEOUT_S", "10"))
_BUFFER_SIZE        = 50_000
_MAX_BUNDLE_EVENTS  = int(os.getenv("TELEMETRY_MAX_BUNDLE_EVENTS", "10000"))  # cap per bundle
_SAMPLE_RATE_NORMAL = 1.0    # 100% capture when load is low
_SAMPLE_RATE_HIGH   = 0.25   # 25% capture when buffer > 80% full
_SAMPLE_THRESHOLD   = int(_BUFFER_SIZE * 0.8)
_SCHEMA_VERSION     = "2.0"
# Canonical state tree (honours STATE_DIR / AI_HOME) — not repo-local ./state. C0.
_TELEMETRY_DIR      = canonical_state_dir() / "telemetry"
_BUNDLE_DIR         = _TELEMETRY_DIR / "bundles"
_STATS_PATH         = _TELEMETRY_DIR / "local_stats.json"
_NONCE_PATH         = _TELEMETRY_DIR / ".nonce_counter"


@dataclass
class MetricEvent:
    event_type: str
    source: str
    payload: dict
    ts_bucket: int   # hour-granularity timestamp
    frequency: int = 1  # how many raw events this represents (after sampling)


class TelemetryEngine:
    """Collects local metrics, bundles them, optionally exports anonymised bundles."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._buffer: deque[MetricEvent] = deque(maxlen=_BUFFER_SIZE)
        self._counters: dict[str, int] = defaultdict(int)
        self._freq_buckets: dict[str, dict[int, int]] = defaultdict(lambda: defaultdict(int))  # event_type → hour_bucket → count
        self._latencies: dict[str, list[float]] = defaultdict(list)  # arch → [ms]
        self._error_counts: dict[str, int] = defaultdict(int)
        self._sample_count = 0
        self._drop_count = 0
        self._running = True
        self._last_bundle_ts = time.time()
        self._nonce = self._load_nonce()
        self._system_id = self._get_or_create_system_id()
        _BUNDLE_DIR.mkdir(parents=True, exist_ok=True)
        _STATS_PATH.parent.mkdir(parents=True, exist_ok=True)
        self._subscribe()
        self._bundle_thread = threading.Thread(
            target=self._bundle_loop, daemon=True, name="telemetry_bundle"
        )
        self._bundle_thread.start()
        logger.info("TelemetryEngine started — system_id=%s… schema=%s", self._system_id[:8], _SCHEMA_VERSION)

    # ── Event ingestion ───────────────────────────────────────────────────────

    def _subscribe(self) -> None:
        try:
            from neural_brain.utils.event_bus import subscribe
            subscribe(None, self._on_event)
        except Exception as e:
            logger.debug("TelemetryEngine subscribe failed: %s", e)

    def _on_event(self, event: dict) -> None:
        """Called for every system event. Must be non-blocking."""
        from neural_brain.telemetry.sanitizer import get_sanitizer
        sanitized = get_sanitizer().sanitize_event(event)
        if sanitized is None:
            return

        # Load-shedding: sample under high buffer pressure
        with self._lock:
            buf_size = len(self._buffer)
        import random as _rnd
        sample_rate = _SAMPLE_RATE_HIGH if buf_size >= _SAMPLE_THRESHOLD else _SAMPLE_RATE_NORMAL
        if _rnd.random() > sample_rate:
            with self._lock:
                self._drop_count += 1
            return

        me = MetricEvent(
            event_type=sanitized["event_type"],
            source=sanitized["source"],
            payload=sanitized["payload"],
            ts_bucket=sanitized["ts_bucket"],
            frequency=max(1, round(1.0 / sample_rate)) if sample_rate < 1.0 else 1,
        )
        with self._lock:
            self._buffer.append(me)
            self._sample_count += 1
            self._counters[me.event_type] += 1
            # Frequency tracking per hour bucket
            self._freq_buckets[me.event_type][me.ts_bucket] += 1
            # Track latency per arch for model calls
            if me.event_type == "nb:model_call":
                arch = me.payload.get("arch", "unknown")
                lat = me.payload.get("latency_ms")
                if isinstance(lat, (int, float)):
                    self._latencies[arch].append(lat)
                    if len(self._latencies[arch]) > 500:
                        self._latencies[arch] = self._latencies[arch][-500:]
            # Track errors — classify unknown patterns
            if "error" in me.event_type or me.event_type == "system:error":
                ec = me.payload.get("error_class") or me.payload.get("error_type") or "unknown_pattern"
                self._error_counts[ec] += 1

    # ── Local stats (always available) ───────────────────────────────────────

    def get_stats(self) -> dict:
        with self._lock:
            latency_stats = {}
            for arch, lats in self._latencies.items():
                if lats:
                    latency_stats[arch] = {
                        "count": len(lats),
                        "avg_ms": round(sum(lats) / len(lats), 1),
                        "p95_ms": round(sorted(lats)[int(len(lats) * 0.95)], 1) if len(lats) >= 20 else None,
                    }
            # Frequency: events per hour for the last 24 buckets
            now_bucket = int(time.time() // 3600) * 3600
            freq_summary: dict[str, int] = {}
            for evt_type, buckets in self._freq_buckets.items():
                freq_summary[evt_type] = sum(
                    v for b, v in buckets.items() if b >= now_bucket - 24 * 3600
                )
            return {
                "system_id_prefix": self._system_id[:8],
                "buffer_size": len(self._buffer),
                "buffer_capacity": _BUFFER_SIZE,
                "schema_version": _SCHEMA_VERSION,
                "event_counts": dict(self._counters),
                "error_counts": dict(self._error_counts),
                "latency_stats": latency_stats,
                "frequency_24h": freq_summary,
                "sample_count": self._sample_count,
                "drop_count": self._drop_count,
                "last_bundle_ago_s": int(time.time() - self._last_bundle_ts),
                "next_bundle_in_s": max(0, int(self._last_bundle_ts + _BUNDLE_INTERVAL_S - time.time())),
            }

    def get_top_errors(self, limit: int = 10) -> list[dict]:
        with self._lock:
            return sorted(
                [{"error_class": k, "count": v} for k, v in self._error_counts.items()],
                key=lambda x: x["count"], reverse=True
            )[:limit]

    def get_event_summary(self, window_buckets: int = 24) -> dict[str, int]:
        """Event counts for the last N hour-buckets."""
        cutoff = int(time.time() // 3600 - window_buckets) * 3600
        with self._lock:
            counts: dict[str, int] = defaultdict(int)
            for me in self._buffer:
                if me.ts_bucket >= cutoff:
                    counts[me.event_type] += 1
        return dict(counts)

    # ── Bundle loop ───────────────────────────────────────────────────────────

    def _bundle_loop(self) -> None:
        while self._running:
            time.sleep(60)
            now = time.time()
            if now - self._last_bundle_ts >= _BUNDLE_INTERVAL_S:
                try:
                    self._create_and_export_bundle()
                except Exception as e:
                    logger.debug("Bundle loop error: %s", e)
                self._last_bundle_ts = now

    def force_bundle(self) -> str:
        """Admin-triggered immediate bundle creation."""
        return self._create_and_export_bundle()

    def _create_and_export_bundle(self) -> str:
        bundle = self._build_bundle()
        bundle_id = bundle["bundle_id"]

        # Always persist locally
        bundle_path = _BUNDLE_DIR / f"{bundle_id}.json"
        bundle_path.write_text(json.dumps(bundle, indent=2))
        logger.info("Telemetry bundle created: %s", bundle_id)

        # Persist local stats summary
        self._save_local_stats(bundle)

        # Export only if user opted in
        from neural_brain.config.privacy_mode import can_export_telemetry, get_privacy
        if can_export_telemetry():
            self._export_bundle(bundle, get_privacy().get_telemetry_endpoint())

        return bundle_id

    def _build_bundle(self) -> dict:
        now = time.time()
        nonce = self._next_nonce()
        with self._lock:
            events = list(self._buffer)
            counters = dict(self._counters)
            error_counts = dict(self._error_counts)
            latency_stats = {
                arch: {
                    "count": len(lats),
                    "avg_ms": round(sum(lats) / len(lats), 1) if lats else 0,
                }
                for arch, lats in self._latencies.items()
            }
            # Frequency summary
            freq_summary: dict[str, int] = {}
            for evt_type, buckets in self._freq_buckets.items():
                freq_summary[evt_type] = sum(buckets.values())
            samples = self._sample_count
            drops = self._drop_count
            # Reset for next bundle window
            self._buffer.clear()
            self._counters.clear()
            self._error_counts.clear()
            self._latencies.clear()
            self._freq_buckets.clear()
            self._sample_count = 0
            self._drop_count = 0

        # Aggregate event types into summary — cap at _MAX_BUNDLE_EVENTS total
        event_summary: dict[str, int] = defaultdict(int)
        for me in events[:_MAX_BUNDLE_EVENTS]:
            event_summary[me.event_type] += me.frequency

        return {
            "bundle_id": str(uuid.uuid4()),
            "system_id": self._system_id,    # rotating anon ID, not user-linked
            "schema_version": _SCHEMA_VERSION,
            "nonce": nonce,                  # monotonic counter — anti-replay
            "issued_at": int(now),           # server validates recency
            "period_start": int(now - _BUNDLE_INTERVAL_S),
            "period_end": int(now),
            "total_events": len(events),
            "capped_at": _MAX_BUNDLE_EVENTS,
            "event_summary": dict(event_summary),
            "frequency_summary": freq_summary,
            "error_counts": error_counts,
            "latency_stats": latency_stats,
            "sample_count": samples,
            "drop_count": drops,
            # No raw events, no user content
        }

    def _export_bundle(self, bundle: dict, endpoint: str) -> None:
        """Send signed bundle to endpoint. Fire-and-forget. Never blocks caller."""
        def _send():
            try:
                payload_bytes = json.dumps(bundle).encode()
                # Sign with HMAC-SHA256 via KeyManager
                headers_extra: dict[str, str] = {}
                try:
                    from neural_brain.security.key_manager import get_key_manager
                    version, sig = get_key_manager().sign(payload_bytes)
                    headers_extra = {
                        "X-Sig-Version": str(version),
                        "X-Sig": sig.hex(),
                    }
                except Exception:
                    pass
                # Timestamp + nonce headers let server reject replays
                import urllib.request
                req = urllib.request.Request(
                    endpoint,
                    data=payload_bytes,
                    headers={
                        "Content-Type": "application/json",
                        "X-Bundle-ID": bundle["bundle_id"],
                        "X-System-ID": bundle["system_id"][:8],
                        "X-Schema-Version": bundle.get("schema_version", _SCHEMA_VERSION),
                        "X-Issued-At": str(bundle.get("issued_at", int(time.time()))),
                        "X-Nonce": str(bundle.get("nonce", 0)),
                        **headers_extra,
                    },
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=_EXPORT_TIMEOUT_S):
                    pass
                logger.info("Telemetry bundle exported: %s → %s", bundle["bundle_id"][:8], endpoint)
            except Exception as e:
                logger.debug("Telemetry export failed (silent): %s", e)

        threading.Thread(target=_send, daemon=True, name="telemetry_export").start()

    # ── Nonce (monotonic counter, persisted across restarts) ──────────────────

    def _load_nonce(self) -> int:
        try:
            _NONCE_PATH.parent.mkdir(parents=True, exist_ok=True)
            if _NONCE_PATH.exists():
                return int(_NONCE_PATH.read_text().strip())
        except Exception:
            pass
        return 0

    def _next_nonce(self) -> int:
        self._nonce += 1
        try:
            _NONCE_PATH.write_text(str(self._nonce))
        except Exception:
            pass
        return self._nonce

    def _save_local_stats(self, bundle: dict) -> None:
        try:
            summary = {
                "last_bundle": bundle["bundle_id"],
                "period_end": bundle["period_end"],
                "total_events": bundle["total_events"],
                "top_events": sorted(
                    bundle["event_summary"].items(), key=lambda x: x[1], reverse=True
                )[:20],
                "top_errors": sorted(
                    bundle["error_counts"].items(), key=lambda x: x[1], reverse=True
                )[:10],
            }
            _STATS_PATH.write_text(json.dumps(summary, indent=2))
        except Exception:
            pass

    # ── User feedback (explicit, opt-in) ─────────────────────────────────────

    def submit_feedback(self, issue_type: str, severity: str, description_category: str,
                        extra_metrics: dict | None = None) -> str:
        """User-initiated feedback. description_category must be a label, not raw text."""
        feedback_id = str(uuid.uuid4())
        feedback = {
            "feedback_id": feedback_id,
            "system_id": self._system_id[:8],
            "issue_type": issue_type[:64],
            "severity": severity,
            "description_category": description_category[:64],
            "extra_metrics": {
                k: v for k, v in (extra_metrics or {}).items()
                if isinstance(v, (int, float, bool, str)) and len(str(v)) <= 64
            },
            "ts": int(time.time()),
        }
        # Save locally always
        fb_path = _BUNDLE_DIR / f"feedback_{feedback_id}.json"
        fb_path.write_text(json.dumps(feedback, indent=2))

        # Export if connected
        from neural_brain.config.privacy_mode import can_export_telemetry, get_privacy
        if can_export_telemetry():
            endpoint = get_privacy().get_telemetry_endpoint().rstrip("/") + "/feedback"
            self._export_bundle(feedback, endpoint)

        return feedback_id

    # ── System ID (rotating, anon, never user-linked) ─────────────────────────

    @staticmethod
    def _get_or_create_system_id() -> str:
        """Stable anon ID for this installation. NOT linked to any user or IP."""
        id_path = _TELEMETRY_DIR / ".system_id"
        try:
            id_path.parent.mkdir(parents=True, exist_ok=True)
            if id_path.exists():
                return id_path.read_text().strip()
        except Exception:
            pass
        new_id = hashlib.sha256(os.urandom(32)).hexdigest()
        try:
            id_path.write_text(new_id)
        except Exception:
            pass
        return new_id

    def rotate_system_id(self) -> str:
        """Admin action: rotate the anon system ID. Breaks linkability to past bundles."""
        id_path = _TELEMETRY_DIR / ".system_id"
        new_id = hashlib.sha256(os.urandom(32)).hexdigest()
        try:
            id_path.write_text(new_id)
        except Exception:
            pass
        with self._lock:
            self._system_id = new_id
        logger.info("System ID rotated → %s…", new_id[:8])
        return new_id


# ── Singleton ─────────────────────────────────────────────────────────────────
_engine: TelemetryEngine | None = None
_lock = threading.Lock()


def get_telemetry_engine() -> TelemetryEngine:
    global _engine
    if _engine is None:
        with _lock:
            if _engine is None:
                _engine = TelemetryEngine()
    return _engine
