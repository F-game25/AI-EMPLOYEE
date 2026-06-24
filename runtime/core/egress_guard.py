"""Egress guard (Python) — never-leak gate for the LLM provider path.

Mirrors backend/services/egress_guard.js and shares runtime/config/egress_policy.json.
Before any prompt/message leaves this machine to an EXTERNAL provider (Anthropic /
OpenAI / OpenRouter) it must pass through here: secrets are BLOCKED off-box, PII is
redacted, and the destination policy is enforced deny-by-default + fail-closed.

CLAUDE.md #5/#20: do not send sensitive local data to external models; redact prompts
before remote fallback; prevent silent leakage.

Reuses runtime/core/output_guard.redact_pii_echo for PII. Pure, never raises
(on any error → BLOCK).
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "egress_policy.json"

_DEFAULTS: dict[str, Any] = {
    "destination_tiers": {"local": 0, "peer_trusted": 1, "rented_trusted": 2, "external_api": 3},
    "classification_rank": {"public": 0, "internal": 1, "pii": 2, "secret": 3},
    "policy_matrix": {
        "local": {"secret": "allow", "pii": "allow", "internal": "allow", "public": "allow"},
        "peer_trusted": {"secret": "block", "pii": "redact", "internal": "allow", "public": "allow"},
        "rented_trusted": {"secret": "block", "pii": "redact", "internal": "redact", "public": "allow"},
        "external_api": {"secret": "block", "pii": "redact", "internal": "redact", "public": "allow"},
    },
    "caps": {"max_payload_bytes": 2097152, "dispatch_timeout_ms": 60000, "max_result_bytes": 8388608},
}

# Secret shapes that must NEVER leave the box (mirror of the Node scrubber).
_SECRET_PATTERNS = [
    re.compile(r"sk-ant-[A-Za-z0-9_\-]{16,}"),
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile(r"eyJ[A-Za-z0-9_\-]+\.eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+"),  # JWT
    re.compile(r"(?:AKIA|ASIA)[A-Z0-9]{16}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]+?-----END [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"(?im)^([A-Z][A-Z0-9_]+)=\S+$"),  # .env-style KEY=value
    re.compile(r"(?i)(?:api[_-]?key|secret|token|password|passwd|bearer)\s*[:=]\s*['\"]?[A-Za-z0-9+/=._\-]{12,}"),
]
_PII_PATTERNS = [
    re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}"),  # email
    re.compile(r"\b(?:\+?\d[\d\s().\-]{7,}\d)\b"),                      # phone-ish (sync w/ JS mirror)
    re.compile(r"\b(?:\d[ \-]*?){13,19}\b"),                           # card-ish
]
_INTERNAL_PATTERNS = [
    re.compile(r"(?:^|[\s\"'`(=])/(?:home|root|etc|var|usr|opt|Users)/"),
    re.compile(r"\b[A-Za-z0-9_\-]+\.(?:local|internal|lan|home)\b"),
]

_cfg: dict[str, Any] | None = None


def _deep_merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for k, v in (override or {}).items():
        out[k] = _deep_merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def load_policy() -> dict[str, Any]:
    global _cfg
    if _cfg is not None:
        return _cfg
    f: dict[str, Any] = {}
    try:
        f = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001 — config problems must not break routing
        logger.debug("egress_guard: using defaults (%s)", e)
        f = {}
    _cfg = _deep_merge(_DEFAULTS, f if isinstance(f, dict) else {})
    return _cfg


def reload() -> None:
    global _cfg
    _cfg = None


def gate_enabled() -> bool:
    return os.environ.get("EGRESS_GUARD", "1") != "0"


def _text_of(payload: Any) -> str:
    if isinstance(payload, str):
        return payload
    try:
        return json.dumps(payload, default=str)
    except Exception:  # noqa: BLE001
        return str(payload)


def contains_secret(payload: Any) -> bool:
    try:
        t = _text_of(payload)
        return any(p.search(t) for p in _SECRET_PATTERNS)
    except Exception:  # noqa: BLE001
        return True  # fail-closed


def classify(payload: Any) -> str:
    try:
        if contains_secret(payload):
            return "secret"
        t = _text_of(payload)
        if any(p.search(t) for p in _PII_PATTERNS):
            return "pii"
        if any(p.search(t) for p in _INTERNAL_PATTERNS):
            return "internal"
        return "public"
    except Exception:  # noqa: BLE001
        return "secret"  # fail-closed


def _redact_text(s: str) -> str:
    out = s
    for p in _SECRET_PATTERNS:
        out = p.sub("[REDACTED]", out)
    # Reuse the project's PII redactor when available; fall back to local patterns.
    try:
        from core.output_guard import redact_pii_echo
        out = redact_pii_echo(out)
    except Exception:  # noqa: BLE001
        for p in _PII_PATTERNS:
            out = p.sub("[REDACTED_PII]", out)
    return out


def redact(payload: Any, _depth: int = 0) -> Any:
    if _depth > 64:
        return "[TRUNCATED_DEPTH]"
    try:
        if isinstance(payload, str):
            return _redact_text(payload)
        if isinstance(payload, list):
            return [redact(x, _depth + 1) for x in payload]
        if isinstance(payload, dict):
            out = {}
            for k, v in payload.items():
                if str(k) in ("__proto__", "constructor", "prototype"):
                    continue
                # Drop secret-named keys entirely.
                if re.fullmatch(r"(?i)password|passwd|secret|token|api_key|apikey|bearer|auth_token|private_key|access_key|session_id|cookie", str(k)):
                    out[k] = "[REDACTED]"
                else:
                    out[k] = redact(v, _depth + 1)
            return out
        return payload
    except Exception:  # noqa: BLE001
        return "[REDACTED]"


def guard(payload: Any, destination_tier: str) -> dict[str, Any]:
    """Decide whether `payload` may leave to `destination_tier`. Never raises.

    Returns {action, payload, classification, tier, reason}. action ∈ allow|redact|block.
    """
    try:
        if not gate_enabled():
            return {"action": "allow", "payload": payload, "classification": "ungated", "tier": destination_tier, "reason": "EGRESS_GUARD=0"}
        cfg = load_policy()
        tier = str(destination_tier or "")
        matrix = cfg["policy_matrix"]
        if tier not in matrix:
            return {"action": "block", "payload": None, "classification": "unknown", "tier": tier, "reason": f"unknown destination tier '{tier}'"}
        text = _text_of(payload)
        if len(text.encode("utf-8", "ignore")) > int(cfg["caps"]["max_payload_bytes"]):
            return {"action": "block", "payload": None, "classification": "oversize", "tier": tier, "reason": "payload exceeds size cap"}
        cls = classify(payload)
        action = matrix[tier].get(cls, "block")  # missing rule → block
        if action == "allow":
            return {"action": "allow", "payload": payload, "classification": cls, "tier": tier, "reason": "within policy"}
        if action == "redact":
            return {"action": "redact", "payload": redact(payload), "classification": cls, "tier": tier, "reason": f"{cls} redacted for {tier}"}
        return {"action": "block", "payload": None, "classification": cls, "tier": tier, "reason": f"{cls} not permitted to {tier}"}
    except Exception:  # noqa: BLE001 — fail-closed
        return {"action": "block", "payload": None, "classification": "error", "tier": str(destination_tier or ""), "reason": "egress guard error (fail-closed)"}


# Provider name → destination tier. Local providers never trigger redaction;
# everything else is an external third party.
_LOCAL_PROVIDERS = {"ollama", "local", "llama_cpp", "vllm_local"}


def tier_for_provider(provider: str) -> str:
    return "local" if str(provider or "").lower() in _LOCAL_PROVIDERS else "external_api"


def guard_for_provider(payload: Any, provider: str) -> dict[str, Any]:
    """Convenience: guard a payload for a named LLM provider."""
    return guard(payload, tier_for_provider(provider))
