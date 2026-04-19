"""Governance Digest — weekly compliance & health report.

Collects data from every governance subsystem and renders a structured
report covering:

  1. High-risk audit events  (AuditEngine, risk_score ≥ 0.6)
  2. Bias alerts             (BiasDetectionEngine, high_risk == True)
  3. System changes          (ChangeLog, all entries in the window)
  4. Failures                (ReliabilityEngine anomalies + CircuitBreaker
                              open/half-open breakers)
  5. Feedback summary        (UserFeedbackStore aggregate — optional)

────────────────────────────────────────────────────────────────
QUICK START
────────────────────────────────────────────────────────────────

::

    from core.governance_digest import get_governance_digest

    digest = get_governance_digest().run()
    print(digest["markdown"])          # human-readable Markdown
    print(digest["sections"])          # structured dict for downstream use

────────────────────────────────────────────────────────────────
CONFIGURATION
────────────────────────────────────────────────────────────────

  DIGEST_WINDOW_DAYS   — lookback window in days (default 7)
  DIGEST_MAX_EVENTS    — max events per section (default 50)
  DIGEST_STORE_PATH    — override JSONL output path (optional)
"""
from __future__ import annotations

import json
import logging
import os
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("ai_employee.governance_digest")

# ── Configuration ─────────────────────────────────────────────────────────────

_RUNTIME_DIR = Path(__file__).resolve().parent.parent
if str(_RUNTIME_DIR) not in sys.path:
    sys.path.insert(0, str(_RUNTIME_DIR))


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (ValueError, TypeError):
        return default


def _iso_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _epoch_from_iso(ts: str) -> float:
    """Convert ISO-8601 UTC string to Unix epoch.  Returns 0.0 on error."""
    try:
        import calendar
        t = time.strptime(ts, "%Y-%m-%dT%H:%M:%SZ")
        return float(calendar.timegm(t))
    except Exception:
        return 0.0


def _state_dir() -> Path:
    ai_home = os.environ.get("AI_HOME", "").strip()
    base = Path(ai_home) if ai_home else Path(__file__).resolve().parents[3]
    return base / "state"


def _default_store_path() -> Path:
    custom = os.environ.get("DIGEST_STORE_PATH", "").strip()
    if custom:
        return Path(custom)
    return _state_dir() / "governance_digests.jsonl"


# ── Core collector ─────────────────────────────────────────────────────────────

class GovernanceDigest:
    """Generate a weekly governance report by querying all subsystems.

    All subsystem integrations are **fault-isolated**: a failure in one
    collector never prevents the others from running.
    """

    def __init__(
        self,
        *,
        window_days: int | None = None,
        max_events: int | None = None,
        store_path: Path | None = None,
    ) -> None:
        self._window_days = window_days if window_days is not None else _env_int("DIGEST_WINDOW_DAYS", 7)
        self._max_events  = max_events  if max_events  is not None else _env_int("DIGEST_MAX_EVENTS", 50)
        self._store_path  = store_path or _default_store_path()
        self._store_path.parent.mkdir(parents=True, exist_ok=True)

    # ── Public ────────────────────────────────────────────────────────────────

    def run(self, *, window_days: int | None = None) -> dict[str, Any]:
        """Collect all sections and return the digest dict.

        The returned dict contains:
          - ``id``       — unique digest id
          - ``ts``       — generation timestamp (ISO-8601)
          - ``window``   — ``{"days": N, "from": <ISO>, "to": <ISO>}``
          - ``sections`` — per-section structured data
          - ``markdown`` — human-readable Markdown report
          - ``summary``  — one-line status string
        """
        wdays = window_days if window_days is not None else self._window_days
        cutoff_epoch = time.time() - (wdays * 86400)
        cutoff_ts    = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(cutoff_epoch))

        sections: dict[str, Any] = {}
        sections["high_risk_events"] = self._collect_high_risk_events(cutoff_epoch)
        sections["bias_alerts"]      = self._collect_bias_alerts(cutoff_epoch)
        sections["system_changes"]   = self._collect_system_changes(cutoff_epoch)
        sections["failures"]         = self._collect_failures(cutoff_epoch)
        sections["feedback_summary"] = self._collect_feedback()

        digest_id = f"dgst-{uuid.uuid4().hex[:12]}"
        ts = _iso_now()

        digest: dict[str, Any] = {
            "id":       digest_id,
            "ts":       ts,
            "window":   {"days": wdays, "from": cutoff_ts, "to": ts},
            "sections": sections,
            "summary":  _one_liner(sections),
            "markdown": _render_markdown(sections, window_days=wdays, generated_at=ts),
        }

        self._persist(digest)
        self._audit(digest)
        return digest

    # ── Collectors ────────────────────────────────────────────────────────────

    def _collect_high_risk_events(self, cutoff_epoch: float) -> dict[str, Any]:
        """Pull high-risk (risk_score ≥ 0.6) events from AuditEngine."""
        events: list[dict[str, Any]] = []
        error: str = ""
        try:
            from core.audit_engine import get_audit_engine  # type: ignore
            raw = get_audit_engine().recent(limit=self._max_events * 5, min_risk=0.6)
            for e in raw:
                if _epoch_from_iso(e.get("ts", "")) >= cutoff_epoch:
                    events.append({
                        "id":         e.get("id", ""),
                        "ts":         e.get("ts", ""),
                        "actor":      e.get("actor", ""),
                        "action":     e.get("action", ""),
                        "risk_score": e.get("risk_score", 0.0),
                        "trace_id":   e.get("trace_id", ""),
                    })
            events = events[:self._max_events]
        except Exception as exc:
            error = str(exc)
            logger.warning("high_risk_events collector error: %s", exc)

        return {"count": len(events), "events": events, "error": error}

    def _collect_bias_alerts(self, cutoff_epoch: float) -> dict[str, Any]:
        """Pull bias_block / bias_flag audit events for the window."""
        alerts: list[dict[str, Any]] = []
        error: str = ""
        try:
            from core.audit_engine import get_audit_engine  # type: ignore
            ae = get_audit_engine()
            # bias events are tagged with action starting with "bias_"
            all_events = ae.recent(limit=self._max_events * 5)
            for e in all_events:
                action = e.get("action", "")
                if not action.startswith("bias_"):
                    continue
                if _epoch_from_iso(e.get("ts", "")) < cutoff_epoch:
                    continue
                alerts.append({
                    "id":         e.get("id", ""),
                    "ts":         e.get("ts", ""),
                    "actor":      e.get("actor", ""),
                    "action":     action,
                    "risk_score": e.get("risk_score", 0.0),
                    "outcome":    e.get("output", {}).get("outcome", ""),
                    "high_risk":  e.get("output", {}).get("high_risk", False),
                })
            alerts = alerts[:self._max_events]
        except Exception as exc:
            error = str(exc)
            logger.warning("bias_alerts collector error: %s", exc)

        return {"count": len(alerts), "alerts": alerts, "error": error}

    def _collect_system_changes(self, cutoff_epoch: float) -> dict[str, Any]:
        """Pull system change entries from ChangeLog."""
        changes: list[dict[str, Any]] = []
        error: str = ""
        try:
            from core.change_log import get_changelog  # type: ignore
            all_entries = get_changelog().read(limit=self._max_events * 5)
            for entry in all_entries:
                ts = entry.get("timestamp", "")
                if _epoch_from_iso(ts) < cutoff_epoch:
                    continue
                changes.append({
                    "ts":          ts,
                    "actor":       entry.get("actor", ""),
                    "action_type": entry.get("action_type", ""),
                    "reason":      entry.get("reason", ""),
                    "outcome":     entry.get("outcome", ""),
                })
            changes = changes[:self._max_events]
        except Exception as exc:
            error = str(exc)
            logger.warning("system_changes collector error: %s", exc)

        return {"count": len(changes), "changes": changes, "error": error}

    def _collect_failures(self, cutoff_epoch: float) -> dict[str, Any]:
        """Collect reliability anomalies + open/half-open circuit breakers."""
        anomalies: list[dict[str, Any]] = []
        open_breakers: list[dict[str, Any]] = []
        stability_score: float | None = None
        forge_frozen: bool = False
        throttled_agents: list[str] = []
        error: str = ""

        try:
            from core.reliability_engine import get_reliability_engine  # type: ignore
            rel = get_reliability_engine()
            st = rel.status()
            stability_score = st.get("stability_score")
            forge_frozen     = bool(st.get("forge_frozen", False))
            throttled_agents = list(st.get("throttled_agents", []))

            # Audit anomalies as failures
            from core.audit_engine import get_audit_engine  # type: ignore
            raw_anomalies = get_audit_engine().anomalies(limit=self._max_events)
            for a in raw_anomalies:
                if _epoch_from_iso(a.get("ts", "")) >= cutoff_epoch:
                    anomalies.append(a)
        except Exception as exc:
            error = str(exc)
            logger.warning("failures/reliability collector error: %s", exc)

        try:
            from core.circuit_breaker import get_circuit_registry  # type: ignore
            reg = get_circuit_registry()
            for breaker in reg.status_all():
                if breaker.get("state") in ("open", "half_open"):
                    open_breakers.append({
                        "name":    breaker.get("name", ""),
                        "state":   breaker.get("state", ""),
                        "failure_count": breaker.get("failure_count", 0),
                    })
        except Exception as exc:
            if not error:
                error = str(exc)
            logger.warning("circuit_breaker collector error: %s", exc)

        total_failures = len(anomalies) + len(open_breakers)
        return {
            "count":            total_failures,
            "anomalies":        anomalies,
            "open_breakers":    open_breakers,
            "stability_score":  stability_score,
            "forge_frozen":     forge_frozen,
            "throttled_agents": throttled_agents,
            "error":            error,
        }

    def _collect_feedback(self) -> dict[str, Any]:
        """Collect user feedback summary (optional — never hard-fails)."""
        try:
            from core.user_feedback_store import get_feedback_store  # type: ignore
            sm = get_feedback_store().summary()
            return {
                "total":         sm.get("total", 0),
                "thumbs_up":     sm.get("thumbs_up", 0),
                "thumbs_down":   sm.get("thumbs_down", 0),
                "avg_reward":    sm.get("avg_reward", 0.0),
                "positive_rate": sm.get("positive_rate", 0.0),
                "error":         "",
            }
        except Exception as exc:
            logger.warning("feedback collector error: %s", exc)
            return {"total": 0, "thumbs_up": 0, "thumbs_down": 0, "avg_reward": 0.0, "positive_rate": 0.0, "error": str(exc)}

    # ── Persistence ───────────────────────────────────────────────────────────

    def _persist(self, digest: dict[str, Any]) -> None:
        """Append the digest (without markdown, to save space) to JSONL."""
        compact = {k: v for k, v in digest.items() if k != "markdown"}
        try:
            with self._store_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(compact) + "\n")
        except Exception as exc:
            logger.warning("Failed to persist governance digest: %s", exc)

    def load_recent(self, limit: int = 10) -> list[dict[str, Any]]:
        """Load the most recent *limit* digests (newest first) from the JSONL store."""
        if not self._store_path.exists():
            return []
        entries: list[dict[str, Any]] = []
        try:
            lines = self._store_path.read_text(encoding="utf-8", errors="replace").splitlines()
            for line in reversed(lines):
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except Exception:
                    pass
                if len(entries) >= limit:
                    break
        except Exception as exc:
            logger.warning("Failed to load governance digests: %s", exc)
        return entries

    def _audit(self, digest: dict[str, Any]) -> None:
        """Emit a low-risk audit record for each digest generation."""
        try:
            from core.audit_engine import get_audit_engine  # type: ignore
            sections = digest.get("sections", {})
            get_audit_engine().record(
                actor      = "governance_digest",
                action     = "governance_report_generated",
                input_data = {"window": digest.get("window", {})},
                output_data = {
                    "digest_id":         digest["id"],
                    "high_risk_count":   sections.get("high_risk_events", {}).get("count", 0),
                    "bias_alert_count":  sections.get("bias_alerts", {}).get("count", 0),
                    "change_count":      sections.get("system_changes", {}).get("count", 0),
                    "failure_count":     sections.get("failures", {}).get("count", 0),
                    "summary":           digest.get("summary", ""),
                },
                risk_score = 0.05,
            )
        except Exception as exc:
            logger.warning("Failed to audit digest %s: %s", digest.get("id"), exc)


# ── Markdown renderer ─────────────────────────────────────────────────────────

def _one_liner(sections: dict[str, Any]) -> str:
    hr  = sections.get("high_risk_events", {}).get("count", 0)
    ba  = sections.get("bias_alerts",      {}).get("count", 0)
    sc  = sections.get("system_changes",   {}).get("count", 0)
    fl  = sections.get("failures",         {}).get("count", 0)
    return (
        f"{hr} high-risk events | {ba} bias alerts | "
        f"{sc} system changes | {fl} failures"
    )


def _render_markdown(
    sections: dict[str, Any],
    *,
    window_days: int,
    generated_at: str,
) -> str:
    lines: list[str] = []
    _h = lines.append

    _h(f"# Governance Digest — {window_days}-Day Window")
    _h(f"**Generated:** {generated_at}")
    _h("")

    # ── Summary table ─────────────────────────────────────────────────────────
    hr  = sections.get("high_risk_events", {}).get("count", 0)
    ba  = sections.get("bias_alerts",      {}).get("count", 0)
    sc  = sections.get("system_changes",   {}).get("count", 0)
    fl  = sections.get("failures",         {}).get("count", 0)
    fb  = sections.get("feedback_summary", {})

    _h("## Executive Summary")
    _h("")
    _h("| Metric | Count |")
    _h("|--------|-------|")
    _h(f"| High-Risk Audit Events | **{hr}** |")
    _h(f"| Bias Alerts            | **{ba}** |")
    _h(f"| System Changes         | **{sc}** |")
    _h(f"| Failures / Anomalies   | **{fl}** |")
    if fb.get("total", 0) > 0:
        pos = f"{fb.get('positive_rate', 0.0)*100:.1f}%"
        _h(f"| User Feedback (total)  | {fb['total']} ({pos} positive) |")
    _h("")

    # ── 1. High-risk events ───────────────────────────────────────────────────
    _h("## 1. High-Risk Audit Events")
    _h("")
    hr_data = sections.get("high_risk_events", {})
    if hr_data.get("error"):
        _h(f"> ⚠️ Collection error: {hr_data['error']}")
        _h("")
    events = hr_data.get("events", [])
    if events:
        _h("| Timestamp | Actor | Action | Risk Score | Trace |")
        _h("|-----------|-------|--------|-----------|-------|")
        for e in events:
            score = f"{e.get('risk_score', 0.0):.2f}"
            trace = e.get("trace_id", "") or "—"
            _h(f"| {e.get('ts','')} | {e.get('actor','')} | `{e.get('action','')}` | {score} | {trace} |")
    else:
        _h("_No high-risk events in window._ ✅")
    _h("")

    # ── 2. Bias alerts ────────────────────────────────────────────────────────
    _h("## 2. Bias Alerts")
    _h("")
    ba_data = sections.get("bias_alerts", {})
    if ba_data.get("error"):
        _h(f"> ⚠️ Collection error: {ba_data['error']}")
        _h("")
    alerts = ba_data.get("alerts", [])
    if alerts:
        _h("| Timestamp | Agent | Action | Outcome | High Risk |")
        _h("|-----------|-------|--------|---------|-----------|")
        for a in alerts:
            hr_flag = "🔴 YES" if a.get("high_risk") else "NO"
            _h(f"| {a.get('ts','')} | {a.get('actor','')} | `{a.get('action','')}` | {a.get('outcome','')} | {hr_flag} |")
    else:
        _h("_No bias alerts in window._ ✅")
    _h("")

    # ── 3. System changes ─────────────────────────────────────────────────────
    _h("## 3. System Changes")
    _h("")
    sc_data = sections.get("system_changes", {})
    if sc_data.get("error"):
        _h(f"> ⚠️ Collection error: {sc_data['error']}")
        _h("")
    changes = sc_data.get("changes", [])
    if changes:
        _h("| Timestamp | Actor | Type | Reason | Outcome |")
        _h("|-----------|-------|------|--------|---------|")
        for c in changes:
            reason  = (c.get("reason",  "") or "—")[:80]
            outcome = (c.get("outcome", "") or "—")[:60]
            _h(f"| {c.get('ts','')} | {c.get('actor','')} | `{c.get('action_type','')}` | {reason} | {outcome} |")
    else:
        _h("_No system changes recorded in window._")
    _h("")

    # ── 4. Failures ───────────────────────────────────────────────────────────
    _h("## 4. Failures & System Health")
    _h("")
    fl_data = sections.get("failures", {})
    if fl_data.get("error"):
        _h(f"> ⚠️ Collection error: {fl_data['error']}")
        _h("")

    stability = fl_data.get("stability_score")
    if stability is not None:
        _h(f"**Stability Score:** {stability:.2f}")
    if fl_data.get("forge_frozen"):
        _h("⛔ **Forge is FROZEN.**")
    throttled = fl_data.get("throttled_agents", [])
    if throttled:
        _h(f"🚦 Throttled agents: {', '.join(throttled)}")
    _h("")

    anomalies = fl_data.get("anomalies", [])
    if anomalies:
        _h("### Audit Anomalies")
        _h("")
        _h("| Timestamp | Type | Severity | Count |")
        _h("|-----------|------|----------|-------|")
        for a in anomalies:
            _h(f"| {a.get('ts','')} | {a.get('type','')} | {a.get('severity','')} | {a.get('count','')} |")
        _h("")

    open_breakers = fl_data.get("open_breakers", [])
    if open_breakers:
        _h("### Open Circuit Breakers")
        _h("")
        _h("| Breaker | State | Failures |")
        _h("|---------|-------|----------|")
        for b in open_breakers:
            _h(f"| `{b.get('name','')}` | **{b.get('state','').upper()}** | {b.get('failure_count',0)} |")
        _h("")

    if not anomalies and not open_breakers:
        _h("_No failures detected in window._ ✅")
        _h("")

    # ── 5. User Feedback ──────────────────────────────────────────────────────
    if fb.get("total", 0) > 0 or not fb.get("error"):
        _h("## 5. User Feedback Summary")
        _h("")
        if fb.get("error"):
            _h(f"> ⚠️ Collection error: {fb['error']}")
        else:
            pos_pct = f"{fb.get('positive_rate', 0.0)*100:.1f}%"
            _h(f"- **Total ratings:** {fb.get('total', 0)}")
            _h(f"- 👍 Thumbs up: {fb.get('thumbs_up', 0)}")
            _h(f"- 👎 Thumbs down: {fb.get('thumbs_down', 0)}")
            _h(f"- **Positive rate:** {pos_pct}")
            _h(f"- **Average reward:** {fb.get('avg_reward', 0.0):.3f}")
        _h("")

    return "\n".join(lines)


# ── Singleton ─────────────────────────────────────────────────────────────────

_instance: Optional[GovernanceDigest] = None
_instance_lock = threading.Lock()


def get_governance_digest(
    *,
    window_days: int | None = None,
    max_events: int | None = None,
    store_path: Path | None = None,
) -> GovernanceDigest:
    """Return the process-wide :class:`GovernanceDigest` singleton."""
    global _instance
    with _instance_lock:
        if _instance is None:
            _instance = GovernanceDigest(
                window_days = window_days,
                max_events  = max_events,
                store_path  = store_path,
            )
    return _instance
