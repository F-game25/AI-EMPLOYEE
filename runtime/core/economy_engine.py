"""Economy Engine — internal economic accounting for AI Employee V4.

Every agent, task, and output carries a monetary value in the system's
internal economy.  The economy engine tracks:

- **Budget** per agent (starts at a configurable default, replenished by
  completing high-value tasks)
- **Cost** per task execution (compute + latency penalty)
- **Value** generated per output (quality score × expected market value)
- **ROI** per action = (value − cost) / max(cost, 1)

This ROI becomes the primary signal for:
1. Agent competition (``agent_competition_engine.py``)
2. Forge optimization priority (``forge_controller.py``)
3. Memory routing importance scores

Usage::

    from core.economy_engine import get_economy_engine

    eco = get_economy_engine()

    # Record a completed task
    eco.record_task(
        agent="email_ninja",
        task_id="t-001",
        cost=12,          # internal compute units
        value=85,         # estimated output value
        duration_ms=420,
        success=True,
    )

    # Query metrics
    eco.agent_metrics("email_ninja")
    eco.system_summary()
    eco.top_agents(limit=5)
    eco.suggest_improvements(limit=3)
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger("core.economy_engine")

_LOCK = threading.RLock()
_DEFAULT_BUDGET = float(os.environ.get("AI_EMPLOYEE_AGENT_BUDGET", "1000"))
_PERSIST_PATH_ENV = "AI_EMPLOYEE_ECONOMY_STATE"


def _ts() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _state_path() -> Path:
    env = os.environ.get(_PERSIST_PATH_ENV)
    if env:
        return Path(env)
    home = os.environ.get("AI_HOME")
    base = Path(home) if home else Path(__file__).resolve().parents[3]
    p = base / "state" / "economy_state.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


# ── Internal data model ────────────────────────────────────────────────────────

class _AgentLedger:
    """Accounting ledger for a single agent."""

    def __init__(self, name: str, budget: float = _DEFAULT_BUDGET) -> None:
        self.name = name
        self.budget = budget
        self.total_cost: float = 0.0
        self.total_value: float = 0.0
        self.tasks_completed: int = 0
        self.tasks_failed: int = 0
        self.total_duration_ms: int = 0
        self.reward_credits: float = 0.0    # bonus granted by competition engine
        self._history: list[dict[str, Any]] = []  # last N task records

    # ── Derived metrics ────────────────────────────────────────────────────────

    @property
    def roi(self) -> float:
        denom = max(self.total_cost, 1.0)
        return round((self.total_value - self.total_cost) / denom, 4)

    @property
    def profit(self) -> float:
        return round(self.total_value - self.total_cost, 2)

    @property
    def efficiency(self) -> float:
        """Value generated per compute unit spent."""
        return round(self.total_value / max(self.total_cost, 1.0), 4)

    @property
    def success_rate(self) -> float:
        total = self.tasks_completed + self.tasks_failed
        return round(self.tasks_completed / max(total, 1), 4)

    @property
    def avg_duration_ms(self) -> float:
        total = self.tasks_completed + self.tasks_failed
        return round(self.total_duration_ms / max(total, 1), 1)

    @property
    def performance_score(self) -> float:
        """Composite 0-1 score used by competition engine."""
        # Weighted blend: ROI (40%), efficiency (30%), success rate (30%)
        roi_norm = min(max(self.roi, 0.0), 2.0) / 2.0   # cap at 2.0
        score = 0.4 * roi_norm + 0.3 * min(self.efficiency / 5.0, 1.0) + 0.3 * self.success_rate
        return round(score, 4)

    # ── Serialisation ──────────────────────────────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "budget": round(self.budget, 2),
            "total_cost": round(self.total_cost, 2),
            "total_value": round(self.total_value, 2),
            "tasks_completed": self.tasks_completed,
            "tasks_failed": self.tasks_failed,
            "total_duration_ms": self.total_duration_ms,
            "reward_credits": round(self.reward_credits, 2),
            "roi": self.roi,
            "profit": self.profit,
            "efficiency": self.efficiency,
            "success_rate": self.success_rate,
            "avg_duration_ms": self.avg_duration_ms,
            "performance_score": self.performance_score,
            "history_count": len(self._history),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "_AgentLedger":
        obj = cls(d["name"], budget=d.get("budget", _DEFAULT_BUDGET))
        obj.total_cost = d.get("total_cost", 0.0)
        obj.total_value = d.get("total_value", 0.0)
        obj.tasks_completed = d.get("tasks_completed", 0)
        obj.tasks_failed = d.get("tasks_failed", 0)
        obj.total_duration_ms = d.get("total_duration_ms", 0)
        obj.reward_credits = d.get("reward_credits", 0.0)
        return obj


# ══════════════════════════════════════════════════════════════════════════════

class EconomyEngine:
    """System-wide internal economy tracker.

    Thread-safe.  Persists to ``state/economy_state.json`` on every mutation.
    """

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or _state_path()
        self._agents: dict[str, _AgentLedger] = {}
        self._global_tasks: int = 0
        self._global_value: float = 0.0
        self._global_cost: float = 0.0
        self._task_log: list[dict[str, Any]] = []  # rolling window
        self._MAX_LOG = 500
        self._load()
        logger.info(
            "EconomyEngine ready — %d agents tracked, global profit=%.2f",
            len(self._agents),
            self._global_value - self._global_cost,
        )

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def record_task(
        self,
        *,
        agent: str,
        task_id: str,
        cost: float,
        value: float,
        duration_ms: int = 0,
        success: bool = True,
        description: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Record a completed task into the ledger.

        Args:
            agent:       Agent identifier.
            task_id:     Unique task ID.
            cost:        Internal compute units consumed.
            value:       Estimated value generated (same units as cost).
            duration_ms: Wall-clock execution time.
            success:     Whether the task completed successfully.
            description: Human-readable description.
            metadata:    Any extra payload.

        Returns:
            Dict with roi, profit, agent performance_score.
        """
        with _LOCK:
            ledger = self._ensure_agent(agent)
            cost = max(float(cost), 0.0)
            value = max(float(value), 0.0)
            ledger.total_cost += cost
            ledger.total_value += value
            ledger.total_duration_ms += duration_ms
            ledger.budget -= cost
            if success:
                ledger.tasks_completed += 1
                ledger.budget += value   # value flows back as budget
            else:
                ledger.tasks_failed += 1

            # Global counters
            self._global_tasks += 1
            self._global_value += value
            self._global_cost += cost

            entry: dict[str, Any] = {
                "ts": _ts(),
                "task_id": task_id,
                "agent": agent,
                "cost": round(cost, 2),
                "value": round(value, 2),
                "duration_ms": duration_ms,
                "success": success,
                "description": description,
                **(metadata or {}),
            }
            ledger._history.append(entry)
            if len(ledger._history) > 100:
                ledger._history = ledger._history[-100:]
            self._task_log.append(entry)
            if len(self._task_log) > self._MAX_LOG:
                self._task_log = self._task_log[-self._MAX_LOG :]
            self._save()

        return {
            "agent": agent,
            "task_id": task_id,
            "roi": ledger.roi,
            "profit": ledger.profit,
            "performance_score": ledger.performance_score,
        }

    def grant_reward(self, agent: str, *, credits: float, reason: str = "") -> None:
        """Award bonus credits to an agent (called by competition engine)."""
        with _LOCK:
            ledger = self._ensure_agent(agent)
            ledger.reward_credits += credits
            ledger.budget += credits
            logger.info("Reward %.2f → %s (%s)", credits, agent, reason or "competition")
            self._save()

    def deduct_penalty(self, agent: str, *, credits: float, reason: str = "") -> None:
        """Deduct credits from an underperforming agent."""
        with _LOCK:
            ledger = self._ensure_agent(agent)
            ledger.budget = max(0.0, ledger.budget - credits)
            logger.info("Penalty %.2f ← %s (%s)", credits, agent, reason or "competition")
            self._save()

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def agent_metrics(self, agent: str) -> dict[str, Any]:
        """Return full ledger metrics for *agent*."""
        with _LOCK:
            return self._ensure_agent(agent).to_dict()

    def top_agents(self, *, limit: int = 10) -> list[dict[str, Any]]:
        """Return agents sorted by performance_score descending."""
        with _LOCK:
            agents = [l.to_dict() for l in self._agents.values()]
        return sorted(agents, key=lambda a: a["performance_score"], reverse=True)[:limit]

    def bottom_agents(self, *, limit: int = 5) -> list[dict[str, Any]]:
        """Return agents sorted by performance_score ascending (worst first)."""
        with _LOCK:
            agents = [l.to_dict() for l in self._agents.values() if l.tasks_completed + l.tasks_failed > 0]
        return sorted(agents, key=lambda a: a["performance_score"])[:limit]

    def system_summary(self) -> dict[str, Any]:
        """Return global economy KPIs."""
        with _LOCK:
            agent_count = len(self._agents)
            total_budget = sum(l.budget for l in self._agents.values())
        return {
            "total_agents": agent_count,
            "global_tasks": self._global_tasks,
            "global_value": round(self._global_value, 2),
            "global_cost": round(self._global_cost, 2),
            "global_profit": round(self._global_value - self._global_cost, 2),
            "global_roi": round(
                (self._global_value - self._global_cost) / max(self._global_cost, 1.0), 4
            ),
            "total_agent_budget": round(total_budget, 2),
            "ts": _ts(),
        }

    def recent_tasks(self, *, limit: int = 20) -> list[dict[str, Any]]:
        """Return most recent task log entries."""
        with _LOCK:
            return list(self._task_log[-limit:])

    def suggest_improvements(self, *, limit: int = 5) -> list[dict[str, Any]]:
        """Return economy-driven improvement suggestions (sorted by ROI impact).

        Identifies:
        - High-cost / low-value agents that should be optimized
        - Agents with high efficiency that should get more resources
        """
        with _LOCK:
            agents = [l.to_dict() for l in self._agents.values() if l.tasks_completed > 0]

        suggestions: list[dict[str, Any]] = []
        for a in agents:
            if a["roi"] < 0.1:
                suggestions.append({
                    "type": "optimize",
                    "agent": a["name"],
                    "reason": f"Low ROI ({a['roi']:.3f}) — candidate for forge rewrite",
                    "roi_impact": round(0.3 - a["roi"], 3),
                    "priority": "high",
                })
            elif a["performance_score"] > 0.8 and a["budget"] < _DEFAULT_BUDGET * 0.3:
                suggestions.append({
                    "type": "fund",
                    "agent": a["name"],
                    "reason": f"High performer ({a['performance_score']:.3f}) with low budget — increase allocation",
                    "roi_impact": round(a["roi"] * 0.2, 3),
                    "priority": "medium",
                })

        # Global suggestions
        summary = self.system_summary()
        if summary["global_roi"] < 0.5:
            suggestions.insert(0, {
                "type": "system",
                "agent": "all",
                "reason": f"Global ROI is low ({summary['global_roi']:.3f}) — review task cost calibration",
                "roi_impact": 0.5 - summary["global_roi"],
                "priority": "critical",
            })

        suggestions.sort(key=lambda s: s["roi_impact"], reverse=True)
        return suggestions[:limit]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure_agent(self, name: str) -> _AgentLedger:
        if name not in self._agents:
            self._agents[name] = _AgentLedger(name)
        return self._agents[name]

    def _save(self) -> None:
        try:
            payload = {
                "updated_at": _ts(),
                "global_tasks": self._global_tasks,
                "global_value": self._global_value,
                "global_cost": self._global_cost,
                "agents": {n: l.to_dict() for n, l in self._agents.items()},
            }
            self._path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except Exception as exc:  # noqa: BLE001
            logger.debug("Economy state save failed (non-fatal): %s", exc)

    def _load(self) -> None:
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            self._global_tasks = raw.get("global_tasks", 0)
            self._global_value = raw.get("global_value", 0.0)
            self._global_cost = raw.get("global_cost", 0.0)
            for name, d in (raw.get("agents") or {}).items():
                self._agents[name] = _AgentLedger.from_dict(d)
        except Exception:  # noqa: BLE001
            pass


# ── Singleton ─────────────────────────────────────────────────────────────────

_instance: EconomyEngine | None = None
_instance_lock = threading.Lock()


def get_economy_engine() -> EconomyEngine:
    """Return the process-wide EconomyEngine singleton."""
    global _instance
    with _instance_lock:
        if _instance is None:
            _instance = EconomyEngine()
    return _instance
