"""Tests for the bias detection and mitigation engine.

Covers:
  - Metric calculations: demographic parity, equalized odds, disparate impact
  - Pipeline outcomes: approve / log / block
  - AuditEngine integration
  - BiasDetectionEngine API: check(), report_for_agent(), is_checked_agent()
  - Server.py: lazy loader, bias API endpoints registered
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_DIR = REPO_ROOT / "runtime"

if str(RUNTIME_DIR) not in sys.path:
    sys.path.insert(0, str(RUNTIME_DIR))

from core.bias_detection_engine import (
    BiasCheckContext,
    BiasDetectionEngine,
    BiasReport,
    GroupStats,
    _GroupStore,
    _demographic_parity,
    _disparate_impact,
    _equalized_odds,
    _compute_bias_risk,
    get_bias_engine,
    BIAS_CHECKED_AGENTS,
    DI_BLOCK_THRESHOLD,
    DI_LOG_THRESHOLD,
    DP_DIFF_LOG_THRESHOLD,
)


# ═══════════════════════════════════════════════════════════════════════════════
# GroupStats properties
# ═══════════════════════════════════════════════════════════════════════════════

class TestGroupStats:
    def test_selection_rate_zero_when_no_observations(self):
        s = GroupStats(group="a")
        assert s.selection_rate == 0.0

    def test_selection_rate_computed_correctly(self):
        s = GroupStats(group="a", n=10, n_positive=4)
        assert s.selection_rate == pytest.approx(0.4)

    def test_tpr_zero_when_no_labels(self):
        s = GroupStats(group="a", n=10, n_positive=5)
        assert s.tpr == 0.0

    def test_tpr_computed(self):
        s = GroupStats(group="a", n_true_positive=8, n_false_negative=2)
        assert s.tpr == pytest.approx(0.8)

    def test_fpr_computed(self):
        s = GroupStats(group="a", n_false_positive=1, n_true_negative=9)
        assert s.fpr == pytest.approx(0.1)


# ═══════════════════════════════════════════════════════════════════════════════
# Metric helpers
# ═══════════════════════════════════════════════════════════════════════════════

class TestDemographicParity:
    def _groups(self, rate_a: float, rate_b: float, n: int = 100) -> dict:
        return {
            "a": GroupStats(group="a", n=n, n_positive=int(rate_a * n)),
            "b": GroupStats(group="b", n=n, n_positive=int(rate_b * n)),
        }

    def test_returns_empty_when_insufficient_data(self):
        groups = {"a": GroupStats(group="a", n=1), "b": GroupStats(group="b", n=1)}
        assert _demographic_parity(groups) == []

    def test_perfect_parity_gives_zero_diff(self):
        results = _demographic_parity(self._groups(0.5, 0.5))
        assert len(results) == 1
        assert results[0]["dp_diff"] == pytest.approx(0.0)
        assert results[0]["dp_ratio"] == pytest.approx(1.0)
        assert results[0]["flagged"] is False

    def test_disparity_above_threshold_is_flagged(self):
        results = _demographic_parity(self._groups(0.8, 0.5))
        assert results[0]["flagged"] is True
        assert results[0]["dp_diff"] == pytest.approx(0.3)

    def test_ratio_is_min_over_max(self):
        results = _demographic_parity(self._groups(0.8, 0.4))
        assert results[0]["dp_ratio"] == pytest.approx(0.5)


class TestEqualizedOdds:
    def _groups(self) -> dict:
        # Group A: perfect TPR/FPR; Group B: biased
        a = GroupStats(group="a", n_true_positive=8, n_false_negative=2,
                       n_false_positive=1, n_true_negative=9)
        b = GroupStats(group="b", n_true_positive=5, n_false_negative=5,
                       n_false_positive=4, n_true_negative=6)
        return {"a": a, "b": b}

    def test_no_results_when_no_ground_truth(self):
        groups = {
            "a": GroupStats(group="a", n=10, n_positive=5),
            "b": GroupStats(group="b", n=10, n_positive=3),
        }
        assert _equalized_odds(groups) == []

    def test_tpr_diff_computed(self):
        results = _equalized_odds(self._groups())
        assert len(results) == 1
        r = results[0]
        assert r["tpr_diff"] == pytest.approx(abs(0.8 - 0.5))

    def test_flagged_when_diff_above_threshold(self):
        results = _equalized_odds(self._groups())
        assert results[0]["flagged"] is True


class TestDisparateImpact:
    def _groups(self, rates: list[tuple[str, float]], n: int = 100) -> dict:
        return {
            name: GroupStats(group=name, n=n, n_positive=int(r * n))
            for name, r in rates
        }

    def test_empty_when_fewer_than_two_groups(self):
        assert _disparate_impact({"a": GroupStats(group="a", n=1)}) == []

    def test_eeoc_rule_below_08_flagged(self):
        groups = self._groups([("a", 1.0), ("b", 0.7)])
        results = _disparate_impact(groups)
        b_result = next(r for r in results if r["group"] == "b")
        assert b_result["eeoc_flagged"] is True
        assert b_result["di_ratio"] == pytest.approx(0.7)

    def test_block_recommended_below_06(self):
        groups = self._groups([("a", 1.0), ("b", 0.5)])
        results = _disparate_impact(groups)
        b_result = next(r for r in results if r["group"] == "b")
        assert b_result["block_recommended"] is True

    def test_no_block_when_di_above_threshold(self):
        groups = self._groups([("a", 1.0), ("b", 0.9)])
        results = _disparate_impact(groups)
        for r in results:
            assert r["block_recommended"] is False

    def test_reference_group_has_di_one(self):
        groups = self._groups([("a", 1.0), ("b", 0.8)])
        results = _disparate_impact(groups)
        a_result = next(r for r in results if r["group"] == "a")
        assert a_result["di_ratio"] == pytest.approx(1.0)


class TestBiasRiskScore:
    def test_zero_risk_when_no_signals(self):
        assert _compute_bias_risk([], [], []) == 0.0

    def test_risk_above_zero_with_flagged_di(self):
        groups = {
            "a": GroupStats(group="a", n=100, n_positive=100),
            "b": GroupStats(group="b", n=100, n_positive=50),
        }
        di = _disparate_impact(groups)
        risk = _compute_bias_risk([], di, [])
        assert risk > 0.0

    def test_risk_capped_at_one(self):
        dp = [{"dp_diff": 999.0}]
        di = [{"di_ratio": 0.0}]
        eo = [{"tpr_diff": 999.0, "fpr_diff": 999.0}]
        risk = _compute_bias_risk(dp, di, eo)
        assert risk <= 1.0


# ═══════════════════════════════════════════════════════════════════════════════
# GroupStore
# ═══════════════════════════════════════════════════════════════════════════════

class TestGroupStore:
    def test_records_decisions(self):
        store = _GroupStore()
        store.record("recruiter", "group_a", True)
        store.record("recruiter", "group_a", False)
        store.record("recruiter", "group_b", True)
        stats = store.get_stats("recruiter")
        assert stats["group_a"].n == 2
        assert stats["group_a"].n_positive == 1
        assert stats["group_b"].n_positive == 1

    def test_empty_stats_for_unknown_agent(self):
        store = _GroupStore()
        assert store.get_stats("unknown-agent") == {}

    def test_snapshot_contains_selection_rates(self):
        store = _GroupStore()
        for _ in range(4):
            store.record("lead-scorer", "group_a", True)
        for _ in range(4):
            store.record("lead-scorer", "group_a", False)
        snap = store.snapshot("lead-scorer")
        assert snap["group_a"]["selection_rate"] == pytest.approx(0.5)

    def test_ground_truth_accumulates(self):
        store = _GroupStore()
        store.record("recruiter", "g", True, ground_truth=True)   # TP
        store.record("recruiter", "g", True, ground_truth=False)  # FP
        stats = store.get_stats("recruiter")
        assert stats["g"].n_true_positive == 1
        assert stats["g"].n_false_positive == 1


# ═══════════════════════════════════════════════════════════════════════════════
# BiasDetectionEngine
# ═══════════════════════════════════════════════════════════════════════════════

class TestBiasDetectionEngine:
    def _engine(self) -> BiasDetectionEngine:
        return BiasDetectionEngine()

    def _ctx(self, agent="recruiter", group="group_a", decision=True) -> BiasCheckContext:
        return BiasCheckContext(
            agent=agent,
            action="rank_candidate",
            subject_id="s-1",
            decision=decision,
            demographic_group=group,
        )

    # ── is_checked_agent ──────────────────────────────────────────────────────

    def test_bias_checked_agents_require_check(self):
        engine = self._engine()
        for agent in BIAS_CHECKED_AGENTS:
            assert engine.is_checked_agent(agent) is True

    def test_normal_agents_not_checked(self):
        engine = self._engine()
        assert engine.is_checked_agent("brand-strategist") is False
        assert engine.is_checked_agent("newsletter-bot") is False

    def test_profiling_action_triggers_check(self):
        engine = self._engine()
        assert engine.is_checked_agent("some-agent", action="profile user data") is True

    # ── check() — single decision ──────────────────────────────────────────────

    def test_check_returns_bias_report(self):
        engine = self._engine()
        report = engine.check(self._ctx())
        assert isinstance(report, BiasReport)
        assert report.outcome in ("approve", "log", "block")

    def test_check_approves_single_decision(self):
        """With only one group and one decision, no disparity is measurable → approve."""
        engine = self._engine()
        report = engine.check(self._ctx())
        assert report.outcome == "approve"

    def test_check_accumulates_across_calls(self):
        engine = self._engine()
        for _ in range(20):
            engine.check(self._ctx(group="group_a", decision=True))
        for _ in range(20):
            engine.check(self._ctx(group="group_b", decision=False))
        # Strong disparity: group_a 100% positive, group_b 0%
        report = engine.check(self._ctx(group="group_b", decision=False))
        # Should be flagged (log or block)
        assert report.outcome in ("log", "block")

    def test_check_blocks_on_severe_disparate_impact(self):
        engine = self._engine()
        # Create severe DI: group_a always positive (selection_rate=1.0),
        # group_b always negative (selection_rate ≈ 0 → DI < 0.6 → block)
        for _ in range(50):
            engine.check(BiasCheckContext(
                agent="lead-scorer", action="score_lead",
                subject_id="x", decision=True, demographic_group="majority",
            ))
        for _ in range(50):
            engine.check(BiasCheckContext(
                agent="lead-scorer", action="score_lead",
                subject_id="y", decision=False, demographic_group="minority",
            ))
        report = engine.check(BiasCheckContext(
            agent="lead-scorer", action="score_lead",
            subject_id="z", decision=False, demographic_group="minority",
        ))
        assert report.outcome == "block"
        assert report.high_risk is True

    def test_check_includes_metrics_when_multiple_groups(self):
        engine = self._engine()
        for _ in range(5):
            engine.check(self._ctx(group="a", decision=True))
        for _ in range(5):
            engine.check(self._ctx(group="b", decision=False))
        report = engine.check(self._ctx(group="a"))
        assert len(report.metrics) > 0

    def test_check_report_has_audit_risk_score(self):
        engine = self._engine()
        report = engine.check(self._ctx())
        assert 0.0 <= report.audit_risk_score <= 1.0

    def test_check_report_has_check_id(self):
        engine = self._engine()
        report = engine.check(self._ctx())
        assert report.check_id.startswith("bias-")

    def test_check_report_has_summary(self):
        engine = self._engine()
        report = engine.check(self._ctx())
        assert len(report.summary) > 0

    def test_to_dict_serialisable(self):
        engine = self._engine()
        report = engine.check(self._ctx())
        d = report.to_dict()
        import json
        json.dumps(d)  # must not raise

    # ── report_for_agent() ────────────────────────────────────────────────────

    def test_report_for_agent_returns_dict(self):
        engine = self._engine()
        result = engine.report_for_agent("recruiter")
        assert isinstance(result, dict)
        assert "agent" in result
        assert "overall_bias_risk" in result

    def test_report_for_agent_has_correct_agent_name(self):
        engine = self._engine()
        result = engine.report_for_agent("lead-scorer")
        assert result["agent"] == "lead-scorer"

    def test_report_for_agent_includes_metric_sections(self):
        engine = self._engine()
        for g in ("a", "b"):
            for _ in range(5):
                engine.check(BiasCheckContext(
                    agent="recruiter", action="hire",
                    subject_id="s", decision=(g == "a"),
                    demographic_group=g,
                ))
        result = engine.report_for_agent("recruiter")
        assert "demographic_parity" in result
        assert "equalized_odds" in result
        assert "disparate_impact" in result
        assert "group_snapshot" in result

    # ── Singleton ─────────────────────────────────────────────────────────────

    def test_singleton_returns_same_instance(self):
        a = get_bias_engine()
        b = get_bias_engine()
        assert a is b


# ═══════════════════════════════════════════════════════════════════════════════
# Server.py integration checks (static analysis — no server start)
# ═══════════════════════════════════════════════════════════════════════════════

class TestServerBiasIntegration:
    """Verify bias engine is wired into server.py without starting the server."""

    def _src(self) -> str:
        return (REPO_ROOT / "runtime" / "agents" / "problem-solver-ui" / "server.py").read_text()

    def test_get_bias_engine_loader_defined(self):
        assert "_get_bias_engine" in self._src()

    def test_bias_engine_imported_via_lazy_loader(self):
        src = self._src()
        assert "bias_detection_engine" in src

    def test_bias_check_wired_in_handle_command(self):
        src = self._src()
        assert "_bias.is_checked_agent" in src

    def test_bias_block_outcome_handled(self):
        src = self._src()
        assert "bias_block" in src
        assert "Bias Detection" in src

    def test_bias_report_endpoint_registered(self):
        src = self._src()
        assert '"/api/bias/report/{agent_id}"' in src

    def test_bias_events_endpoint_registered(self):
        src = self._src()
        assert '"/api/bias/events"' in src

    def test_bias_check_endpoint_registered(self):
        src = self._src()
        assert '"/api/bias/check"' in src

    def test_bias_module_file_exists(self):
        assert (RUNTIME_DIR / "core" / "bias_detection_engine.py").exists()

    def test_bias_block_audit_logged(self):
        src = self._src()
        assert "bias_block" in src
        assert "_audit_logger.warning" in src

    def test_bias_high_risk_audit_logged(self):
        src = self._src()
        assert "bias_high_risk" in src
