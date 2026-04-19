"""ASCEND AI — Fairness Dashboard Router

Provides bias detection / ML fairness data for the frontend Fairness Dashboard.

This router is self-contained and does NOT require the runtime/ package.
When the full runtime is present it will attempt to import the real
BiasDetectionEngine; otherwise it returns illustrative demo data so the UI
always renders.

Endpoints
─────────
  GET  /api/fairness/report          — full per-agent fairness metrics
  POST /api/fairness/check           — submit a single bias check context
  GET  /api/fairness/agents          — list agents with bias check counts
  GET  /api/fairness/summary         — top-level summary card data
"""
from __future__ import annotations

import math
import time
import uuid
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()

# ── In-memory log of submitted bias checks ────────────────────────────────
_checks: list[dict[str, Any]] = []

# ── Demo baseline data (shown until real runtime data is available) ────────
_DEMO_AGENTS = [
    {
        "agent": "lead-scorer",
        "groups": [
            {"group": "group_A", "n": 120, "n_positive": 72, "selection_rate": 0.60},
            {"group": "group_B", "n": 95,  "n_positive": 48, "selection_rate": 0.51},
        ],
        "metrics": {
            "demographic_parity_diff": 0.09,
            "demographic_parity_ratio": 0.85,
            "disparate_impact": 0.85,
            "tpr_diff": 0.04,
            "fpr_diff": 0.03,
            "bias_risk_score": 0.12,
            "flagged": False,
        },
        "checks_total": 215,
        "blocked": 0,
        "flagged_count": 3,
        "last_check": "2026-04-19T20:00:00Z",
    },
    {
        "agent": "recruiter",
        "groups": [
            {"group": "group_A", "n": 80,  "n_positive": 52, "selection_rate": 0.65},
            {"group": "group_B", "n": 75,  "n_positive": 31, "selection_rate": 0.41},
        ],
        "metrics": {
            "demographic_parity_diff": 0.24,
            "demographic_parity_ratio": 0.63,
            "disparate_impact": 0.63,
            "tpr_diff": 0.18,
            "fpr_diff": 0.11,
            "bias_risk_score": 0.41,
            "flagged": True,
        },
        "checks_total": 155,
        "blocked": 2,
        "flagged_count": 12,
        "last_check": "2026-04-19T21:00:00Z",
    },
    {
        "agent": "qualification-agent",
        "groups": [
            {"group": "group_A", "n": 200, "n_positive": 110, "selection_rate": 0.55},
            {"group": "group_B", "n": 198, "n_positive": 100, "selection_rate": 0.51},
        ],
        "metrics": {
            "demographic_parity_diff": 0.04,
            "demographic_parity_ratio": 0.93,
            "disparate_impact": 0.93,
            "tpr_diff": 0.02,
            "fpr_diff": 0.01,
            "bias_risk_score": 0.06,
            "flagged": False,
        },
        "checks_total": 398,
        "blocked": 0,
        "flagged_count": 1,
        "last_check": "2026-04-19T21:30:00Z",
    },
    {
        "agent": "hr-manager",
        "groups": [
            {"group": "group_A", "n": 60,  "n_positive": 45, "selection_rate": 0.75},
            {"group": "group_B", "n": 58,  "n_positive": 29, "selection_rate": 0.50},
        ],
        "metrics": {
            "demographic_parity_diff": 0.25,
            "demographic_parity_ratio": 0.67,
            "disparate_impact": 0.67,
            "tpr_diff": 0.20,
            "fpr_diff": 0.12,
            "bias_risk_score": 0.45,
            "flagged": True,
        },
        "checks_total": 118,
        "blocked": 3,
        "flagged_count": 15,
        "last_check": "2026-04-19T19:45:00Z",
    },
]


def _try_live_report() -> list[dict[str, Any]] | None:
    """Attempt to pull real data from BiasDetectionEngine."""
    try:
        import sys
        from pathlib import Path
        runtime = Path(__file__).resolve().parents[4] / "runtime"
        if str(runtime) not in sys.path:
            sys.path.insert(0, str(runtime))
        from core.bias_detection_engine import get_bias_engine  # type: ignore
        engine = get_bias_engine()
        out = []
        for agent_id in ["lead-scorer", "recruiter", "qualification-agent", "hr-manager"]:
            rpt = engine.report_for_agent(agent_id)
            if rpt:
                out.append(rpt)
        return out if out else None
    except Exception:
        return None


# ── Endpoints ─────────────────────────────────────────────────────────────

@router.get("/fairness/report")
def get_fairness_report():
    live = _try_live_report()
    agents_data = live if live else _DEMO_AGENTS
    total_checks = sum(a.get("checks_total", 0) for a in agents_data)
    flagged_count = sum(a.get("flagged_count", 0) for a in agents_data)
    blocked_count = sum(a.get("blocked", 0) for a in agents_data)
    return {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "live_data": live is not None,
        "summary": {
            "agents_monitored": len(agents_data),
            "total_checks": total_checks,
            "flagged": flagged_count,
            "blocked": blocked_count,
            "overall_risk": "medium" if any(
                a.get("metrics", {}).get("flagged") for a in agents_data
            ) else "low",
        },
        "agents": agents_data,
        "recent_checks": _checks[-20:],
    }


@router.get("/fairness/summary")
def get_fairness_summary():
    live = _try_live_report()
    agents_data = live if live else _DEMO_AGENTS
    flagged_agents = [a["agent"] for a in agents_data if a.get("metrics", {}).get("flagged")]
    avg_risk = sum(
        a.get("metrics", {}).get("bias_risk_score", 0) for a in agents_data
    ) / max(len(agents_data), 1)
    return {
        "agents_monitored": len(agents_data),
        "flagged_agents": flagged_agents,
        "avg_bias_risk": round(avg_risk, 3),
        "compliance_status": "WARN" if flagged_agents else "PASS",
        "di_ratio_min": min(
            (a.get("metrics", {}).get("disparate_impact", 1.0) for a in agents_data),
            default=1.0,
        ),
    }


@router.get("/fairness/agents")
def get_fairness_agents():
    live = _try_live_report()
    agents_data = live if live else _DEMO_AGENTS
    return [
        {
            "agent": a["agent"],
            "checks_total": a.get("checks_total", 0),
            "flagged_count": a.get("flagged_count", 0),
            "blocked": a.get("blocked", 0),
            "risk_score": a.get("metrics", {}).get("bias_risk_score", 0),
            "flagged": a.get("metrics", {}).get("flagged", False),
        }
        for a in agents_data
    ]


class BiasCheckRequest(BaseModel):
    agent: str
    action: str
    subject_id: str
    decision: bool
    demographic_group: str
    ground_truth: bool | None = None


@router.post("/fairness/check")
def submit_bias_check(req: BiasCheckRequest):
    record: dict[str, Any] = {
        "check_id": f"bias-{uuid.uuid4().hex[:10]}",
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "agent": req.agent,
        "action": req.action,
        "subject_id": req.subject_id,
        "decision": req.decision,
        "demographic_group": req.demographic_group,
        "outcome": "approve",
        "high_risk": False,
        "summary": f"Check recorded for {req.agent} / {req.demographic_group}",
    }
    # Try real engine
    try:
        import sys
        from pathlib import Path
        runtime = Path(__file__).resolve().parents[4] / "runtime"
        if str(runtime) not in sys.path:
            sys.path.insert(0, str(runtime))
        from core.bias_detection_engine import get_bias_engine, BiasCheckContext  # type: ignore
        ctx = BiasCheckContext(
            agent=req.agent,
            action=req.action,
            subject_id=req.subject_id,
            decision=req.decision,
            demographic_group=req.demographic_group,
            ground_truth=req.ground_truth,
        )
        report = get_bias_engine().check(ctx)
        record.update({
            "outcome": report.outcome,
            "high_risk": report.high_risk,
            "summary": report.summary,
            "metrics": report.metrics,
        })
    except Exception:
        pass

    _checks.append(record)
    if len(_checks) > 500:
        _checks.pop(0)
    return {"success": True, "check": record}
