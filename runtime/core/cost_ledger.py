"""Per-tenant cost ledger with hard caps and budget enforcement."""
from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

MODEL_COSTS: dict[str, dict] = {
    "claude-sonnet": {"input_per_1k": 0.003, "output_per_1k": 0.015},
    "claude-opus":   {"input_per_1k": 0.015, "output_per_1k": 0.075},
    "claude-haiku":  {"input_per_1k": 0.00025, "output_per_1k": 0.00125},
    "gpt-4":         {"input_per_1k": 0.03, "output_per_1k": 0.06},
    "gpt-4o":        {"input_per_1k": 0.005, "output_per_1k": 0.015},
    "gpt-3.5-turbo": {"input_per_1k": 0.0005, "output_per_1k": 0.0015},
    "ollama":        {"input_per_1k": 0.0, "output_per_1k": 0.0},
    "default":       {"input_per_1k": 0.003, "output_per_1k": 0.015},
}

# Ordered from most-specific to least-specific for fuzzy matching
_MODEL_KEYS = [k for k in MODEL_COSTS if k != "default"]


def _resolve_model(model: str) -> str:
    """Fuzzy match 'claude-sonnet-4-6' → 'claude-sonnet'."""
    m = model.lower()
    for key in _MODEL_KEYS:
        if key in m:
            return key
    return "default"


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Return USD cost for a single LLM call."""
    rates = MODEL_COSTS[_resolve_model(model)]
    return (input_tokens / 1000.0) * rates["input_per_1k"] + \
           (output_tokens / 1000.0) * rates["output_per_1k"]


@dataclass
class BudgetConfig:
    tenant_id: str
    daily_limit_usd: float = 10.0
    monthly_limit_usd: float = 200.0
    alert_threshold: float = 0.8
    hard_cap: bool = True


class BudgetEnforcementError(Exception):
    """Raised when a hard budget cap is exceeded."""


class CostLedger:
    """Thread-safe per-tenant cost ledger backed by JSON files."""

    _STATE_DIR = Path.home() / ".ai-employee" / "state"

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._STATE_DIR.mkdir(parents=True, exist_ok=True)
        self._ledger_path = self._STATE_DIR / "cost_ledger.json"
        self._budget_path = self._STATE_DIR / "budget_configs.json"
        self._ledger: dict[str, float] = self._load(self._ledger_path)
        self._budgets: dict[str, dict] = self._load(self._budget_path)

    # ── persistence helpers ────────────────────────────────────────────────

    @staticmethod
    def _load(path: Path) -> dict:
        try:
            if path.exists():
                return json.loads(path.read_text("utf-8"))
        except Exception as exc:
            logger.warning("cost_ledger: could not load %s: %s", path, exc)
        return {}

    def _save_ledger(self) -> None:
        try:
            self._ledger_path.write_text(json.dumps(self._ledger, indent=2), "utf-8")
        except Exception as exc:
            logger.error("cost_ledger: save failed: %s", exc)

    def _save_budgets(self) -> None:
        try:
            self._budget_path.write_text(json.dumps(self._budgets, indent=2), "utf-8")
        except Exception as exc:
            logger.error("budget_configs: save failed: %s", exc)

    # ── key helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _day_key(tenant_id: str, date: Optional[str] = None) -> str:
        d = date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
        return f"{tenant_id}:{d}"

    @staticmethod
    def _month_prefix(tenant_id: str, year_month: Optional[str] = None) -> str:
        ym = year_month or datetime.now(timezone.utc).strftime("%Y-%m")
        return f"{tenant_id}:{ym}"

    # ── public API ────────────────────────────────────────────────────────

    def record(
        self,
        tenant_id: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        request_id: str = "",
    ) -> float:
        """Record a spend event and return the cost in USD."""
        cost = estimate_cost(model, input_tokens, output_tokens)
        key = self._day_key(tenant_id)
        with self._lock:
            self._ledger[key] = self._ledger.get(key, 0.0) + cost
            self._save_ledger()
        logger.debug(
            "cost_ledger: tenant=%s model=%s in=%d out=%d cost=%.6f req=%s",
            tenant_id, model, input_tokens, output_tokens, cost, request_id,
        )
        return cost

    def get_daily_spend(self, tenant_id: str, date: Optional[str] = None) -> float:
        key = self._day_key(tenant_id, date)
        with self._lock:
            return self._ledger.get(key, 0.0)

    def get_monthly_spend(self, tenant_id: str, year_month: Optional[str] = None) -> float:
        prefix = self._month_prefix(tenant_id, year_month)
        with self._lock:
            return sum(v for k, v in self._ledger.items() if k.startswith(prefix))

    def check_budget(self, tenant_id: str) -> tuple[bool, str]:
        """Return (allowed, reason). reason is 'ok', 'daily_cap_exceeded', or 'monthly_cap_exceeded'."""
        cfg = self.get_budget(tenant_id)
        if not cfg.hard_cap:
            return True, "ok"
        daily = self.get_daily_spend(tenant_id)
        if daily >= cfg.daily_limit_usd:
            return False, "daily_cap_exceeded"
        monthly = self.get_monthly_spend(tenant_id)
        if monthly >= cfg.monthly_limit_usd:
            return False, "monthly_cap_exceeded"
        return True, "ok"

    def set_budget(self, tenant_id: str, daily_usd: float, monthly_usd: float) -> BudgetConfig:
        cfg = self.get_budget(tenant_id)
        cfg.daily_limit_usd = daily_usd
        cfg.monthly_limit_usd = monthly_usd
        with self._lock:
            self._budgets[tenant_id] = asdict(cfg)
            self._save_budgets()
        return cfg

    def get_budget(self, tenant_id: str) -> BudgetConfig:
        with self._lock:
            raw = self._budgets.get(tenant_id)
        if raw:
            return BudgetConfig(**{k: v for k, v in raw.items() if k in BudgetConfig.__dataclass_fields__})
        return BudgetConfig(tenant_id=tenant_id)

    def get_summary(self, tenant_id: str) -> dict:
        cfg = self.get_budget(tenant_id)
        daily = self.get_daily_spend(tenant_id)
        monthly = self.get_monthly_spend(tenant_id)
        daily_pct = daily / cfg.daily_limit_usd if cfg.daily_limit_usd else 0.0
        monthly_pct = monthly / cfg.monthly_limit_usd if cfg.monthly_limit_usd else 0.0
        pct = max(daily_pct, monthly_pct)
        if not cfg.hard_cap or pct < cfg.alert_threshold:
            status = "ok"
        elif pct < 1.0:
            status = "warning"
        else:
            status = "hard_cap"
        return {
            "tenant_id": tenant_id,
            "daily_spend": round(daily, 6),
            "monthly_spend": round(monthly, 6),
            "daily_limit": cfg.daily_limit_usd,
            "monthly_limit": cfg.monthly_limit_usd,
            "daily_pct": round(daily_pct, 4),
            "monthly_pct": round(monthly_pct, 4),
            "status": status,
        }


_ledger_instance: Optional[CostLedger] = None
_ledger_lock = threading.Lock()


def get_cost_ledger() -> CostLedger:
    global _ledger_instance
    if _ledger_instance is None:
        with _ledger_lock:
            if _ledger_instance is None:
                _ledger_instance = CostLedger()
    return _ledger_instance
