"""Bias Detection & Mitigation Engine.

ML fairness module for ASCEND AI — EU AI Act / EEOC compliance.

────────────────────────────────────────────────────────────────
METRICS IMPLEMENTED
────────────────────────────────────────────────────────────────

1. Demographic Parity (DP)
   The positive-decision rate should be equal across groups.
   DP difference  = |P(Ŷ=1|A=0) − P(Ŷ=1|A=1)|
   DP ratio       = min(P(Ŷ=1|A=a)) / max(P(Ŷ=1|A=a))

2. Equalized Odds (EO)
   Both TPR (true positive rate) and FPR (false positive rate)
   should be equal across groups.
   EO TPR diff = |TPR_A0 − TPR_A1|
   EO FPR diff = |FPR_A0 − FPR_A1|

3. Disparate Impact (DI)   — EEOC "4/5ths rule"
   DI ratio = (lowest selection rate) / (highest selection rate)
   DI < 0.8 is flagged as adverse impact.

────────────────────────────────────────────────────────────────
PIPELINE
────────────────────────────────────────────────────────────────

  input → BiasCheckContext → BiasEngine.check() → BiasReport
    ↳ outcome: APPROVE | BLOCK | LOG
    ↳ stored in AuditEngine
    ↳ high-risk events flagged separately

────────────────────────────────────────────────────────────────
INTEGRATION
────────────────────────────────────────────────────────────────

Agents that trigger bias checks automatically:
  - lead-scorer
  - qualification-agent
  - lead-intelligence
  - lead-hunter-elite
  - recruiter
  - hr-manager
  - customer-profiling (any agent whose action contains "profil")

Design constraints
  - Pure Python stdlib only (no numpy/sklearn required).
  - Thread-safe (RLock around shared state).
  - Async-compatible: all public methods are synchronous but safe to
    call from asyncio.run_in_threadpool().
  - Non-breaking: importing or calling this module never raises —
    all errors are caught and surfaced as BiasReport.error fields.
"""
from __future__ import annotations

import math
import threading
import time
import uuid
from dataclasses import dataclass, field, asdict
from typing import Any

# ── Thresholds ────────────────────────────────────────────────────────────────

# Disparate impact below this ratio triggers a BLOCK.
DI_BLOCK_THRESHOLD: float = float(
    __import__("os").environ.get("BIAS_DI_BLOCK_THRESHOLD", "0.6")
)
# Disparate impact below this (but above BLOCK) triggers a LOG.
DI_LOG_THRESHOLD: float = float(
    __import__("os").environ.get("BIAS_DI_LOG_THRESHOLD", "0.8")
)
# Demographic parity difference above this triggers a LOG.
DP_DIFF_LOG_THRESHOLD: float = float(
    __import__("os").environ.get("BIAS_DP_DIFF_THRESHOLD", "0.1")
)
# Equalized odds difference above this triggers a LOG.
EO_DIFF_LOG_THRESHOLD: float = float(
    __import__("os").environ.get("BIAS_EO_DIFF_THRESHOLD", "0.1")
)

# Agents that always go through bias checking
BIAS_CHECKED_AGENTS: frozenset[str] = frozenset({
    "lead-scorer",
    "qualification-agent",
    "lead-intelligence",
    "lead-hunter-elite",
    "recruiter",
    "hr-manager",
})

# Action keywords that also trigger bias checks regardless of agent
BIAS_TRIGGER_ACTIONS: frozenset[str] = frozenset({
    "profil",
    "score_lead",
    "rank_candidate",
    "screen",
    "qualify",
    "hire",
    "reject_candidate",
})


def _ts() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# ── Data structures ───────────────────────────────────────────────────────────

@dataclass
class GroupStats:
    """Observed statistics for one demographic group."""
    group: str
    n: int = 0                     # total observations
    n_positive: int = 0            # positive decisions (Ŷ=1)
    n_true_positive: int = 0       # TP: Ŷ=1, Y=1
    n_false_positive: int = 0      # FP: Ŷ=1, Y=0
    n_true_negative: int = 0       # TN: Ŷ=0, Y=0
    n_false_negative: int = 0      # FN: Ŷ=0, Y=1

    @property
    def selection_rate(self) -> float:
        """P(Ŷ=1 | A=group)"""
        return self.n_positive / self.n if self.n > 0 else 0.0

    @property
    def tpr(self) -> float:
        """True positive rate  TP / (TP + FN)"""
        denom = self.n_true_positive + self.n_false_negative
        return self.n_true_positive / denom if denom > 0 else 0.0

    @property
    def fpr(self) -> float:
        """False positive rate  FP / (FP + TN)"""
        denom = self.n_false_positive + self.n_true_negative
        return self.n_false_positive / denom if denom > 0 else 0.0


@dataclass
class BiasMetrics:
    """Computed fairness metrics for a pair of demographic groups."""
    reference_group: str
    comparison_group: str
    # Demographic parity
    dp_diff: float = 0.0           # |P(Ŷ=1|ref) − P(Ŷ=1|cmp)|
    dp_ratio: float = 1.0          # min / max selection rate
    # Equalized odds
    tpr_diff: float = 0.0
    fpr_diff: float = 0.0
    # Disparate impact (EEOC 4/5ths rule)
    di_ratio: float = 1.0
    # Aggregated risk
    bias_risk_score: float = 0.0   # 0.0 (fair) – 1.0 (severely biased)


@dataclass
class BiasCheckContext:
    """Input to a single bias check."""
    agent: str
    action: str
    subject_id: str                         # person / entity being evaluated
    decision: bool                          # True = positive (hire/accept/qualify)
    demographic_group: str                  # group label for the subject
    ground_truth: bool | None = None        # actual label (Y), if known
    metadata: dict[str, Any] = field(default_factory=dict)
    session_id: str = field(default_factory=lambda: uuid.uuid4().hex[:10])


@dataclass
class BiasReport:
    """Full output of one bias check pipeline run."""
    check_id: str = field(default_factory=lambda: f"bias-{uuid.uuid4().hex[:10]}")
    ts: str = field(default_factory=_ts)
    agent: str = ""
    action: str = ""
    subject_id: str = ""
    demographic_group: str = ""
    decision: bool = False
    # Pipeline outcome
    outcome: str = "approve"               # approve | block | log
    # Metrics (may be empty if insufficient data)
    metrics: list[dict[str, Any]] = field(default_factory=list)
    # Human-readable summary
    summary: str = ""
    # Set to True when the event is considered high-risk bias
    high_risk: bool = False
    # Non-fatal error message (if check partially failed)
    error: str = ""
    # Risk score stored in AuditEngine
    audit_risk_score: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ── Metric calculation helpers ────────────────────────────────────────────────

def _demographic_parity(groups: dict[str, GroupStats]) -> list[dict[str, Any]]:
    """Compute demographic parity between every pair of groups."""
    results = []
    group_list = list(groups.values())
    for i in range(len(group_list)):
        for j in range(i + 1, len(group_list)):
            g1, g2 = group_list[i], group_list[j]
            if g1.n < 2 or g2.n < 2:
                continue
            dp_diff = abs(g1.selection_rate - g2.selection_rate)
            rates = [g1.selection_rate, g2.selection_rate]
            max_r = max(rates)
            dp_ratio = min(rates) / max_r if max_r > 0 else 1.0
            results.append({
                "metric": "demographic_parity",
                "group_a": g1.group,
                "group_b": g2.group,
                "rate_a": round(g1.selection_rate, 4),
                "rate_b": round(g2.selection_rate, 4),
                "dp_diff": round(dp_diff, 4),
                "dp_ratio": round(dp_ratio, 4),
                "flagged": dp_diff > DP_DIFF_LOG_THRESHOLD,
            })
    return results


def _equalized_odds(groups: dict[str, GroupStats]) -> list[dict[str, Any]]:
    """Compute equalized odds (TPR + FPR parity) between every pair of groups."""
    results = []
    group_list = list(groups.values())
    for i in range(len(group_list)):
        for j in range(i + 1, len(group_list)):
            g1, g2 = group_list[i], group_list[j]
            # Need at least some ground-truth data
            has_labels = (
                (g1.n_true_positive + g1.n_false_negative + g1.n_false_positive + g1.n_true_negative) > 0
                and (g2.n_true_positive + g2.n_false_negative + g2.n_false_positive + g2.n_true_negative) > 0
            )
            if not has_labels:
                continue
            tpr_diff = abs(g1.tpr - g2.tpr)
            fpr_diff = abs(g1.fpr - g2.fpr)
            results.append({
                "metric": "equalized_odds",
                "group_a": g1.group,
                "group_b": g2.group,
                "tpr_a": round(g1.tpr, 4),
                "tpr_b": round(g2.tpr, 4),
                "fpr_a": round(g1.fpr, 4),
                "fpr_b": round(g2.fpr, 4),
                "tpr_diff": round(tpr_diff, 4),
                "fpr_diff": round(fpr_diff, 4),
                "flagged": (tpr_diff > EO_DIFF_LOG_THRESHOLD or fpr_diff > EO_DIFF_LOG_THRESHOLD),
            })
    return results


def _disparate_impact(groups: dict[str, GroupStats]) -> list[dict[str, Any]]:
    """Compute the EEOC 4/5ths-rule disparate impact ratio across all groups."""
    results = []
    valid = [g for g in groups.values() if g.n >= 2]
    if len(valid) < 2:
        return results
    rates = [(g.group, g.selection_rate) for g in valid]
    max_rate = max(r for _, r in rates)
    if max_rate == 0:
        return results
    for group, rate in rates:
        di_ratio = rate / max_rate
        results.append({
            "metric": "disparate_impact",
            "group": group,
            "selection_rate": round(rate, 4),
            "reference_max_rate": round(max_rate, 4),
            "di_ratio": round(di_ratio, 4),
            "eeoc_flagged": di_ratio < DI_LOG_THRESHOLD,
            "block_recommended": di_ratio < DI_BLOCK_THRESHOLD,
        })
    return results


def _compute_bias_risk(dp_results: list, di_results: list, eo_results: list) -> float:
    """Aggregate a single risk score from all metric results (0.0–1.0)."""
    signals: list[float] = []

    for r in dp_results:
        signals.append(min(1.0, r["dp_diff"] / (DP_DIFF_LOG_THRESHOLD + 1e-9)))

    for r in di_results:
        # Invert: di_ratio=1 → risk=0, di_ratio=0 → risk=1
        signals.append(max(0.0, 1.0 - r["di_ratio"]))

    for r in eo_results:
        signals.append(min(1.0, r["tpr_diff"] / (EO_DIFF_LOG_THRESHOLD + 1e-9)))
        signals.append(min(1.0, r["fpr_diff"] / (EO_DIFF_LOG_THRESHOLD + 1e-9)))

    if not signals:
        return 0.0
    # Use RMS to weight extreme outliers more heavily than mean
    return min(1.0, math.sqrt(sum(s * s for s in signals) / len(signals)))


# ── In-process group statistics store ─────────────────────────────────────────

class _GroupStore:
    """Thread-safe, in-process accumulator of per-agent, per-group statistics.

    Keyed by (agent, demographic_group).  Statistics are accumulated across
    requests during the process lifetime to enable batch metric calculation.
    A rolling window of the last ``_MAX_EVENTS`` decisions is used to avoid
    stale data from old runs.
    """

    _MAX_EVENTS = int(__import__("os").environ.get("BIAS_STORE_MAX_EVENTS", "10000"))

    def __init__(self) -> None:
        self._lock = threading.RLock()
        # Key: agent → dict[group → GroupStats]
        self._data: dict[str, dict[str, GroupStats]] = {}
        # Rolling event buffer key: agent → list of (group, decision, ground_truth)
        self._events: dict[str, list[tuple[str, bool, bool | None]]] = {}

    def record(
        self,
        agent: str,
        group: str,
        decision: bool,
        ground_truth: bool | None = None,
    ) -> None:
        with self._lock:
            if agent not in self._events:
                self._events[agent] = []
            self._events[agent].append((group, decision, ground_truth))
            # Trim to rolling window
            if len(self._events[agent]) > self._MAX_EVENTS:
                self._events[agent] = self._events[agent][-self._MAX_EVENTS:]
            # Rebuild stats for this agent from scratch (cheap for ≤10k events)
            self._rebuild_stats(agent)

    def _rebuild_stats(self, agent: str) -> None:
        stats: dict[str, GroupStats] = {}
        for grp, decision, gt in self._events[agent]:
            if grp not in stats:
                stats[grp] = GroupStats(group=grp)
            s = stats[grp]
            s.n += 1
            if decision:
                s.n_positive += 1
                if gt is True:
                    s.n_true_positive += 1
                elif gt is False:
                    s.n_false_positive += 1
            else:
                if gt is True:
                    s.n_false_negative += 1
                elif gt is False:
                    s.n_true_negative += 1
        self._data[agent] = stats

    def get_stats(self, agent: str) -> dict[str, GroupStats]:
        with self._lock:
            return dict(self._data.get(agent, {}))

    def snapshot(self, agent: str) -> dict[str, Any]:
        stats = self.get_stats(agent)
        return {
            g: {
                "n": s.n,
                "n_positive": s.n_positive,
                "selection_rate": round(s.selection_rate, 4),
                "tpr": round(s.tpr, 4),
                "fpr": round(s.fpr, 4),
            }
            for g, s in stats.items()
        }


# ── Core engine ────────────────────────────────────────────────────────────────

class BiasDetectionEngine:
    """Main bias detection and mitigation engine.

    Usage (from agents or server.py)
    --------------------------------
    ::

        engine = get_bias_engine()

        report = engine.check(BiasCheckContext(
            agent="recruiter",
            action="rank_candidate",
            subject_id="candidate-42",
            decision=True,
            demographic_group="group_a",
            ground_truth=None,   # not yet known
        ))

        if report.outcome == "block":
            return {"blocked": True, "bias_report": report.to_dict()}

    Async usage
    -----------
    Since all methods are synchronous, wrap with ``asyncio.run_in_threadpool``
    (FastAPI) or ``loop.run_in_executor`` when calling from async code.
    """

    def __init__(self, store: _GroupStore | None = None) -> None:
        self._store = store or _GroupStore()

    # ── Public API ─────────────────────────────────────────────────────────────

    def is_checked_agent(self, agent: str, action: str = "") -> bool:
        """Return True if this agent/action combination should be bias-checked."""
        if agent in BIAS_CHECKED_AGENTS:
            return True
        action_lower = (action or "").lower()
        return any(kw in action_lower for kw in BIAS_TRIGGER_ACTIONS)

    def check(self, ctx: BiasCheckContext) -> BiasReport:
        """Run the full bias detection pipeline for one decision.

        Steps:
        1. Record the decision in the rolling stats store.
        2. Compute demographic parity, equalized odds, disparate impact.
        3. Determine pipeline outcome: approve | log | block.
        4. Persist to AuditEngine.
        5. Return a BiasReport.
        """
        report = BiasReport(
            agent=ctx.agent,
            action=ctx.action,
            subject_id=ctx.subject_id,
            demographic_group=ctx.demographic_group,
            decision=ctx.decision,
        )
        try:
            # 1. Record
            self._store.record(
                agent=ctx.agent,
                group=ctx.demographic_group,
                decision=ctx.decision,
                ground_truth=ctx.ground_truth,
            )

            # 2. Compute metrics
            stats = self._store.get_stats(ctx.agent)
            dp = _demographic_parity(stats)
            eo = _equalized_odds(stats)
            di = _disparate_impact(stats)
            all_metrics = dp + eo + di
            report.metrics = all_metrics

            # 3. Determine outcome
            risk = _compute_bias_risk(dp, di, eo)
            report.audit_risk_score = round(risk, 4)

            block_recommended = any(
                r.get("block_recommended") for r in di
            )
            any_flagged = any(r.get("flagged") or r.get("eeoc_flagged") for r in all_metrics)

            if block_recommended:
                report.outcome = "block"
                report.high_risk = True
                report.summary = (
                    f"BLOCKED: Disparate impact ratio below {DI_BLOCK_THRESHOLD:.0%} "
                    f"({DI_BLOCK_THRESHOLD:.2f}) threshold. "
                    f"Risk score: {risk:.2f}. "
                    "This decision pattern shows severe adverse impact and has been blocked "
                    "pending human review."
                )
            elif any_flagged or risk > 0.3:
                report.outcome = "log"
                report.high_risk = risk >= 0.6
                report.summary = (
                    f"FLAGGED: Bias metrics exceed configured thresholds. "
                    f"Risk score: {risk:.2f}. "
                    "Decision logged for human review."
                )
            else:
                report.outcome = "approve"
                report.summary = (
                    f"APPROVED: No significant bias detected. "
                    f"Risk score: {risk:.2f}."
                )

        except Exception as exc:
            report.outcome = "log"
            report.error = str(exc)
            report.summary = f"Bias check encountered an error: {exc}. Decision logged."
            report.audit_risk_score = 0.5

        # 4. Persist to AuditEngine
        self._audit(report, ctx)
        return report

    def report_for_agent(self, agent: str) -> dict[str, Any]:
        """Return a current bias summary report for an agent.

        Computes all fairness metrics across all accumulated decisions for
        the agent and returns a structured summary.  Safe to call at any time.
        """
        stats = self._store.get_stats(agent)
        dp = _demographic_parity(stats)
        eo = _equalized_odds(stats)
        di = _disparate_impact(stats)
        risk = _compute_bias_risk(dp, di, eo)
        return {
            "agent": agent,
            "ts": _ts(),
            "group_snapshot": self._store.snapshot(agent),
            "demographic_parity": dp,
            "equalized_odds": eo,
            "disparate_impact": di,
            "overall_bias_risk": round(risk, 4),
            "high_risk": risk >= 0.6,
        }

    def recent_events(self, *, limit: int = 100) -> list[dict[str, Any]]:
        """Return recent high-risk bias events from the AuditEngine."""
        try:
            import sys as _sys
            import os as _os
            from pathlib import Path as _Path
            _rdir = _Path(__file__).resolve().parent.parent
            if str(_rdir) not in _sys.path:
                _sys.path.insert(0, str(_rdir))
            from core.audit_engine import get_audit_engine
            engine = get_audit_engine()
            raw = engine._cache
            events = [
                e for e in list(raw)
                if e.get("action", "").startswith("bias_")
            ]
            return events[:limit]
        except Exception:
            return []

    # ── Internal ──────────────────────────────────────────────────────────────

    def _audit(self, report: BiasReport, ctx: BiasCheckContext) -> None:
        try:
            import sys as _sys
            from pathlib import Path as _Path
            _rdir = _Path(__file__).resolve().parent.parent
            if str(_rdir) not in _sys.path:
                _sys.path.insert(0, str(_rdir))
            from core.audit_engine import get_audit_engine
            action = "bias_block" if report.outcome == "block" else (
                "bias_flag" if report.outcome == "log" else "bias_check"
            )
            get_audit_engine().record(
                actor=ctx.agent,
                action=action,
                input_data={
                    "agent": ctx.agent,
                    "action": ctx.action,
                    "subject_id": ctx.subject_id,
                    "demographic_group": ctx.demographic_group,
                    "decision": ctx.decision,
                    "check_id": report.check_id,
                },
                output_data={
                    "outcome": report.outcome,
                    "summary": report.summary,
                    "high_risk": report.high_risk,
                    "metrics_count": len(report.metrics),
                },
                risk_score=report.audit_risk_score,
                meta={
                    "check_id": report.check_id,
                    "high_risk": report.high_risk,
                    "bias_module": "bias_detection_engine",
                },
            )
        except Exception:
            pass


# ── Singleton ──────────────────────────────────────────────────────────────────

_instance: BiasDetectionEngine | None = None
_instance_lock = threading.Lock()


def get_bias_engine() -> BiasDetectionEngine:
    """Return the process-wide BiasDetectionEngine singleton."""
    global _instance
    with _instance_lock:
        if _instance is None:
            _instance = BiasDetectionEngine()
    return _instance
