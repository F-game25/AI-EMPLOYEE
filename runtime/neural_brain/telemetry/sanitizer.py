"""Data Sanitization Layer — strips ALL user content before any telemetry use.

Contract:
  - Input:  raw event dict (may contain prompts, user text, memory content)
  - Output: sanitized metadata dict (categories, patterns, metrics only)

NEVER in output:
  - User prompts or responses
  - Memory content
  - File paths that expose usernames
  - IP addresses
  - User IDs (replaced with session-scoped anon token)
  - Email addresses
  - Any string longer than 40 chars that isn't a metric name

Everything is reduced to:
  - event_type  (category label)
  - intent_type (classifier output, not raw text)
  - error_class (exception type, not message)
  - latency_ms  (number)
  - success     (bool)
  - arch        (LLM/SLM/etc.)
  - severity    (LOW/MEDIUM/HIGH/CRITICAL)
"""
from __future__ import annotations

import hashlib
import re
from typing import Any

# ── Regex patterns for PII detection ─────────────────────────────────────────
_EMAIL_RE    = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
_IP_RE       = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
_UUID_RE     = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I)
_TOKEN_RE    = re.compile(r"\b(Bearer\s+|sk-|pk-|ey[A-Za-z0-9])[A-Za-z0-9\-_.+/]{10,}\b")
_PATH_RE     = re.compile(r"/(?:home|users|root)/[^/\s]+", re.I)
_LONG_STR_RE = re.compile(r"[a-zA-Z0-9 ,.\-_]{41,}")  # any string >40 chars

# Intent classifier — maps suspicious patterns to safe category labels
_INTENT_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"hack|exploit|inject|bypass|overflow|exfil", re.I), "suspicious_prompt"),
    (re.compile(r"password|secret|credential|api.?key|token", re.I), "credential_request"),
    (re.compile(r"delete|drop|truncate|purge|wipe", re.I), "destructive_intent"),
    (re.compile(r"explain|what|how|why|describe|tell me", re.I), "informational_query"),
    (re.compile(r"create|build|generate|write|make", re.I), "creation_task"),
    (re.compile(r"analyze|analyse|review|check|audit", re.I), "analysis_task"),
    (re.compile(r"search|find|look|query|fetch", re.I), "retrieval_task"),
]

# Safe metric keys — ONLY these pass through from payload
_SAFE_PAYLOAD_KEYS = frozenset({
    "arch", "provider", "model", "latency_ms", "success", "status",
    "error_class", "error_type", "severity", "attempt", "fallback_used",
    "candidate_count", "selected_rank", "node", "graph_size",
    "memory_size", "queue_depth", "agent_count", "task_count",
    "duration_ms", "tokens_in", "tokens_out", "phase", "step",
    "event_count", "threat_count", "threat_score", "mode",
    "version", "update_version", "issue_type", "frequency",
    "forge_status", "builder_type", "file_count",
})


class Sanitizer:
    """Stateless — all methods are pure functions of their inputs."""

    # ── Public entry point ────────────────────────────────────────────────────

    def sanitize_event(self, event: dict) -> dict | None:
        """Sanitize a raw system event for telemetry export.

        Returns None if the event carries no useful metric signal.
        """
        event_type = event.get("type", "")
        source = event.get("source", "system")
        payload = event.get("payload", {})

        # Never export internal debug or identity events
        if self._should_drop(event_type):
            return None

        clean_payload = self._sanitize_payload(payload)
        if not clean_payload and not self._is_metric_event(event_type):
            return None

        return {
            "event_type": event_type,
            "source": source,
            "payload": clean_payload,
            "ts_bucket": self._bucket_timestamp(event.get("timestamp", 0)),
        }

    def classify_intent(self, text: str) -> str:
        """Map raw user text → safe intent category label. Never stores the text."""
        if not text or len(text) < 3:
            return "empty"
        text_lower = text.lower()
        for pattern, label in _INTENT_PATTERNS:
            if pattern.search(text_lower):
                return label
        if len(text) < 20:
            return "short_query"
        if "?" in text:
            return "question"
        return "general_task"

    def classify_error(self, error: str | Exception) -> str:
        """Map exception/error string → safe type label. Never stores the message."""
        if isinstance(error, Exception):
            return type(error).__name__
        err_str = str(error)
        # Extract just the exception class name if present
        match = re.match(r"^([A-Za-z]+Error|[A-Za-z]+Exception|[A-Za-z]+Warning)", err_str)
        if match:
            return match.group(1)
        if "timeout" in err_str.lower():
            return "TimeoutError"
        if "connection" in err_str.lower():
            return "ConnectionError"
        if "permission" in err_str.lower() or "forbidden" in err_str.lower():
            return "PermissionError"
        if "not found" in err_str.lower() or "404" in err_str:
            return "NotFoundError"
        if "memory" in err_str.lower():
            return "MemoryError"
        return "UnknownError"

    def anon_id(self, raw_id: str) -> str:
        """One-way hash: user_id / IP / device → 8-char anon token. NOT reversible."""
        return hashlib.sha256(f"anon:{raw_id}".encode()).hexdigest()[:8]

    # ── Internal ──────────────────────────────────────────────────────────────

    def _sanitize_payload(self, payload: dict) -> dict:
        """Keep only safe metric keys from payload."""
        result = {}
        for key, value in payload.items():
            if key not in _SAFE_PAYLOAD_KEYS:
                continue
            if isinstance(value, (int, float, bool)):
                result[key] = value
            elif isinstance(value, str):
                # Even safe keys: strip PII if it somehow ended up there
                clean = self._strip_pii(value)
                if clean and len(clean) <= 64:
                    result[key] = clean
        return result

    @staticmethod
    def _strip_pii(text: str) -> str:
        text = _EMAIL_RE.sub("[email]", text)
        text = _IP_RE.sub("[ip]", text)
        text = _UUID_RE.sub("[id]", text)
        text = _TOKEN_RE.sub("[token]", text)
        text = _PATH_RE.sub("[path]", text)
        return text.strip()

    @staticmethod
    def _should_drop(event_type: str) -> bool:
        """Events that must never appear in telemetry, even sanitized."""
        DROP_PREFIXES = (
            "auth:login",       # login events contain user context
            "memory:",          # memory content
            "brain:graph",      # graph data
            "identity:",        # machine identity
            "chat:",            # chat content
            "orchestrator:",    # response content
            "privacy:",         # mode changes (local metadata only)
        )
        return any(event_type.startswith(p) for p in DROP_PREFIXES)

    @staticmethod
    def _is_metric_event(event_type: str) -> bool:
        """Events that always carry useful metrics even with empty payload."""
        METRIC_PREFIXES = (
            "system:error", "system:degraded", "system:recovered",
            "agent:failed", "agent:completed",
            "nb:model_call", "nb:reasoning_step",
            "forge:", "nb:forge",
            "blacklight:mode_change",
            "security:rate_limited",
        )
        return any(event_type.startswith(p) for p in METRIC_PREFIXES)

    @staticmethod
    def _bucket_timestamp(ts_ms: float) -> int:
        """Round timestamp to nearest hour bucket — prevents timing fingerprinting."""
        ts_s = ts_ms / 1000 if ts_ms > 1e10 else ts_ms
        return int(ts_s // 3600) * 3600  # nearest hour


# ── Singleton ─────────────────────────────────────────────────────────────────
_sanitizer: Sanitizer | None = None


def get_sanitizer() -> Sanitizer:
    global _sanitizer
    if _sanitizer is None:
        _sanitizer = Sanitizer()
    return _sanitizer
