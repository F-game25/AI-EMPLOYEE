"""ASCEND AI — Governance Dashboard Router

Provides governance digest data for the frontend Governance Dashboard.

Self-contained: works without the full runtime. Tries to import the real
GovernanceDigest when the runtime package is available; falls back to demo
data so the UI always renders.

Endpoints
─────────
  GET  /api/governance/summary        — top-level status card
  GET  /api/governance/digest         — latest full digest (or demo)
  POST /api/governance/digest/run     — trigger a fresh digest generation
  GET  /api/governance/audit-events   — recent high-risk audit events
  GET  /api/governance/bias-alerts    — recent bias alerts
"""
from __future__ import annotations

import time
import uuid
from typing import Any

from fastapi import APIRouter

router = APIRouter()

# ── Persisted latest digest (in-memory cache for this session) ────────────
_latest_digest: dict[str, Any] | None = None


# ── Demo data ─────────────────────────────────────────────────────────────

def _demo_digest() -> dict[str, Any]:
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    return {
        "id": f"dgst-{uuid.uuid4().hex[:12]}",
        "ts": now,
        "live_data": False,
        "window": {"days": 7, "from": "2026-04-12T00:00:00Z", "to": now},
        "summary": "2 high-risk events, 1 bias alert, 0 failures — system stable",
        "sections": {
            "high_risk_events": {
                "count": 2,
                "events": [
                    {
                        "id": "evt-001",
                        "ts": "2026-04-18T14:22:00Z",
                        "actor": "recruiter",
                        "action": "reject_candidate",
                        "risk_score": 0.72,
                        "trace_id": "trace-abc123",
                    },
                    {
                        "id": "evt-002",
                        "ts": "2026-04-17T09:10:00Z",
                        "actor": "lead-scorer",
                        "action": "score_lead",
                        "risk_score": 0.61,
                        "trace_id": "trace-def456",
                    },
                ],
                "error": "",
            },
            "bias_alerts": {
                "count": 1,
                "alerts": [
                    {
                        "id": "bias-001",
                        "ts": "2026-04-18T14:22:00Z",
                        "actor": "recruiter",
                        "action": "bias_block",
                        "risk_score": 0.72,
                        "outcome": "block",
                        "high_risk": True,
                    },
                ],
                "error": "",
            },
            "system_changes": {
                "count": 3,
                "changes": [
                    {"ts": "2026-04-15T10:00:00Z", "component": "forge", "change": "Mode enabled", "actor": "operator"},
                    {"ts": "2026-04-16T08:30:00Z", "component": "money-mode", "change": "Revenue target updated", "actor": "operator"},
                    {"ts": "2026-04-17T11:00:00Z", "component": "blacklight", "change": "Scan schedule changed", "actor": "operator"},
                ],
                "error": "",
            },
            "failures": {
                "count": 0,
                "items": [],
                "circuit_breakers": [],
                "error": "",
            },
            "feedback_summary": {
                "thumbs_up": 38,
                "thumbs_down": 4,
                "net_reward": 34.0,
                "total": 42,
                "error": "",
            },
        },
        "markdown": (
            "# Governance Digest — Weekly Report\n\n"
            "**Generated:** " + now + "\n\n"
            "## High-Risk Events (2)\n"
            "- `recruiter` reject_candidate — risk 0.72\n"
            "- `lead-scorer` score_lead — risk 0.61\n\n"
            "## Bias Alerts (1)\n"
            "- `recruiter` BLOCKED — high risk bias detected\n\n"
            "## System Changes (3)\n"
            "- Forge mode enabled\n"
            "- Money Mode revenue target updated\n"
            "- Blacklight scan schedule changed\n\n"
            "## Failures\nNone\n\n"
            "## Feedback Summary\n"
            "👍 38 / 👎 4 — net reward +34.0\n"
        ),
    }


def _try_live_digest(window_days: int = 7) -> dict[str, Any] | None:
    """Attempt to generate a real digest from the runtime GovernanceDigest."""
    try:
        import sys
        from pathlib import Path
        runtime = Path(__file__).resolve().parents[4] / "runtime"
        if str(runtime) not in sys.path:
            sys.path.insert(0, str(runtime))
        from core.governance_digest import get_governance_digest  # type: ignore
        digest = get_governance_digest().run(window_days=window_days)
        digest["live_data"] = True
        return digest
    except Exception:
        return None


def _safe_str(value: Any, max_len: int = 500) -> str:
    """Return value as a string only if it is already a plain string literal.

    Rejects any value that originates from an exception (it will not be a
    plain str instance produced by our own code).  This prevents taint from
    ``str(exc)`` inside runtime collectors from reaching API responses.
    """
    if isinstance(value, str):
        return value[:max_len]
    return ""


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _safe_bool(value: Any) -> bool:
    return bool(value)


def _build_event(raw: Any) -> dict[str, Any]:
    """Reconstruct a high-risk event from only the known-safe scalar fields."""
    if not isinstance(raw, dict):
        return {}
    return {
        "id":         _safe_str(raw.get("id", "")),
        "ts":         _safe_str(raw.get("ts", "")),
        "actor":      _safe_str(raw.get("actor", "")),
        "action":     _safe_str(raw.get("action", "")),
        "risk_score": _safe_float(raw.get("risk_score", 0.0)),
        "trace_id":   _safe_str(raw.get("trace_id", "")),
    }


def _build_alert(raw: Any) -> dict[str, Any]:
    """Reconstruct a bias alert from only the known-safe scalar fields."""
    if not isinstance(raw, dict):
        return {}
    return {
        "id":         _safe_str(raw.get("id", "")),
        "ts":         _safe_str(raw.get("ts", "")),
        "actor":      _safe_str(raw.get("actor", "")),
        "action":     _safe_str(raw.get("action", "")),
        "risk_score": _safe_float(raw.get("risk_score", 0.0)),
        "outcome":    _safe_str(raw.get("outcome", "")),
        "high_risk":  _safe_bool(raw.get("high_risk", False)),
    }


def _build_change(raw: Any) -> dict[str, Any]:
    """Reconstruct a system-change entry from only the known-safe scalar fields."""
    if not isinstance(raw, dict):
        return {}
    return {
        "ts":        _safe_str(raw.get("ts", "")),
        "component": _safe_str(raw.get("component", "")),
        "change":    _safe_str(raw.get("change", "")),
        "actor":     _safe_str(raw.get("actor", "")),
    }


def _build_safe_digest(digest: dict[str, Any]) -> dict[str, Any]:
    """Return a fully reconstructed digest with only known-safe scalar values.

    Every field is extracted by name and cast to a safe primitive type so that
    no tainted data (e.g. ``str(exc)`` from runtime collectors) can reach the
    API response.
    """
    secs = digest.get("sections", {})

    hr_sec   = secs.get("high_risk_events", {}) if isinstance(secs.get("high_risk_events"), dict) else {}
    bias_sec = secs.get("bias_alerts", {})      if isinstance(secs.get("bias_alerts"), dict)      else {}
    chg_sec  = secs.get("system_changes", {})   if isinstance(secs.get("system_changes"), dict)   else {}
    fail_sec = secs.get("failures", {})         if isinstance(secs.get("failures"), dict)         else {}
    fb_sec   = secs.get("feedback_summary", {}) if isinstance(secs.get("feedback_summary"), dict) else {}

    window = digest.get("window", {})
    if not isinstance(window, dict):
        window = {}

    return {
        "id":         _safe_str(digest.get("id", "")),
        "ts":         _safe_str(digest.get("ts", "")),
        "live_data":  _safe_bool(digest.get("live_data", False)),
        "summary":    _safe_str(digest.get("summary", "")),
        "window": {
            "days": _safe_int(window.get("days", 7)),
            "from": _safe_str(window.get("from", "")),
            "to":   _safe_str(window.get("to", "")),
        },
        "sections": {
            "high_risk_events": {
                "count":     _safe_int(hr_sec.get("count", 0)),
                "has_error": bool(hr_sec.get("error", "")),
                "events":    [_build_event(e) for e in (hr_sec.get("events") or []) if isinstance(e, dict)],
            },
            "bias_alerts": {
                "count":     _safe_int(bias_sec.get("count", 0)),
                "has_error": bool(bias_sec.get("error", "")),
                "alerts":    [_build_alert(a) for a in (bias_sec.get("alerts") or []) if isinstance(a, dict)],
            },
            "system_changes": {
                "count":     _safe_int(chg_sec.get("count", 0)),
                "has_error": bool(chg_sec.get("error", "")),
                "changes":   [_build_change(c) for c in (chg_sec.get("changes") or []) if isinstance(c, dict)],
            },
            "failures": {
                "count":     _safe_int(fail_sec.get("count", 0)),
                "has_error": bool(fail_sec.get("error", "")),
            },
            "feedback_summary": {
                "thumbs_up":   _safe_int(fb_sec.get("thumbs_up", 0)),
                "thumbs_down": _safe_int(fb_sec.get("thumbs_down", 0)),
                "net_reward":  _safe_float(fb_sec.get("net_reward", 0)),
                "total":       _safe_int(fb_sec.get("total", 0)),
            },
        },
        "markdown": _safe_str(digest.get("markdown", ""), max_len=10000),
    }


# ── Endpoints ─────────────────────────────────────────────────────────────

@router.get("/governance/summary")
def get_governance_summary():
    raw = _latest_digest or _demo_digest()
    safe = _build_safe_digest(raw)
    secs = safe["sections"]
    high_risk_count = secs["high_risk_events"]["count"]
    bias_count       = secs["bias_alerts"]["count"]
    failure_count    = secs["failures"]["count"]
    changes_count    = secs["system_changes"]["count"]
    feedback         = secs["feedback_summary"]
    status = "CRITICAL" if (high_risk_count > 5 or bias_count > 3) else \
             "WARN"     if (high_risk_count > 0 or bias_count > 0) else "OK"
    return {
        "status":           status,
        "high_risk_events": high_risk_count,
        "bias_alerts":      bias_count,
        "system_changes":   changes_count,
        "failures":         failure_count,
        "feedback_net":     feedback["net_reward"],
        "last_digest_ts":   safe["ts"],
        "window_days":      safe["window"]["days"],
        "live_data":        safe["live_data"],
    }


@router.get("/governance/digest")
def get_digest():
    global _latest_digest
    if _latest_digest is None:
        live = _try_live_digest()
        _latest_digest = live if live else _demo_digest()
    return _build_safe_digest(_latest_digest)


@router.post("/governance/digest/run")
def run_digest():
    global _latest_digest
    live = _try_live_digest()
    _latest_digest = live if live else _demo_digest()
    _latest_digest["refreshed_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    return {"success": True, "digest": _build_safe_digest(_latest_digest)}


@router.get("/governance/audit-events")
def get_audit_events(limit: int = 20):
    raw = _latest_digest or _demo_digest()
    safe = _build_safe_digest(raw)
    events = safe["sections"]["high_risk_events"]["events"]
    return {"events": events[:limit], "total": len(events)}


@router.get("/governance/bias-alerts")
def get_bias_alerts(limit: int = 20):
    raw = _latest_digest or _demo_digest()
    safe = _build_safe_digest(raw)
    alerts = safe["sections"]["bias_alerts"]["alerts"]
    return {"alerts": alerts[:limit], "total": len(alerts)}
