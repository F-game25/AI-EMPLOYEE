"""RiskScorer — P(failure) × severity_weight per scenario."""
from __future__ import annotations
import logging
import sqlite3
import os
from pathlib import Path
from typing import Optional

from .schema import RiskScore, SimulationResult

logger = logging.getLogger(__name__)

_SEVERITY_WEIGHTS = {
    "data_loss": 1.0,
    "compliance_violation": 0.8,
    "financial_error": 0.6,
    "performance_degradation": 0.3,
    "ux_degradation": 0.2,
    "default": 0.5,
}

_SCENARIO_SEVERITY = {
    "adversarial_prompt_injection": "compliance_violation",
    "finance_reconciliation": "financial_error",
    "hr_workflow_automation": "compliance_violation",
    "sales_pipeline_automation": "ux_degradation",
    "onboard_enterprise_client": "ux_degradation",
}


def _get_historical_failure_rate(scenario_id: str) -> float:
    """Read last 10 runs for scenario, compute failed_steps / total_steps."""
    try:
        db = Path(os.path.expanduser("~/.ai-employee/simulation.db"))
        if not db.exists():
            return 0.1  # no history → assume low risk
        with sqlite3.connect(str(db), timeout=5) as c:
            rows = c.execute(
                "SELECT overall_score FROM simulation_runs WHERE scenario_id=? "
                "ORDER BY started_at DESC LIMIT 10",
                (scenario_id,)
            ).fetchall()
        if not rows:
            return 0.1
        scores = [r[0] for r in rows if r[0] is not None]
        failed = sum(1 for s in scores if s < 0.7)
        return failed / len(scores)
    except Exception:
        return 0.1


def score(scenario_id: str, result: Optional[SimulationResult] = None) -> RiskScore:
    p_failure = _get_historical_failure_rate(scenario_id)

    # Factor in current run's score if available
    if result and result.overall_score is not None:
        current_fail = 1.0 - result.overall_score
        p_failure = 0.6 * p_failure + 0.4 * current_fail

    severity_key = _SCENARIO_SEVERITY.get(scenario_id, "default")
    severity_weight = _SEVERITY_WEIGHTS.get(severity_key, 0.5)
    risk = p_failure * (1 + severity_weight)

    return RiskScore(
        scenario_id=scenario_id,
        probability=round(p_failure, 3),
        severity_weight=severity_weight,
        risk=round(risk, 3),
        breakdown={
            "p_failure": p_failure,
            "severity_key": severity_key,
            "severity_weight": severity_weight,
            "formula": "P(failure) × (1 + severity_weight)",
        },
    )
