"""Secret redaction — Python port of forge_learning.js::scrubSecretsFromLearningData.

Mirrors the exact scrubbing approach used by the existing distillation pipeline so
evolution traces/lessons/feeds are redacted identically before any persist:
  - provider keys (sk-ant-/sk-/gh*_), JWTs, bearer/authorization headers
  - api_key/token/secret/password/bearer/auth key:value forms
  - long hex secrets, AWS access keys, PEM private-key blocks, cookies/sessions
  - .env-style KEY=value lines (key kept, value redacted)
  - secret-named object keys dropped to [REDACTED]
  - emails redacted (low-value PII in learning data)
"""
from __future__ import annotations

import re
from typing import Any

_REDACTED = "[REDACTED]"

# Standalone, unambiguous provider-key shapes — applied first.
_PROVIDER_PATTERNS = [
    re.compile(r"sk-ant-[A-Za-z0-9_\-]{16,}", re.IGNORECASE),
    re.compile(r"sk-or-[A-Za-z0-9_\-]{16,}", re.IGNORECASE),  # OpenRouter
    re.compile(r"sk-[A-Za-z0-9]{20,}"),                        # OpenAI-style
    re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"),                 # GitHub tokens
    re.compile(r"eyJ[A-Za-z0-9_\-]+\.eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+"),  # JWT
]

# Generic key:value / token patterns. (regex, group_to_redact|None).
_SECRET_PATTERNS = [
    (re.compile(
        r"(?:api[_-]?key|apikey|token|secret|password|passwd|pwd|bearer|auth)"
        r"[^\s=:]*\s*[:=]\s*[\"']?([A-Za-z0-9+/=._\-]{8,})[\"']?",
        re.IGNORECASE), 1),
    (re.compile(r"\b[A-Fa-f0-9]{32,}\b"), None),               # long hex
    (re.compile(r"(?:AKIA|ASIA)[A-Z0-9]{16}"), None),          # AWS keys
    (re.compile(
        r"-----BEGIN [A-Z ]* PRIVATE KEY-----[\s\S]+?-----END [A-Z ]* PRIVATE KEY-----"),
     None),
    (re.compile(
        r"(?:cookie|session|csrf)[^\s=:]*\s*[:=]\s*[\"']?([A-Za-z0-9+/=._\-]{12,})[\"']?",
        re.IGNORECASE), 1),
    (re.compile(r"authorization\s*:\s*\S+\s*\S*", re.IGNORECASE), None),
    (re.compile(r"bearer\s+[A-Za-z0-9\-._~+/]+=*", re.IGNORECASE), None),
    (re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}"), None),  # email
]

_ENV_LINE = re.compile(r"^([A-Z][A-Z0-9_]+=).+$", re.MULTILINE)

_SECRET_KEY_NAMES = re.compile(
    r"^(password|passwd|secret|token|api_key|apikey|bearer|auth_token|"
    r"private_key|access_key|session_id|cookie)$",
    re.IGNORECASE,
)


def _scrub_string(s: str) -> str:
    out = s
    for pat in _PROVIDER_PATTERNS:
        out = pat.sub(_REDACTED, out)
    for pat, grp in _SECRET_PATTERNS:
        if grp is None:
            out = pat.sub(_REDACTED, out)
        else:
            out = pat.sub(
                lambda m: m.group(0).replace(m.group(grp), _REDACTED)
                if m.group(grp) else _REDACTED,
                out,
            )
    out = _ENV_LINE.sub(r"\1" + _REDACTED, out)
    return out


def scrub(data: Any) -> Any:
    """Deep-scrub strings/dicts/lists; drop secret-named keys. Pure / no I/O."""
    if data is None or isinstance(data, (int, float, bool)):
        return data
    if isinstance(data, str):
        return _scrub_string(data)
    if isinstance(data, (list, tuple)):
        return [scrub(v) for v in data]
    if isinstance(data, dict):
        out: dict[str, Any] = {}
        for k, v in data.items():
            out[k] = _REDACTED if _SECRET_KEY_NAMES.match(str(k)) else scrub(v)
        return out
    return data


__all__ = ["scrub"]
