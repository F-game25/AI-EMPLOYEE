"""Local AI Feedback Analyzer — runs entirely on-device.

Analyzes sanitized telemetry to detect:
  - Recurring error patterns
  - Performance bottlenecks (high latency archs)
  - Agent failure clusters
  - Forge failure patterns
  - Security anomalies

Produces structured improvement proposals that feed into Ascend Forge.

All analysis input is already sanitized (no user content). The LLM is called
only if privacy mode allows it AND an Ollama instance is available locally.
Falls back to pure rule-based analysis when LLM is unavailable.

Output schema per issue:
  {
    issue_type: str,        # "high_latency" | "error_spike" | "agent_failure" | etc.
    frequency: int,         # how many times observed
    severity: str,          # LOW | MEDIUM | HIGH | CRITICAL
    suggested_fix_type: str,# "model_switch" | "retry_config" | "rate_limit" | etc.
    affected_component: str,# "LLM_arch" | "forge" | "agent:X" | etc.
    forge_trigger: bool,    # whether this should trigger Ascend Forge
    details: dict,          # numeric metrics only
  }
"""
from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass, asdict
from typing import Any

logger = logging.getLogger(__name__)

# Thresholds for rule-based detection
_LATENCY_HIGH_MS    = 5000    # avg > 5s → high latency issue
_LATENCY_CRIT_MS    = 15000   # avg > 15s → critical
_ERROR_RATE_HIGH    = 0.15    # >15% errors in window → spike
_ERROR_RATE_CRIT    = 0.40    # >40% → critical
_MIN_SAMPLES        = 5       # ignore archs with fewer samples
_FORGE_MIN_SEVERITY = "HIGH"  # only HIGH/CRITICAL trigger forge


@dataclass
class IssueReport:
    issue_type: str
    frequency: int
    severity: str
    suggested_fix_type: str
    affected_component: str
    forge_trigger: bool
    details: dict
    confidence: float = 1.0   # 0.0–1.0 — rule-based always 1.0, AI may lower it

    def to_dict(self) -> dict:
        return asdict(self)


class LocalAnalyzer:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._last_analysis: list[IssueReport] = []
        self._last_run_ts: float = 0
        self._ai_available: bool = False
        self._ai_checked: bool = False

    # ── Main entry point ──────────────────────────────────────────────────────

    def analyze(self, stats: dict | None = None) -> list[dict]:
        """Run full analysis. Returns list of IssueReport dicts."""
        if stats is None:
            try:
                from neural_brain.telemetry.telemetry_engine import get_telemetry_engine
                stats = get_telemetry_engine().get_stats()
            except Exception as e:
                logger.debug("LocalAnalyzer: stats unavailable: %s", e)
                stats = {}

        issues: list[IssueReport] = []
        issues.extend(self._analyze_latency(stats))
        issues.extend(self._analyze_errors(stats))
        issues.extend(self._analyze_event_patterns(stats))
        issues.extend(self._analyze_frequency(stats))

        # Log unknown patterns
        self._log_unknown(stats)

        # AI enhancement (optional, local only) — may lower confidence
        if self._should_use_ai():
            issues = self._ai_enhance(issues, stats)

        # Trigger forge for severe issues (HIGH/CRITICAL + confidence >= 0.7)
        self._maybe_trigger_forge(issues)

        with self._lock:
            self._last_analysis = issues
            self._last_run_ts = time.time()

        return [i.to_dict() for i in issues]

    def get_last_analysis(self) -> list[dict]:
        with self._lock:
            return [i.to_dict() for i in self._last_analysis]

    # ── Rule-based detectors ──────────────────────────────────────────────────

    def _analyze_latency(self, stats: dict) -> list[IssueReport]:
        issues = []
        for arch, lat_stats in stats.get("latency_stats", {}).items():
            count = lat_stats.get("count", 0)
            avg = lat_stats.get("avg_ms", 0)
            if count < _MIN_SAMPLES or avg == 0:
                continue
            if avg >= _LATENCY_CRIT_MS:
                issues.append(IssueReport(
                    issue_type="critical_latency",
                    frequency=count,
                    severity="CRITICAL",
                    suggested_fix_type="model_switch_or_fallback",
                    affected_component=f"arch:{arch}",
                    forge_trigger=True,
                    details={"avg_ms": avg, "count": count, "arch": arch},
                ))
            elif avg >= _LATENCY_HIGH_MS:
                issues.append(IssueReport(
                    issue_type="high_latency",
                    frequency=count,
                    severity="HIGH",
                    suggested_fix_type="timeout_or_model_config",
                    affected_component=f"arch:{arch}",
                    forge_trigger=True,
                    details={"avg_ms": avg, "count": count, "arch": arch},
                ))
        return issues

    def _analyze_errors(self, stats: dict) -> list[IssueReport]:
        issues = []
        error_counts = stats.get("error_counts", {})
        total_events = max(stats.get("buffer_size", 1), 1)

        for error_class, count in error_counts.items():
            rate = count / total_events
            if rate >= _ERROR_RATE_CRIT:
                severity, fix = "CRITICAL", "circuit_breaker_or_retry_config"
                forge = True
            elif rate >= _ERROR_RATE_HIGH:
                severity, fix = "HIGH", "retry_config_or_fallback"
                forge = True
            elif count >= 10:
                severity, fix = "MEDIUM", "investigate_root_cause"
                forge = False
            else:
                continue

            issues.append(IssueReport(
                issue_type="error_spike",
                frequency=count,
                severity=severity,
                suggested_fix_type=fix,
                affected_component=f"error:{error_class}",
                forge_trigger=forge,
                details={"error_class": error_class, "count": count, "rate": round(rate, 3)},
            ))
        return issues

    def _analyze_event_patterns(self, stats: dict) -> list[IssueReport]:
        issues = []
        counts = stats.get("event_counts", {})

        # Agent failures
        agent_fail = counts.get("agent:failed", 0)
        if agent_fail >= 5:
            sev = "CRITICAL" if agent_fail >= 20 else "HIGH" if agent_fail >= 10 else "MEDIUM"
            issues.append(IssueReport(
                issue_type="agent_failure_cluster",
                frequency=agent_fail,
                severity=sev,
                suggested_fix_type="agent_config_review",
                affected_component="agents",
                forge_trigger=sev in ("HIGH", "CRITICAL"),
                details={"failure_count": agent_fail},
            ))

        # Forge failures
        forge_fail = counts.get("forge:failed", 0) + counts.get("nb:forge_rejected", 0)
        if forge_fail >= 3:
            issues.append(IssueReport(
                issue_type="forge_failure_pattern",
                frequency=forge_fail,
                severity="HIGH",
                suggested_fix_type="forge_prompt_or_sandbox_review",
                affected_component="forge",
                forge_trigger=False,  # forge can't fix itself this way
                details={"failure_count": forge_fail},
            ))

        # System degraded events
        degraded = counts.get("system:degraded", 0)
        if degraded >= 3:
            issues.append(IssueReport(
                issue_type="system_instability",
                frequency=degraded,
                severity="HIGH",
                suggested_fix_type="health_monitor_threshold_tuning",
                affected_component="system",
                forge_trigger=True,
                details={"degraded_count": degraded},
            ))

        # Security events (rate-limiting often means config issue)
        rate_limited = counts.get("security:rate_limited", 0)
        if rate_limited >= 50:
            issues.append(IssueReport(
                issue_type="rate_limit_saturation",
                frequency=rate_limited,
                severity="MEDIUM",
                suggested_fix_type="rate_limit_threshold_increase",
                affected_component="security:request_guard",
                forge_trigger=False,
                details={"rate_limited_count": rate_limited},
            ))

        return issues

    def _analyze_frequency(self, stats: dict) -> list[IssueReport]:
        """Detect unusual event frequency spikes using 24h frequency data."""
        issues = []
        freq = stats.get("frequency_24h", {})
        if not freq:
            return issues
        for event_type, count in freq.items():
            # Flag events with very high frequency that aren't expected high-volume events
            if event_type in ("nb:reasoning_step", "nb:model_call"):
                continue  # expected high volume
            if count >= 500:
                sev = "CRITICAL" if count >= 2000 else "HIGH"
                issues.append(IssueReport(
                    issue_type="frequency_spike",
                    frequency=count,
                    severity=sev,
                    suggested_fix_type="investigate_event_source",
                    affected_component=f"event:{event_type}",
                    forge_trigger=sev == "CRITICAL",
                    details={"event_type": event_type, "count_24h": count},
                    confidence=0.8,  # frequency alone is less certain
                ))
        return issues

    # ── Unknown pattern logging ───────────────────────────────────────────────

    def _log_unknown(self, stats: dict) -> None:
        """Log any error patterns that don't match known categories."""
        error_counts = stats.get("error_counts", {})
        for ec, count in error_counts.items():
            if ec == "unknown_pattern" and count >= 5:
                logger.warning(
                    "LocalAnalyzer: %d events classified as 'unknown_pattern' — "
                    "consider adding intent rules to sanitizer.py",
                    count,
                )

    # ── AI enhancement (local Ollama only) ───────────────────────────────────

    def _should_use_ai(self) -> bool:
        from neural_brain.config.privacy_mode import get_privacy
        from neural_brain.config.privacy_mode import PrivacyMode
        priv = get_privacy()
        # Only use local AI (Ollama) — never external
        if priv.get_mode() == PrivacyMode.OFFLINE:
            return False
        if not self._ai_checked:
            self._ai_available = self._check_ollama()
            self._ai_checked = True
        return self._ai_available

    @staticmethod
    def _check_ollama() -> bool:
        try:
            import urllib.request
            from neural_brain.config.settings import get_settings
            url = get_settings().ollama_host.rstrip("/") + "/api/tags"
            with urllib.request.urlopen(url, timeout=2):
                return True
        except Exception:
            return False

    def _ai_enhance(self, issues: list[IssueReport], stats: dict) -> list[IssueReport]:
        """Use local SLM to add fix suggestions to existing issues."""
        if not issues:
            return issues
        try:
            from neural_brain.config.settings import get_settings
            settings = get_settings()
            # Build a compact, non-PII prompt (metrics only)
            summary = {
                "issues_found": len(issues),
                "issue_types": [i.issue_type for i in issues],
                "top_errors": list(stats.get("error_counts", {}).items())[:5],
                "latency_stats": stats.get("latency_stats", {}),
            }
            prompt = (
                "You are a system reliability analyzer. Given these metrics (no user data), "
                "suggest specific technical fixes for each issue. Respond in JSON: "
                '[{"issue_type": "...", "suggested_fix_type": "...", "fix_detail": "..."}]\n\n'
                f"Metrics: {json.dumps(summary)}"
            )
            import urllib.request
            payload = json.dumps({
                "model": settings.slm_model,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.1, "num_predict": 300},
            }).encode()
            req = urllib.request.Request(
                settings.ollama_host.rstrip("/") + "/api/generate",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                result = json.loads(resp.read())
            text = result.get("response", "")
            # Parse JSON from response
            start, end = text.find("["), text.rfind("]")
            if start != -1 and end != -1:
                suggestions = json.loads(text[start:end + 1])
                # Merge suggestions into issues
                for issue in issues:
                    for sug in suggestions:
                        if sug.get("issue_type") == issue.issue_type:
                            fix_detail = str(sug.get("fix_detail", ""))[:128]
                            issue.details["ai_suggestion"] = fix_detail
                            if sug.get("suggested_fix_type"):
                                issue.suggested_fix_type = str(sug["suggested_fix_type"])[:64]
                            ai_conf = float(sug.get("confidence", 0.9))
                            issue.confidence = min(issue.confidence, max(0.0, ai_conf))
        except Exception as e:
            logger.debug("LocalAnalyzer AI enhancement failed: %s", e)
        return issues

    # ── Forge trigger ─────────────────────────────────────────────────────────

    def _maybe_trigger_forge(self, issues: list[IssueReport]) -> None:
        forge_issues = [
            i for i in issues
            if i.forge_trigger and i.severity in ("HIGH", "CRITICAL") and i.confidence >= 0.7
        ]
        if not forge_issues:
            return
        try:
            from neural_brain.utils.event_bus import publish
            for issue in forge_issues:
                publish("forge:health_trigger", source="local_analyzer", payload={
                    "issue_type": issue.issue_type,
                    "severity": issue.severity,
                    "affected_component": issue.affected_component,
                    "suggested_fix_type": issue.suggested_fix_type,
                    "details": issue.details,
                })
            logger.info("LocalAnalyzer triggered forge for %d issues", len(forge_issues))
        except Exception as e:
            logger.debug("Forge trigger failed: %s", e)


# ── Singleton ─────────────────────────────────────────────────────────────────
_analyzer: LocalAnalyzer | None = None
_lock = threading.Lock()


def get_local_analyzer() -> LocalAnalyzer:
    global _analyzer
    if _analyzer is None:
        with _lock:
            if _analyzer is None:
                _analyzer = LocalAnalyzer()
    return _analyzer
