"""C4 — Memory closed-loop: provenance-trust gate for the Python RAG path.

`MemoryRouter.retrieve()` feeds memories into the unified pipeline / codegen
context. CLAUDE.md rule #2 + #18: a retrieved memory is UNTRUSTED DATA, never
command authority — a poisoned or stale memory must not become an instruction.
This module is the retrieval-side guard that mirrors the Node forge gate
(backend/services/memory_trust_gate.js) and shares its config
(runtime/config/memory_trust.json).

A memory may pass only if its trust score clears ``min_trust`` AND its text does
not trip an injection pattern. Signals available on the Python side differ from
the forge SQLite rows, so they are mapped onto the same three config weights:

    confidence    → metadata["confidence"]   (how sure we are it is true)
    corroboration → metadata["importance"]    (how reinforced / load-bearing)
    provenance    → metadata["verified"] / trusted ``source`` / unknown

Hard rules: pure, config-driven with baked-in defaults, NEVER raises (degrades
to "keep nothing" on error — fail-closed), kill-switch ``MEMORY_TRUST_GATE=0``.
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "memory_trust.json"

_DEFAULTS: dict[str, Any] = {
    "min_trust": 0.40,
    "max_injected": 6,
    "weights": {"confidence": 0.45, "corroboration": 0.30, "provenance": 0.25},
    "provenance": {
        "trusted_sources": ["run", "verified", "test_pass", "memory_service", "lesson", "user"],
        "trusted_source_credit": 0.8,
        "unknown_source_credit": 0.25,
        "verified_credit": 1.0,
    },
    "recency": {"enabled": True, "weight": 0.0, "half_life_days": 45},
    "injection_markers": [
        "ignore previous", "ignore all previous", "disregard the above", "disregard previous",
        "system prompt", "you are now", "new instructions", "override your",
        "forget your instructions", "do not follow", "instead of", "act as", "jailbreak",
        "developer mode",
    ],
}

_cfg: dict[str, Any] | None = None


def _deep_merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_config() -> dict[str, Any]:
    """Config with baked-in defaults; never raises on a bad/missing file."""
    global _cfg
    if _cfg is not None:
        return _cfg
    file_cfg: dict[str, Any] = {}
    try:
        file_cfg = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001 — config problems must not break retrieval
        logger.debug("memory_trust: using defaults (%s)", e)
        file_cfg = {}
    _cfg = _deep_merge(_DEFAULTS, file_cfg if isinstance(file_cfg, dict) else {})
    return _cfg


def reload() -> None:
    """Test/admin seam — drop the cached config."""
    global _cfg, _INJ_RE
    _cfg = None
    _INJ_RE = None


def gate_enabled() -> bool:
    return os.environ.get("MEMORY_TRUST_GATE", "1") != "0"


def _clamp01(v: Any, default: float = 0.0) -> float:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return default
    return 0.0 if f < 0 else 1.0 if f > 1 else f


_INJ_RE: re.Pattern | None = None


def _injection_re() -> re.Pattern:
    global _INJ_RE
    if _INJ_RE is None:
        markers = load_config().get("injection_markers") or []
        pat = "|".join(re.escape(str(m)) for m in markers) or r"(?!x)x"  # never-match if empty
        _INJ_RE = re.compile(pat, re.IGNORECASE)
    return _INJ_RE


def _has_injection(text: str) -> bool:
    try:
        return bool(_injection_re().search(str(text or "")))
    except Exception:  # noqa: BLE001
        return True  # fail-closed: if detection breaks, treat as injection


def _meta(entry: dict) -> dict:
    m = entry.get("metadata") if isinstance(entry, dict) else None
    return m if isinstance(m, dict) else {}


def _provenance_score(entry: dict, cfg: dict) -> float:
    p = cfg["provenance"]
    meta = _meta(entry)
    if meta.get("verified") is True:
        return _clamp01(p.get("verified_credit", 1.0))
    src = str(meta.get("source") or entry.get("source") or entry.get("_source") or "").lower()
    # Exact token match — substring matching would let "unverified" satisfy "verified".
    src_tokens = set(re.split(r"[^a-z0-9_]+", src))
    trusted = any(str(t).lower() in src_tokens for t in (p.get("trusted_sources") or []))
    return _clamp01(p.get("trusted_source_credit") if trusted else p.get("unknown_source_credit"))


def _recency_factor(entry: dict, cfg: dict) -> float:
    rec = cfg.get("recency") or {}
    if not rec.get("enabled"):
        return 1.0
    meta = _meta(entry)
    ts = meta.get("created_at") or meta.get("timestamp") or entry.get("created_at")
    if not ts:
        return 1.0
    try:
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        age_days = max(0.0, (datetime.now(timezone.utc) - dt).total_seconds() / 86400.0)
        half = max(1e-6, float(rec.get("half_life_days", 45)))
        return 0.5 ** (age_days / half)
    except Exception:  # noqa: BLE001
        return 1.0


def trust_score(entry: dict, cfg: dict | None = None) -> float:
    """Trust in [0,1]. Injection-bearing memories are hard-zeroed (fail-closed)."""
    if not isinstance(entry, dict):
        return 0.0
    cfg = cfg or load_config()
    if _has_injection(entry.get("text") or entry.get("content") or ""):
        return 0.0
    meta = _meta(entry)
    w = cfg["weights"]
    wc, wo, wp = float(w.get("confidence", 0)), float(w.get("corroboration", 0)), float(w.get("provenance", 0))
    wsum = (wc + wo + wp) or 1.0
    # Missing trust metadata must NOT earn default credit — an opaque legacy row
    # should not pass the gate just because confidence/importance are absent.
    conf = _clamp01(meta.get("confidence"), 0.0)
    corro = _clamp01(meta.get("importance"), 0.0)
    prov = _provenance_score(entry, cfg)
    base = (wc * conf + wo * corro + wp * prov) / wsum

    rec = cfg.get("recency") or {}
    rw = float(rec.get("weight", 0) or 0)
    if rec.get("enabled") and rw > 0:
        base = (1 - rw) * base + rw * _recency_factor(entry, cfg)
    return _clamp01(base)


def apply_trust_gate(
    results: list[dict],
    *,
    min_trust: float | None = None,
    limit: int | None = None,
) -> tuple[list[dict], dict]:
    """Filter retrieval results by trust. Returns (kept, stats). Never raises.

    Relevance order is preserved (results arrive already ranked by ``_score``);
    we only DROP untrusted/injection-bearing entries and cap the count. Each kept
    entry gets a ``_trust`` field for downstream telemetry.
    """
    try:
        if not gate_enabled():
            n = len(results) if isinstance(results, list) else 0
            return (list(results or []), {"in": n, "kept": n, "dropped_low_trust": 0,
                                          "dropped_injection": 0, "disabled": True})
        cfg = load_config()
        lst = list(results or [])
        mt = cfg["min_trust"] if min_trust is None else float(min_trust)
        cap = cfg["max_injected"] if limit is None else int(limit)
        kept: list[dict] = []
        dropped_low = 0
        dropped_inj = 0
        for e in lst:
            text = e.get("text") or e.get("content") or "" if isinstance(e, dict) else ""
            if _has_injection(text):
                dropped_inj += 1
                continue
            t = trust_score(e, cfg)
            if t < mt:
                dropped_low += 1
                continue
            kept.append({**e, "_trust": round(t, 3)})
        if cap >= 0:
            kept = kept[:cap]
        return (kept, {"in": len(lst), "kept": len(kept), "dropped_low_trust": dropped_low,
                       "dropped_injection": dropped_inj, "min_trust": mt})
    except Exception as e:  # noqa: BLE001 — fail-closed: keep nothing rather than ungated
        logger.warning("memory_trust: gate error, dropping all (%s)", e)
        return ([], {"in": len(results) if isinstance(results, list) else 0, "kept": 0,
                     "dropped_low_trust": 0, "dropped_injection": 0, "error": True})
