"""Budget Tracker — Per-Agent Cost Tracking & Enforcement for AI-EMPLOYEE.

Inspired by Paperclip's per-agent monthly budget controls, this module:
  - Tracks token usage per agent per month
  - Enforces configurable monthly budget caps (USD)
  - Warns at 80% usage, hard-stops at 100%
  - Provides cost breakdown per agent / model / month
  - Integrates with ai_router to gate API calls

Config:  ~/.ai-employee/config/budgets.json
State:   ~/.ai-employee/state/budget-tracker.state.json

Token → USD pricing (approximate, configurable):
  gpt-4o:          $5 / 1M input tokens, $15 / 1M output tokens
  claude-opus-4-5: $15 / 1M input tokens, $75 / 1M output tokens
  ollama (local):  $0

API (via problem-solver-ui server.py):
  GET  /api/budget/status           — budget status for all agents
  GET  /api/budget/status/{agent}   — budget status for one agent
  POST /api/budget/set              — set budget for an agent
  POST /api/budget/reset/{agent}    — reset monthly usage for an agent
  POST /api/budget/record           — record token usage (called by ai_router)
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger("budget-tracker")

AI_HOME = Path(os.environ.get("AI_HOME", str(Path.home() / ".ai-employee")))
BUDGETS_FILE = AI_HOME / "config" / "budgets.json"
STATE_FILE = AI_HOME / "state" / "budget-tracker.state.json"

# Approximate USD cost per 1M tokens for common models.
# Last updated: 2026-04 — update when providers change prices,
# or override via config/budget_pricing.json (loaded below).
MODEL_COST_PER_1M: dict[str, dict[str, float]] = {
    "gpt-4o": {"input": 5.0, "output": 15.0},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "claude-opus-4-5": {"input": 15.0, "output": 75.0},
    "claude-sonnet-4-5": {"input": 3.0, "output": 15.0},
    "claude-haiku-4-5": {"input": 0.25, "output": 1.25},
    "nemotron": {"input": 0.0, "output": 0.0},   # free via NVIDIA NIM
    "qwen": {"input": 0.0, "output": 0.0},        # free via NVIDIA NIM
    "llama3.2": {"input": 0.0, "output": 0.0},    # free via Ollama
    "llama3.1": {"input": 0.0, "output": 0.0},
    "hermes3": {"input": 0.0, "output": 0.0},
    "gemma3": {"input": 0.0, "output": 0.0},
}
DEFAULT_MODEL_COST = {"input": 1.0, "output": 3.0}  # fallback pricing

# Default monthly budget per agent (USD) — 0 means unlimited
DEFAULT_BUDGET_USD = float(os.environ.get("DEFAULT_AGENT_BUDGET_USD", "10.0"))
WARN_THRESHOLD = 0.80   # 80% → warning
STOP_THRESHOLD = 1.00   # 100% → hard stop


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _current_month() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


# ── Config helpers ────────────────────────────────────────────────────────────


def _load_budgets() -> dict:
    """Load per-agent budget configuration."""
    if BUDGETS_FILE.exists():
        try:
            return json.loads(BUDGETS_FILE.read_text())
        except Exception as exc:
            logger.warning("budgets load error: %s", exc)
    return {}


def _save_budgets(budgets: dict) -> None:
    BUDGETS_FILE.parent.mkdir(parents=True, exist_ok=True)
    BUDGETS_FILE.write_text(json.dumps(budgets, indent=2))


# ── State helpers ─────────────────────────────────────────────────────────────


def _load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception as exc:
            logger.warning("budget state load error: %s", exc)
    return {}


def _save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = _now_iso()
    STATE_FILE.write_text(json.dumps(state, indent=2))


# ── Core accounting ───────────────────────────────────────────────────────────


def _estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Return estimated USD cost for a model call."""
    pricing = MODEL_COST_PER_1M.get(model.lower(), DEFAULT_MODEL_COST)
    return (input_tokens / 1_000_000) * pricing["input"] + (
        output_tokens / 1_000_000
    ) * pricing["output"]


def record_usage(
    agent_id: str,
    model: str,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cost_usd: float | None = None,
) -> dict:
    """Record token usage for an agent call.

    Returns a status dict with fields:
      agent_id, month, spent_usd, budget_usd, percent, status
      status: "ok" | "warning" | "exceeded"
    """
    month = _current_month()
    if cost_usd is None:
        cost_usd = _estimate_cost(model, input_tokens, output_tokens)

    state = _load_state()
    usage: dict = state.setdefault("usage", {})
    agent_usage: dict = usage.setdefault(agent_id, {})
    month_usage: dict = agent_usage.setdefault(month, {"cost_usd": 0.0, "calls": 0, "tokens": 0})
    month_usage["cost_usd"] = round(month_usage["cost_usd"] + cost_usd, 6)
    month_usage["calls"] += 1
    month_usage["tokens"] += input_tokens + output_tokens

    # Track per-model breakdown
    model_key = f"model_{model.lower()}"
    month_usage[model_key] = round(month_usage.get(model_key, 0.0) + cost_usd, 6)

    _save_state(state)
    return get_agent_status(agent_id)


def get_agent_status(agent_id: str) -> dict:
    """Return budget status for a single agent."""
    month = _current_month()
    budgets = _load_budgets()
    state = _load_state()

    budget_usd = budgets.get(agent_id, DEFAULT_BUDGET_USD)
    usage = state.get("usage", {}).get(agent_id, {}).get(month, {})
    spent = usage.get("cost_usd", 0.0)

    if budget_usd <= 0:
        percent = 0.0
        status = "ok"
    else:
        percent = spent / budget_usd
        if percent >= STOP_THRESHOLD:
            status = "exceeded"
        elif percent >= WARN_THRESHOLD:
            status = "warning"
        else:
            status = "ok"

    return {
        "agent_id": agent_id,
        "month": month,
        "spent_usd": round(spent, 4),
        "budget_usd": budget_usd,
        "percent": round(percent, 4),
        "status": status,
        "calls": usage.get("calls", 0),
        "tokens": usage.get("tokens", 0),
    }


def is_budget_exceeded(agent_id: str) -> bool:
    """Return True if the agent has exhausted its monthly budget."""
    status = get_agent_status(agent_id)
    return status["status"] == "exceeded"


def get_all_status() -> list[dict]:
    """Return budget status for every tracked agent."""
    budgets = _load_budgets()
    state = _load_state()
    month = _current_month()
    usage = state.get("usage", {})

    agent_ids = set(budgets.keys()) | set(usage.keys())
    return [get_agent_status(aid) for aid in sorted(agent_ids)]


def set_budget(agent_id: str, monthly_budget_usd: float) -> dict:
    """Set the monthly budget cap for an agent (0 = unlimited)."""
    budgets = _load_budgets()
    budgets[agent_id] = max(0.0, float(monthly_budget_usd))
    _save_budgets(budgets)
    return get_agent_status(agent_id)


def reset_usage(agent_id: str) -> dict:
    """Reset monthly token usage for an agent (e.g., at start of new month)."""
    month = _current_month()
    state = _load_state()
    usage = state.get("usage", {})
    if agent_id in usage and month in usage[agent_id]:
        del usage[agent_id][month]
    _save_state(state)
    return get_agent_status(agent_id)


def auto_reset_all_if_new_month() -> int:
    """Check and auto-reset all agents if a new month has started.

    Returns the number of agents whose state was reset.
    """
    state = _load_state()
    last_reset_month = state.get("last_auto_reset_month", "")
    current_month = _current_month()
    if last_reset_month == current_month:
        return 0

    # New month — clear all usage
    state["usage"] = {}
    state["last_auto_reset_month"] = current_month
    _save_state(state)
    logger.info("budget-tracker: auto-reset all agents for new month %s", current_month)
    count = len(state.get("usage", {}))
    return count
