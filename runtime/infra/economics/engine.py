"""Economic Orchestration Engine.

Core reasoning loop:
  1. Score task economic value (expected_value_usd)
  2. Estimate execution cost (tokens × model_price)
  3. Compute ROI ratio = expected_value / cost
  4. Route to cheapest model that meets quality/latency SLA
  5. Enforce tenant budget ceiling
  6. Record actuals for ROI learning

Decision contract:
  {
    "approved": bool,
    "model_id": str,
    "estimated_cost_usd": float,
    "expected_value_usd": float,
    "roi_ratio": float,
    "reason": str,
    "budget_remaining_usd": float,
  }
"""
from __future__ import annotations

import json
import logging
import sqlite3
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from threading import RLock
from typing import Any

from infra.economics.model_pricing import ModelPrice, get_pricing_catalog

logger = logging.getLogger("economics.engine")

_DB_PATH = Path.home() / ".ai-employee" / "economics.db"

_INIT_SQL = """
CREATE TABLE IF NOT EXISTS tenant_budgets (
    tenant_id       TEXT PRIMARY KEY,
    monthly_ceiling_usd REAL NOT NULL DEFAULT 500.0,
    current_month   TEXT NOT NULL,    -- YYYY-MM
    spent_usd       REAL NOT NULL DEFAULT 0.0,
    updated_at      REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS execution_ledger (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ts              REAL NOT NULL,
    tenant_id       TEXT NOT NULL,
    task_id         TEXT NOT NULL,
    agent_id        TEXT NOT NULL DEFAULT '',
    model_id        TEXT NOT NULL,
    input_tokens    INTEGER NOT NULL DEFAULT 0,
    output_tokens   INTEGER NOT NULL DEFAULT 0,
    actual_cost_usd REAL NOT NULL DEFAULT 0.0,
    expected_value_usd REAL NOT NULL DEFAULT 0.0,
    roi_ratio       REAL NOT NULL DEFAULT 0.0,
    latency_ms      REAL NOT NULL DEFAULT 0.0,
    outcome         TEXT NOT NULL DEFAULT 'unknown'   -- success|failure|timeout
);

CREATE INDEX IF NOT EXISTS idx_ledger_tenant ON execution_ledger(tenant_id, ts);
CREATE INDEX IF NOT EXISTS idx_ledger_task ON execution_ledger(task_id);
"""


@dataclass
class TaskProfile:
    """Describes a task for economic evaluation."""
    task_id: str
    tenant_id: str
    task_type: str              # classification, generation, analysis, code, search, hitl
    description: str
    required_capabilities: list[str] = field(default_factory=lambda: ["text"])
    expected_input_tokens: int = 500
    expected_output_tokens: int = 200
    sla_latency_tier: str = "balanced"   # fast | balanced | quality
    priority: str = "p2"
    business_context: dict[str, Any] = field(default_factory=dict)
    # Value hints (optional — engine will estimate if not provided)
    hint_value_usd: float = 0.0


@dataclass
class EconomicDecision:
    task_id: str
    approved: bool
    model_id: str
    provider: str
    estimated_cost_usd: float
    expected_value_usd: float
    roi_ratio: float
    reason: str
    budget_remaining_usd: float
    alternatives: list[dict] = field(default_factory=list)


class ValueScoringModel:
    """Estimates business value of a task execution.

    Scoring tiers by task_type and priority:
      P0 = at least $50 (blocking operations)
      generation/analysis = $5–$200 based on context
      classification = $1–$10
    """

    BASE_VALUES: dict[str, float] = {
        "code":         50.0,
        "analysis":     25.0,
        "generation":   15.0,
        "search":       10.0,
        "classification": 5.0,
        "hitl":         100.0,   # human-in-loop = high value
        "default":      10.0,
    }
    PRIORITY_MULT: dict[str, float] = {"p0": 10.0, "p1": 3.0, "p2": 1.0, "p3": 0.3}

    def estimate(self, profile: TaskProfile) -> float:
        if profile.hint_value_usd > 0:
            return profile.hint_value_usd
        base = self.BASE_VALUES.get(profile.task_type, self.BASE_VALUES["default"])
        mult = self.PRIORITY_MULT.get(profile.priority, 1.0)
        # Context bonuses
        ctx = profile.business_context
        if ctx.get("customer_facing"):
            mult *= 2.0
        if ctx.get("revenue_generating"):
            mult *= 3.0
        return round(base * mult, 2)


class ModelRouter:
    """Selects the cheapest model meeting SLA + capability requirements."""

    _LATENCY_PRIORITY = {"fast": 0, "balanced": 1, "quality": 2}
    _MIN_ROI = 2.0   # reject if ROI < 2x (cost must return at least 2× value)

    def select(
        self,
        profile: TaskProfile,
        estimated_value: float,
        budget_remaining: float,
    ) -> tuple[ModelPrice | None, list[dict]]:
        catalog = get_pricing_catalog()
        candidates = [
            m for m in catalog.all_models()
            if set(profile.required_capabilities).issubset(set(m.capabilities))
            and self._latency_ok(m.latency_tier, profile.sla_latency_tier)
        ]
        if not candidates:
            return None, []

        # Score each candidate: cheaper is better, but penalize if quality < sla
        alternatives: list[dict] = []
        for m in candidates:
            cost = m.cost(profile.expected_input_tokens, profile.expected_output_tokens)
            roi = estimated_value / cost if cost > 0 else 9999.0
            alternatives.append({
                "model_id": m.model_id, "provider": m.provider,
                "cost_usd": round(cost, 6), "roi_ratio": round(roi, 1),
                "latency_tier": m.latency_tier,
            })

        alternatives.sort(key=lambda x: x["cost_usd"])

        # Pick cheapest that fits budget and ROI threshold
        for alt in alternatives:
            if alt["cost_usd"] <= budget_remaining and alt["roi_ratio"] >= self._MIN_ROI:
                model = catalog.get(alt["model_id"])
                return model, alternatives
        return None, alternatives

    def _latency_ok(self, model_tier: str, sla_tier: str) -> bool:
        mp = self._LATENCY_PRIORITY
        return mp.get(model_tier, 99) <= mp.get(sla_tier, 99)


class BudgetLedger:
    """Tracks per-tenant spending against monthly ceilings."""

    def __init__(self, db_path: Path = _DB_PATH) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db_path = db_path
        self._lock = RLock()
        with self._connect() as conn:
            conn.executescript(_INIT_SQL)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._db_path), timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    def _current_month(self) -> str:
        return time.strftime("%Y-%m")

    def get_remaining(self, tenant_id: str) -> float:
        month = self._current_month()
        with self._connect() as conn:
            row = conn.execute("SELECT monthly_ceiling_usd, current_month, spent_usd FROM tenant_budgets WHERE tenant_id=?",
                               (tenant_id,)).fetchone()
        if not row:
            return 500.0  # default ceiling
        if row["current_month"] != month:
            # New month — reset
            return row["monthly_ceiling_usd"]
        return max(0.0, row["monthly_ceiling_usd"] - row["spent_usd"])

    def set_ceiling(self, tenant_id: str, ceiling_usd: float) -> None:
        month = self._current_month()
        with self._lock, self._connect() as conn:
            conn.execute(
                """INSERT INTO tenant_budgets(tenant_id, monthly_ceiling_usd, current_month, spent_usd, updated_at)
                   VALUES(?,?,?,0,?)
                   ON CONFLICT(tenant_id) DO UPDATE SET monthly_ceiling_usd=?, updated_at=?""",
                (tenant_id, ceiling_usd, month, time.time(), ceiling_usd, time.time()),
            )

    def record_spend(self, tenant_id: str, cost_usd: float) -> None:
        month = self._current_month()
        with self._lock, self._connect() as conn:
            conn.execute(
                """INSERT INTO tenant_budgets(tenant_id, monthly_ceiling_usd, current_month, spent_usd, updated_at)
                   VALUES(?,500.0,?,?,?)
                   ON CONFLICT(tenant_id) DO UPDATE SET
                     spent_usd = CASE WHEN current_month=? THEN spent_usd+? ELSE ? END,
                     current_month=?,
                     updated_at=?""",
                (tenant_id, month, cost_usd, time.time(),
                 month, cost_usd, cost_usd, month, time.time()),
            )

    def record_execution(
        self,
        tenant_id: str, task_id: str, agent_id: str, model_id: str,
        input_tokens: int, output_tokens: int, actual_cost: float,
        expected_value: float, latency_ms: float, outcome: str,
    ) -> None:
        roi = expected_value / actual_cost if actual_cost > 0 else 0.0
        with self._lock, self._connect() as conn:
            conn.execute(
                """INSERT INTO execution_ledger
                   (ts, tenant_id, task_id, agent_id, model_id, input_tokens, output_tokens,
                    actual_cost_usd, expected_value_usd, roi_ratio, latency_ms, outcome)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                (time.time(), tenant_id, task_id, agent_id, model_id,
                 input_tokens, output_tokens, actual_cost, expected_value, roi, latency_ms, outcome),
            )
        if actual_cost > 0:
            self.record_spend(tenant_id, actual_cost)

    def monthly_summary(self, tenant_id: str) -> dict:
        month = self._current_month()
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM tenant_budgets WHERE tenant_id=?", (tenant_id,)).fetchone()
            stats = conn.execute(
                """SELECT COUNT(*) as executions,
                          SUM(actual_cost_usd) as total_cost,
                          SUM(expected_value_usd) as total_value,
                          AVG(roi_ratio) as avg_roi,
                          AVG(latency_ms) as avg_latency_ms
                   FROM execution_ledger
                   WHERE tenant_id=? AND strftime('%Y-%m', datetime(ts, 'unixepoch'))=?""",
                (tenant_id, month),
            ).fetchone()
        return {
            "tenant_id": tenant_id,
            "month": month,
            "ceiling_usd": row["monthly_ceiling_usd"] if row else 500.0,
            "spent_usd": round(row["spent_usd"] if row else 0.0, 4),
            "remaining_usd": self.get_remaining(tenant_id),
            "executions": stats["executions"] or 0,
            "total_cost_usd": round(stats["total_cost"] or 0.0, 4),
            "total_value_usd": round(stats["total_value"] or 0.0, 2),
            "avg_roi": round(stats["avg_roi"] or 0.0, 2),
            "avg_latency_ms": round(stats["avg_latency_ms"] or 0.0, 1),
        }

    def top_costs(self, tenant_id: str, limit: int = 10) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT task_id, agent_id, model_id, actual_cost_usd, expected_value_usd, roi_ratio, outcome, ts
                   FROM execution_ledger WHERE tenant_id=?
                   ORDER BY actual_cost_usd DESC LIMIT ?""",
                (tenant_id, limit),
            ).fetchall()
        return [dict(r) for r in rows]


class EconomicOrchestrator:
    """Central economic decision engine."""

    def __init__(self) -> None:
        self._value_model = ValueScoringModel()
        self._router = ModelRouter()
        self._ledger = BudgetLedger()

    def evaluate(self, profile: TaskProfile) -> EconomicDecision:
        """Synchronous evaluation — safe to call from any context."""
        expected_value = self._value_model.estimate(profile)
        budget_remaining = self._ledger.get_remaining(profile.tenant_id)

        model, alternatives = self._router.select(profile, expected_value, budget_remaining)

        if not model:
            return EconomicDecision(
                task_id=profile.task_id,
                approved=False,
                model_id="",
                provider="",
                estimated_cost_usd=0.0,
                expected_value_usd=expected_value,
                roi_ratio=0.0,
                reason="No model found meeting SLA and budget constraints",
                budget_remaining_usd=budget_remaining,
                alternatives=alternatives,
            )

        cost = model.cost(profile.expected_input_tokens, profile.expected_output_tokens)
        roi = expected_value / cost if cost > 0 else 9999.0

        approved = cost <= budget_remaining and roi >= ModelRouter._MIN_ROI
        reason = "Approved" if approved else (
            "Budget ceiling reached" if cost > budget_remaining else
            f"ROI {roi:.1f}× below threshold {ModelRouter._MIN_ROI}×"
        )

        logger.info(
            "EconEval task=%s model=%s cost=$%.4f value=$%.2f roi=%.1f× approved=%s",
            profile.task_id, model.model_id, cost, expected_value, roi, approved,
        )

        return EconomicDecision(
            task_id=profile.task_id,
            approved=approved,
            model_id=model.model_id,
            provider=model.provider,
            estimated_cost_usd=round(cost, 6),
            expected_value_usd=round(expected_value, 2),
            roi_ratio=round(roi, 2),
            reason=reason,
            budget_remaining_usd=round(budget_remaining, 4),
            alternatives=alternatives,
        )

    def record_actual(
        self,
        task_id: str,
        tenant_id: str,
        model_id: str,
        input_tokens: int,
        output_tokens: int,
        expected_value_usd: float,
        latency_ms: float,
        outcome: str = "success",
        agent_id: str = "",
    ) -> float:
        """Record actual execution cost and return the real cost."""
        catalog = get_pricing_catalog()
        model = catalog.get(model_id)
        actual_cost = model.cost(input_tokens, output_tokens) if model else 0.0
        self._ledger.record_execution(
            tenant_id=tenant_id, task_id=task_id, agent_id=agent_id,
            model_id=model_id, input_tokens=input_tokens, output_tokens=output_tokens,
            actual_cost=actual_cost, expected_value=expected_value_usd,
            latency_ms=latency_ms, outcome=outcome,
        )
        return actual_cost

    def set_budget(self, tenant_id: str, ceiling_usd: float) -> None:
        self._ledger.set_ceiling(tenant_id, ceiling_usd)

    def get_summary(self, tenant_id: str) -> dict:
        return self._ledger.monthly_summary(tenant_id)

    def top_costs(self, tenant_id: str) -> list[dict]:
        return self._ledger.top_costs(tenant_id)


_orchestrator: EconomicOrchestrator | None = None

def get_economic_orchestrator() -> EconomicOrchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = EconomicOrchestrator()
    return _orchestrator
