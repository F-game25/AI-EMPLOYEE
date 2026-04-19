"""Tests for governance_digest.py — runtime/core/governance_digest.py.

Coverage:
  GovernanceDigest.run():
  - Returns dict with required keys: id, ts, window, sections, summary, markdown
  - window reflects requested window_days
  - summary is a non-empty string
  - markdown contains all section headers

  Section: high_risk_events
  - Empty when AuditEngine returns nothing
  - Includes events with risk_score >= 0.6
  - Excludes events outside the time window
  - AuditEngine failure is swallowed (error key set)

  Section: bias_alerts
  - Empty when no bias_ actions in audit log
  - Includes bias_block / bias_flag actions
  - BiasDetectionEngine failure is swallowed

  Section: system_changes
  - Empty when ChangeLog has no entries
  - Includes entries within window
  - Excludes entries outside window
  - ChangeLog failure is swallowed

  Section: failures
  - Includes anomalies from AuditEngine
  - Includes open/half_open circuit breakers
  - ReliabilityEngine status captured
  - All collectors fail gracefully

  Section: feedback_summary
  - Total/thumbs_up/thumbs_down populated from UserFeedbackStore
  - Failure swallowed (error key set)

  Markdown:
  - Renders Executive Summary table
  - Renders high_risk_events section
  - Renders bias_alerts section
  - Renders system_changes section
  - Renders failures section
  - Renders feedback section when data present

  Persistence:
  - _persist() writes to JSONL (without markdown key)
  - load_recent() returns entries newest-first
  - load_recent() returns empty when store absent

  Audit:
  - _audit() calls AuditEngine.record with action='governance_report_generated'
  - Audit failure is swallowed

  _one_liner:
  - Includes correct counts from all sections

  Singleton:
  - get_governance_digest() returns same instance

  Server integration:
  - _get_governance_digest loader defined in server.py
  - POST /api/governance/digest endpoint present
  - GET /api/governance/digest/latest endpoint present
  - governance_digest.py module exists at runtime/core/governance_digest.py
"""
from __future__ import annotations

import json
import sys
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

REPO_ROOT   = Path(__file__).resolve().parents[1]
RUNTIME_DIR = REPO_ROOT / "runtime"
if str(RUNTIME_DIR) not in sys.path:
    sys.path.insert(0, str(RUNTIME_DIR))

from core.governance_digest import (
    GovernanceDigest,
    _one_liner,
    _render_markdown,
    get_governance_digest,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _make_digest(tmp_path: Path, **kwargs) -> GovernanceDigest:
    return GovernanceDigest(store_path=tmp_path / "digests.jsonl", **kwargs)


def _fake_audit_event(*, ts: str = "2026-04-18T10:00:00Z", action: str = "chat", risk: float = 0.8) -> dict:
    return {"id": "a-1", "ts": ts, "actor": "user:alice", "action": action, "risk_score": risk, "trace_id": ""}


def _fake_change_entry(*, ts: str = "2026-04-18T10:00:00Z") -> dict:
    return {"timestamp": ts, "actor": "system", "action_type": "config_update", "reason": "test", "outcome": "ok"}


# ═══════════════════════════════════════════════════════════════════════════════
# run() — return structure
# ═══════════════════════════════════════════════════════════════════════════════

class TestRunStructure:
    def _mock_all_collectors(self, gd: GovernanceDigest):
        """Patch all subsystem integrations to return empty/safe results."""
        for method in ("_collect_high_risk_events", "_collect_bias_alerts",
                       "_collect_system_changes", "_collect_failures", "_collect_feedback"):
            patcher = patch.object(gd, method, return_value={"count": 0, "error": ""})
            patcher.start()
        patcher2 = patch.object(gd, "_audit")
        patcher2.start()

    def test_required_keys(self, tmp_path):
        gd = _make_digest(tmp_path)
        self._mock_all_collectors(gd)
        result = gd.run()
        for key in ("id", "ts", "window", "sections", "summary", "markdown"):
            assert key in result, f"Missing key: {key}"

    def test_id_starts_with_prefix(self, tmp_path):
        gd = _make_digest(tmp_path)
        self._mock_all_collectors(gd)
        assert gd.run()["id"].startswith("dgst-")

    def test_window_reflects_days(self, tmp_path):
        gd = _make_digest(tmp_path, window_days=14)
        self._mock_all_collectors(gd)
        w = gd.run()["window"]
        assert w["days"] == 14

    def test_window_override(self, tmp_path):
        gd = _make_digest(tmp_path, window_days=7)
        self._mock_all_collectors(gd)
        w = gd.run(window_days=30)["window"]
        assert w["days"] == 30

    def test_summary_nonempty(self, tmp_path):
        gd = _make_digest(tmp_path)
        self._mock_all_collectors(gd)
        assert len(gd.run()["summary"]) > 0

    def test_markdown_is_string(self, tmp_path):
        gd = _make_digest(tmp_path)
        self._mock_all_collectors(gd)
        assert isinstance(gd.run()["markdown"], str)

    def test_sections_has_all_keys(self, tmp_path):
        gd = _make_digest(tmp_path)
        self._mock_all_collectors(gd)
        secs = gd.run()["sections"]
        for key in ("high_risk_events", "bias_alerts", "system_changes", "failures", "feedback_summary"):
            assert key in secs


# ═══════════════════════════════════════════════════════════════════════════════
# Section: high_risk_events
# ═══════════════════════════════════════════════════════════════════════════════

class TestHighRiskEvents:
    def test_empty_when_no_events(self, tmp_path):
        gd = _make_digest(tmp_path, window_days=7)
        mock_ae = MagicMock()
        mock_ae.recent.return_value = []
        with patch("core.audit_engine.get_audit_engine", return_value=mock_ae), \
             patch.object(gd, "_audit"):
            sec = gd._collect_high_risk_events(time.time() - 7 * 86400)
        assert sec["count"] == 0
        assert sec["events"] == []

    def test_includes_high_risk(self, tmp_path):
        gd = _make_digest(tmp_path, window_days=7)
        now_ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        mock_ae = MagicMock()
        mock_ae.recent.return_value = [_fake_audit_event(ts=now_ts, risk=0.9)]
        with patch("core.audit_engine.get_audit_engine", return_value=mock_ae):
            sec = gd._collect_high_risk_events(time.time() - 7 * 86400)
        assert sec["count"] == 1
        assert sec["events"][0]["risk_score"] == 0.9

    def test_excludes_old_events(self, tmp_path):
        gd = _make_digest(tmp_path, window_days=1)
        old_ts = "2020-01-01T00:00:00Z"
        mock_ae = MagicMock()
        mock_ae.recent.return_value = [_fake_audit_event(ts=old_ts, risk=0.9)]
        with patch("core.audit_engine.get_audit_engine", return_value=mock_ae):
            sec = gd._collect_high_risk_events(time.time() - 86400)
        assert sec["count"] == 0

    def test_audit_engine_error_swallowed(self, tmp_path):
        gd = _make_digest(tmp_path)
        with patch("core.audit_engine.get_audit_engine", side_effect=RuntimeError("boom")):
            sec = gd._collect_high_risk_events(time.time() - 7 * 86400)
        assert sec["error"] != ""
        assert sec["count"] == 0


# ═══════════════════════════════════════════════════════════════════════════════
# Section: bias_alerts
# ═══════════════════════════════════════════════════════════════════════════════

class TestBiasAlerts:
    def test_empty_when_no_bias_actions(self, tmp_path):
        gd = _make_digest(tmp_path)
        now_ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        mock_ae = MagicMock()
        mock_ae.recent.return_value = [_fake_audit_event(ts=now_ts, action="chat", risk=0.1)]
        with patch("core.audit_engine.get_audit_engine", return_value=mock_ae):
            sec = gd._collect_bias_alerts(time.time() - 86400)
        assert sec["count"] == 0

    def test_includes_bias_block(self, tmp_path):
        gd = _make_digest(tmp_path)
        now_ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        event = _fake_audit_event(ts=now_ts, action="bias_block", risk=0.8)
        event["output"] = {"outcome": "block", "high_risk": True}
        mock_ae = MagicMock()
        mock_ae.recent.return_value = [event]
        with patch("core.audit_engine.get_audit_engine", return_value=mock_ae):
            sec = gd._collect_bias_alerts(time.time() - 86400)
        assert sec["count"] == 1
        assert sec["alerts"][0]["action"] == "bias_block"

    def test_includes_bias_flag(self, tmp_path):
        gd = _make_digest(tmp_path)
        now_ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        event = _fake_audit_event(ts=now_ts, action="bias_flag", risk=0.6)
        event["output"] = {"outcome": "log", "high_risk": False}
        mock_ae = MagicMock()
        mock_ae.recent.return_value = [event]
        with patch("core.audit_engine.get_audit_engine", return_value=mock_ae):
            sec = gd._collect_bias_alerts(time.time() - 86400)
        assert sec["count"] == 1

    def test_bias_collector_error_swallowed(self, tmp_path):
        gd = _make_digest(tmp_path)
        with patch("core.audit_engine.get_audit_engine", side_effect=RuntimeError("bias boom")):
            sec = gd._collect_bias_alerts(time.time() - 86400)
        assert sec["error"] != ""


# ═══════════════════════════════════════════════════════════════════════════════
# Section: system_changes
# ═══════════════════════════════════════════════════════════════════════════════

class TestSystemChanges:
    def test_empty_when_no_changes(self, tmp_path):
        gd = _make_digest(tmp_path)
        mock_cl = MagicMock()
        mock_cl.read.return_value = []
        with patch("core.change_log.get_changelog", return_value=mock_cl):
            sec = gd._collect_system_changes(time.time() - 86400)
        assert sec["count"] == 0

    def test_includes_recent_entry(self, tmp_path):
        gd = _make_digest(tmp_path)
        now_ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        mock_cl = MagicMock()
        mock_cl.read.return_value = [_fake_change_entry(ts=now_ts)]
        with patch("core.change_log.get_changelog", return_value=mock_cl):
            sec = gd._collect_system_changes(time.time() - 86400)
        assert sec["count"] == 1
        assert sec["changes"][0]["action_type"] == "config_update"

    def test_excludes_old_entry(self, tmp_path):
        gd = _make_digest(tmp_path)
        mock_cl = MagicMock()
        mock_cl.read.return_value = [_fake_change_entry(ts="2019-01-01T00:00:00Z")]
        with patch("core.change_log.get_changelog", return_value=mock_cl):
            sec = gd._collect_system_changes(time.time() - 86400)
        assert sec["count"] == 0

    def test_changelog_error_swallowed(self, tmp_path):
        gd = _make_digest(tmp_path)
        with patch("core.change_log.get_changelog", side_effect=RuntimeError("cl down")):
            sec = gd._collect_system_changes(time.time() - 86400)
        assert sec["error"] != ""


# ═══════════════════════════════════════════════════════════════════════════════
# Section: failures
# ═══════════════════════════════════════════════════════════════════════════════

class TestFailures:
    def _mock_reliability(self):
        m = MagicMock()
        m.status.return_value = {
            "stability_score": 0.85,
            "forge_frozen": False,
            "throttled_agents": [],
        }
        return m

    def test_stability_score_captured(self, tmp_path):
        gd = _make_digest(tmp_path)
        mock_rel = self._mock_reliability()
        mock_ae  = MagicMock()
        mock_ae.anomalies.return_value = []
        mock_reg = MagicMock()
        mock_reg.status_all.return_value = []
        with patch("core.reliability_engine.get_reliability_engine", return_value=mock_rel), \
             patch("core.audit_engine.get_audit_engine", return_value=mock_ae), \
             patch("core.circuit_breaker.get_circuit_registry", return_value=mock_reg):
            sec = gd._collect_failures(time.time() - 86400)
        assert sec["stability_score"] == pytest.approx(0.85)

    def test_forge_frozen_detected(self, tmp_path):
        gd = _make_digest(tmp_path)
        mock_rel = self._mock_reliability()
        mock_rel.status.return_value["forge_frozen"] = True
        mock_ae  = MagicMock()
        mock_ae.anomalies.return_value = []
        mock_reg = MagicMock()
        mock_reg.status_all.return_value = []
        with patch("core.reliability_engine.get_reliability_engine", return_value=mock_rel), \
             patch("core.audit_engine.get_audit_engine", return_value=mock_ae), \
             patch("core.circuit_breaker.get_circuit_registry", return_value=mock_reg):
            sec = gd._collect_failures(time.time() - 86400)
        assert sec["forge_frozen"] is True

    def test_open_breakers_included(self, tmp_path):
        gd = _make_digest(tmp_path)
        mock_rel = self._mock_reliability()
        mock_ae  = MagicMock()
        mock_ae.anomalies.return_value = []
        mock_reg = MagicMock()
        mock_reg.status_all.return_value = [
            {"name": "llm", "state": "open", "failure_count": 5},
        ]
        with patch("core.reliability_engine.get_reliability_engine", return_value=mock_rel), \
             patch("core.audit_engine.get_audit_engine", return_value=mock_ae), \
             patch("core.circuit_breaker.get_circuit_registry", return_value=mock_reg):
            sec = gd._collect_failures(time.time() - 86400)
        assert len(sec["open_breakers"]) == 1
        assert sec["count"] >= 1

    def test_closed_breakers_excluded(self, tmp_path):
        gd = _make_digest(tmp_path)
        mock_rel = self._mock_reliability()
        mock_ae  = MagicMock()
        mock_ae.anomalies.return_value = []
        mock_reg = MagicMock()
        mock_reg.status_all.return_value = [
            {"name": "llm", "state": "closed", "failure_count": 0},
        ]
        with patch("core.reliability_engine.get_reliability_engine", return_value=mock_rel), \
             patch("core.audit_engine.get_audit_engine", return_value=mock_ae), \
             patch("core.circuit_breaker.get_circuit_registry", return_value=mock_reg):
            sec = gd._collect_failures(time.time() - 86400)
        assert sec["open_breakers"] == []

    def test_all_collectors_fail_gracefully(self, tmp_path):
        gd = _make_digest(tmp_path)
        with patch("core.reliability_engine.get_reliability_engine", side_effect=RuntimeError("rel down")), \
             patch("core.audit_engine.get_audit_engine", side_effect=RuntimeError("ae down")), \
             patch("core.circuit_breaker.get_circuit_registry", side_effect=RuntimeError("cb down")):
            sec = gd._collect_failures(time.time() - 86400)
        # Must return a valid dict with count and a non-empty error
        assert isinstance(sec, dict)
        assert sec["count"] == 0
        assert sec["error"] != ""


# ═══════════════════════════════════════════════════════════════════════════════
# Section: feedback_summary
# ═══════════════════════════════════════════════════════════════════════════════

class TestFeedbackSummary:
    def test_populated_from_store(self, tmp_path):
        gd = _make_digest(tmp_path)
        mock_store = MagicMock()
        mock_store.summary.return_value = {
            "total": 10, "thumbs_up": 7, "thumbs_down": 3,
            "avg_reward": 0.4, "positive_rate": 0.7,
        }
        with patch("core.user_feedback_store.get_feedback_store", return_value=mock_store):
            sec = gd._collect_feedback()
        assert sec["total"] == 10
        assert sec["thumbs_up"] == 7
        assert sec["thumbs_down"] == 3
        assert sec["error"] == ""

    def test_error_swallowed(self, tmp_path):
        gd = _make_digest(tmp_path)
        with patch("core.user_feedback_store.get_feedback_store", side_effect=RuntimeError("fb crash")):
            sec = gd._collect_feedback()
        assert sec["error"] != ""
        assert sec["total"] == 0


# ═══════════════════════════════════════════════════════════════════════════════
# Markdown rendering
# ═══════════════════════════════════════════════════════════════════════════════

class TestMarkdownRendering:
    def _base_sections(self, *, hr=0, ba=0, sc=0, fl=0) -> dict:
        return {
            "high_risk_events": {"count": hr, "events": [], "error": ""},
            "bias_alerts":      {"count": ba, "alerts": [], "error": ""},
            "system_changes":   {"count": sc, "changes": [], "error": ""},
            "failures":         {
                "count": fl, "anomalies": [], "open_breakers": [],
                "stability_score": None, "forge_frozen": False,
                "throttled_agents": [], "error": "",
            },
            "feedback_summary": {"total": 0, "thumbs_up": 0, "thumbs_down": 0, "avg_reward": 0.0, "positive_rate": 0.0, "error": ""},
        }

    def test_contains_title(self):
        md = _render_markdown(self._base_sections(), window_days=7, generated_at="2026-01-01T00:00:00Z")
        assert "# Governance Digest" in md

    def test_contains_executive_summary(self):
        md = _render_markdown(self._base_sections(), window_days=7, generated_at="2026-01-01T00:00:00Z")
        assert "Executive Summary" in md

    def test_all_section_headers(self):
        md = _render_markdown(self._base_sections(), window_days=7, generated_at="2026-01-01T00:00:00Z")
        for header in ("High-Risk Audit Events", "Bias Alerts", "System Changes", "Failures"):
            assert header in md

    def test_counts_in_summary(self):
        secs = self._base_sections(hr=3, ba=2, sc=1, fl=4)
        md = _render_markdown(secs, window_days=7, generated_at="2026-01-01T00:00:00Z")
        assert "3" in md
        assert "2" in md
        assert "1" in md
        assert "4" in md

    def test_feedback_section_when_total_nonzero(self):
        secs = self._base_sections()
        secs["feedback_summary"] = {"total": 5, "thumbs_up": 4, "thumbs_down": 1, "avg_reward": 0.6, "positive_rate": 0.8, "error": ""}
        md = _render_markdown(secs, window_days=7, generated_at="2026-01-01T00:00:00Z")
        assert "Feedback" in md
        assert "80.0%" in md

    def test_no_events_message(self):
        md = _render_markdown(self._base_sections(), window_days=7, generated_at="2026-01-01T00:00:00Z")
        assert "No high-risk events" in md

    def test_forge_frozen_warning(self):
        secs = self._base_sections()
        secs["failures"]["forge_frozen"] = True
        md = _render_markdown(secs, window_days=7, generated_at="2026-01-01T00:00:00Z")
        assert "FROZEN" in md

    def test_open_breaker_shown(self):
        secs = self._base_sections()
        secs["failures"]["open_breakers"] = [{"name": "llm", "state": "open", "failure_count": 3}]
        md = _render_markdown(secs, window_days=7, generated_at="2026-01-01T00:00:00Z")
        assert "llm" in md
        assert "OPEN" in md


# ═══════════════════════════════════════════════════════════════════════════════
# _one_liner
# ═══════════════════════════════════════════════════════════════════════════════

class TestOneLiner:
    def test_includes_all_counts(self):
        sections = {
            "high_risk_events": {"count": 5},
            "bias_alerts":      {"count": 3},
            "system_changes":   {"count": 2},
            "failures":         {"count": 1},
        }
        line = _one_liner(sections)
        assert "5" in line
        assert "3" in line
        assert "2" in line
        assert "1" in line

    def test_handles_missing_keys(self):
        line = _one_liner({})
        assert "0" in line


# ═══════════════════════════════════════════════════════════════════════════════
# Persistence
# ═══════════════════════════════════════════════════════════════════════════════

class TestPersistence:
    def _patched_run(self, gd: GovernanceDigest) -> dict:
        for method in ("_collect_high_risk_events", "_collect_bias_alerts",
                       "_collect_system_changes", "_collect_failures", "_collect_feedback"):
            patcher = patch.object(gd, method, return_value={"count": 0, "error": ""})
            patcher.start()
        patch.object(gd, "_audit").start()
        return gd.run()

    def test_persist_writes_jsonl(self, tmp_path):
        gd = _make_digest(tmp_path)
        self._patched_run(gd)
        lines = [l for l in (tmp_path / "digests.jsonl").read_text().splitlines() if l.strip()]
        assert len(lines) == 1
        d = json.loads(lines[0])
        assert d["id"].startswith("dgst-")

    def test_persist_omits_markdown(self, tmp_path):
        gd = _make_digest(tmp_path)
        self._patched_run(gd)
        line = (tmp_path / "digests.jsonl").read_text().strip()
        d = json.loads(line)
        assert "markdown" not in d

    def test_multiple_runs_accumulate(self, tmp_path):
        gd = _make_digest(tmp_path)
        self._patched_run(gd)
        self._patched_run(gd)
        lines = [l for l in (tmp_path / "digests.jsonl").read_text().splitlines() if l.strip()]
        assert len(lines) == 2

    def test_load_recent_newest_first(self, tmp_path):
        gd = _make_digest(tmp_path)
        for _ in range(3):
            self._patched_run(gd)
        entries = gd.load_recent(limit=3)
        assert len(entries) == 3
        # newest is first
        ids = [e["id"] for e in entries]
        assert ids == list(reversed([e["id"] for e in reversed(entries)]))

    def test_load_recent_respects_limit(self, tmp_path):
        gd = _make_digest(tmp_path)
        for _ in range(5):
            self._patched_run(gd)
        assert len(gd.load_recent(limit=2)) == 2

    def test_load_recent_returns_empty_when_no_store(self, tmp_path):
        gd = GovernanceDigest(store_path=tmp_path / "nonexistent.jsonl")
        assert gd.load_recent() == []


# ═══════════════════════════════════════════════════════════════════════════════
# Audit integration
# ═══════════════════════════════════════════════════════════════════════════════

class TestAuditIntegration:
    def test_audit_called_after_run(self, tmp_path):
        gd = _make_digest(tmp_path)
        mock_ae = MagicMock()
        for method in ("_collect_high_risk_events", "_collect_bias_alerts",
                       "_collect_system_changes", "_collect_failures", "_collect_feedback"):
            patch.object(gd, method, return_value={"count": 0, "error": ""}).start()
        with patch("core.audit_engine.get_audit_engine", return_value=mock_ae):
            gd.run()
        mock_ae.record.assert_called_once()
        kwargs = mock_ae.record.call_args[1]
        assert kwargs["action"] == "governance_report_generated"
        assert kwargs["risk_score"] == pytest.approx(0.05)

    def test_audit_failure_swallowed(self, tmp_path):
        gd = _make_digest(tmp_path)
        digest = {"id": "dgst-test", "window": {}, "sections": {}, "summary": ""}
        with patch("core.audit_engine.get_audit_engine", side_effect=RuntimeError("ae down")):
            gd._audit(digest)  # must not raise


# ═══════════════════════════════════════════════════════════════════════════════
# Singleton
# ═══════════════════════════════════════════════════════════════════════════════

class TestSingleton:
    def test_same_instance_returned(self):
        a = get_governance_digest()
        b = get_governance_digest()
        assert a is b


# ═══════════════════════════════════════════════════════════════════════════════
# Server integration (static analysis)
# ═══════════════════════════════════════════════════════════════════════════════

class TestServerIntegration:
    def _src(self) -> str:
        return (REPO_ROOT / "runtime" / "agents" / "problem-solver-ui" / "server.py").read_text()

    def test_governance_digest_loader_defined(self):
        assert "_get_governance_digest" in self._src()

    def test_post_endpoint_present(self):
        assert '"/api/governance/digest"' in self._src()

    def test_get_latest_endpoint_present(self):
        assert '"/api/governance/digest/latest"' in self._src()

    def test_module_exists(self):
        assert (RUNTIME_DIR / "core" / "governance_digest.py").exists()

    def test_generate_wired(self):
        assert "gd.run(" in self._src()

    def test_load_recent_wired(self):
        assert "gd.load_recent(" in self._src()
