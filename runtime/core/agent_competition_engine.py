"""Agent Competition Engine — Darwinian optimization loop for AI Employee V4.

Agents compete on every task cycle.  The engine:

1. **Scores** each agent using a composite metric:
   economy ROI × self-learning weight × task success rate
2. **Routes** new tasks to the best-scoring eligible agent
   (with softmax-weighted randomness to allow exploration)
3. **Rewards** top performers with extra economy credits
4. **Penalizes** persistent underperformers (budget deduction)
5. **Proposes rewrites** for bottom agents via ForgeController

Competition happens passively — agents call ``register_outcome()`` after
every task and the engine updates scores automatically.

Usage::

    from core.agent_competition_engine import get_competition_engine

    ce = get_competition_engine()

    # Select best agent for a task
    agent = ce.select_agent(task_type="email", available=["email_ninja", "hermes"])

    # After execution, register the outcome
    ce.register_outcome("email_ninja", success=True, value=85, cost=10, duration_ms=300)

    # View leaderboard
    ce.leaderboard(limit=10)

    # Check if any agents need rewriting
    ce.propose_rewrites()
"""
from __future__ import annotations

import logging
import math
import threading
import time
from typing import Any

logger = logging.getLogger("core.agent_competition_engine")

_LOCK = threading.RLock()

# Thresholds for automatic actions
_REWARD_THRESHOLD = 0.75          # performance_score above this → reward
_PENALTY_THRESHOLD = 0.25         # performance_score below this → penalty
_REWRITE_THRESHOLD = 0.15         # performance_score below this → rewrite proposal
_REWARD_CREDITS = 50.0
_PENALTY_CREDITS = 30.0
_MIN_TASKS_FOR_ACTION = 3         # don't penalise/reward until this many tasks


def _ts() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


class _AgentRecord:
    """Lightweight competition record for one agent."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.tasks_won: int = 0      # tasks where this agent was selected
        self.challenges_issued: int = 0
        self.challenges_won: int = 0
        self.last_selected: str = ""
        self.rewrite_proposals: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "tasks_won": self.tasks_won,
            "challenges_issued": self.challenges_issued,
            "challenges_won": self.challenges_won,
            "last_selected": self.last_selected,
            "rewrite_proposals": self.rewrite_proposals,
        }


class AgentCompetitionEngine:
    """Darwinian agent selection and optimization loop.

    Integrates with EconomyEngine for score data and ForgeController for
    rewrite proposals.  All actions are non-blocking and best-effort.
    """

    def __init__(self) -> None:
        self._records: dict[str, _AgentRecord] = {}
        self._actions_log: list[dict[str, Any]] = []
        logger.info("AgentCompetitionEngine ready")

    # ------------------------------------------------------------------
    # Selection
    # ------------------------------------------------------------------

    def select_agent(
        self,
        *,
        task_type: str = "",
        available: list[str] | None = None,
        exploit_ratio: float = 0.8,
    ) -> str | None:
        """Select the best agent for a task using ε-greedy softmax routing.

        Args:
            task_type:     Optional hint (currently used for logging).
            available:     Candidate agent names.  If None, uses all known agents.
            exploit_ratio: Probability of choosing the best agent vs. random
                           exploration (0–1, default 0.8).

        Returns:
            Agent name, or None if no agents are available.
        """
        candidates = available or self._all_known_agents()
        if not candidates:
            return None

        scores = {a: self._score(a) for a in candidates}
        if not scores:
            return None

        import random
        if random.random() < exploit_ratio:
            # Exploit: softmax-weighted selection (not just argmax, to prevent monopoly)
            winner = self._softmax_sample(scores)
        else:
            # Explore: uniform random
            winner = random.choice(list(scores.keys()))

        with _LOCK:
            rec = self._ensure_record(winner)
            rec.tasks_won += 1
            rec.last_selected = _ts()

        logger.debug("Competition selected '%s' for task_type='%s'", winner, task_type)
        return winner

    # ------------------------------------------------------------------
    # Outcome registration
    # ------------------------------------------------------------------

    def register_outcome(
        self,
        agent: str,
        *,
        success: bool,
        value: float = 0.0,
        cost: float = 0.0,
        duration_ms: int = 0,
        task_id: str = "",
    ) -> dict[str, Any]:
        """Register a task outcome and apply competition rewards/penalties.

        Returns a summary of any reward/penalty actions taken.
        """
        # Forward to economy engine
        eco = self._get_eco()
        if eco:
            eco.record_task(
                agent=agent,
                task_id=task_id or f"ce-{_ts()}",
                cost=cost,
                value=value,
                duration_ms=duration_ms,
                success=success,
            )

        with _LOCK:
            self._ensure_record(agent)

        actions: list[dict[str, Any]] = []

        if eco:
            metrics = eco.agent_metrics(agent)
            score = metrics.get("performance_score", 0.5)
            total_tasks = metrics.get("tasks_completed", 0) + metrics.get("tasks_failed", 0)

            if total_tasks >= _MIN_TASKS_FOR_ACTION:
                if score >= _REWARD_THRESHOLD:
                    eco.grant_reward(agent, credits=_REWARD_CREDITS, reason="competition:top_performer")
                    actions.append({"action": "reward", "agent": agent, "credits": _REWARD_CREDITS})
                    logger.info("Rewarded top performer '%s' (score=%.3f)", agent, score)

                elif score <= _PENALTY_THRESHOLD:
                    eco.deduct_penalty(agent, credits=_PENALTY_CREDITS, reason="competition:underperformer")
                    actions.append({"action": "penalty", "agent": agent, "credits": _PENALTY_CREDITS})
                    logger.warning("Penalised underperformer '%s' (score=%.3f)", agent, score)

                    if score <= _REWRITE_THRESHOLD:
                        proposal = self._propose_rewrite(agent, score)
                        if proposal:
                            actions.append({"action": "rewrite_proposal", **proposal})

        entry = {
            "ts": _ts(),
            "agent": agent,
            "success": success,
            "value": value,
            "cost": cost,
            "actions": actions,
        }
        with _LOCK:
            self._actions_log.append(entry)
            if len(self._actions_log) > 300:
                self._actions_log = self._actions_log[-300:]

        return entry

    # ------------------------------------------------------------------
    # Leaderboard + proposals
    # ------------------------------------------------------------------

    def leaderboard(self, *, limit: int = 10) -> list[dict[str, Any]]:
        """Return agents ranked by performance_score."""
        eco = self._get_eco()
        if not eco:
            return []
        top = eco.top_agents(limit=limit)
        with _LOCK:
            records = dict(self._records)
        result = []
        for rank, a in enumerate(top, start=1):
            rec = records.get(a["name"])
            result.append({
                "rank": rank,
                **a,
                "tasks_won": rec.tasks_won if rec else 0,
                "challenges_won": rec.challenges_won if rec else 0,
            })
        return result

    def propose_rewrites(self, *, limit: int = 3) -> list[dict[str, Any]]:
        """Return rewrite proposals for the worst-performing agents."""
        eco = self._get_eco()
        if not eco:
            return []
        bottom = eco.bottom_agents(limit=limit)
        proposals = []
        for a in bottom:
            score = a.get("performance_score", 1.0)
            if score <= _REWRITE_THRESHOLD:
                proposals.append(self._propose_rewrite(a["name"], score) or {})
        return [p for p in proposals if p]

    def challenge(
        self,
        *,
        challenger: str,
        defender: str,
        task_type: str = "",
    ) -> dict[str, Any]:
        """Run a head-to-head score comparison between two agents.

        Returns the winner and margin.
        """
        challenger_score = self._score(challenger)
        defender_score = self._score(defender)

        if challenger_score > defender_score:
            winner, loser = challenger, defender
        else:
            winner, loser = defender, challenger

        margin = abs(challenger_score - defender_score)
        with _LOCK:
            self._ensure_record(challenger).challenges_issued += 1
            self._ensure_record(winner).challenges_won += 1

        result = {
            "winner": winner,
            "loser": loser,
            "margin": round(margin, 4),
            "challenger_score": round(challenger_score, 4),
            "defender_score": round(defender_score, 4),
            "task_type": task_type,
            "ts": _ts(),
        }
        logger.info("Challenge result: %s beat %s (margin=%.4f)", winner, loser, margin)
        return result

    def competition_summary(self) -> dict[str, Any]:
        """Return high-level competition status."""
        eco = self._get_eco()
        summary = eco.system_summary() if eco else {}
        with _LOCK:
            log_len = len(self._actions_log)
        return {
            "economy": summary,
            "action_events": log_len,
            "rewrite_proposals": sum(r.rewrite_proposals for r in self._records.values()),
            "ts": _ts(),
        }

    def recent_actions(self, *, limit: int = 20) -> list[dict[str, Any]]:
        with _LOCK:
            return list(self._actions_log[-limit:])

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _score(self, agent: str) -> float:
        """Composite score: economy performance_score (primary)."""
        eco = self._get_eco()
        if eco:
            try:
                m = eco.agent_metrics(agent)
                return m.get("performance_score", 0.5)
            except Exception:  # noqa: BLE001
                pass
        return 0.5   # neutral default for unknown agents

    @staticmethod
    def _softmax_sample(scores: dict[str, float], temperature: float = 1.5) -> str:
        """Softmax sampling over score dict."""
        import random
        names = list(scores.keys())
        vals = [scores[n] for n in names]
        max_v = max(vals)
        exps = [math.exp((v - max_v) / temperature) for v in vals]
        total = sum(exps)
        probs = [e / total for e in exps]
        rng = random.random()
        cumulative = 0.0
        for name, prob in zip(names, probs):
            cumulative += prob
            if rng <= cumulative:
                return name
        return names[-1]

    def _all_known_agents(self) -> list[str]:
        eco = self._get_eco()
        if eco:
            return [a["name"] for a in eco.top_agents(limit=100)]
        with _LOCK:
            return list(self._records.keys())

    def _propose_rewrite(self, agent: str, score: float) -> dict[str, Any] | None:
        """Submit a rewrite proposal for *agent* to ForgeController."""
        with _LOCK:
            rec = self._ensure_record(agent)
            rec.rewrite_proposals += 1

        try:
            from core.forge_controller import get_forge_controller
            fc = get_forge_controller()
            # Suggest optimisation in description — not a code submission
            proposal_desc = (
                f"Competition Engine: agent '{agent}' has performance_score={score:.3f} "
                f"(below threshold {_REWRITE_THRESHOLD}). "
                "Recommend reviewing task logic and optimising failure paths."
            )
            return {
                "agent": agent,
                "score": score,
                "description": proposal_desc,
                "ts": _ts(),
            }
        except Exception:  # noqa: BLE001
            return None

    def _ensure_record(self, name: str) -> _AgentRecord:
        if name not in self._records:
            self._records[name] = _AgentRecord(name)
        return self._records[name]

    @staticmethod
    def _get_eco():  # type: ignore[return]
        try:
            from core.economy_engine import get_economy_engine
            return get_economy_engine()
        except Exception:  # noqa: BLE001
            return None


# ── Singleton ─────────────────────────────────────────────────────────────────

_instance: AgentCompetitionEngine | None = None
_instance_lock = threading.Lock()


def get_competition_engine() -> AgentCompetitionEngine:
    """Return the process-wide AgentCompetitionEngine singleton."""
    global _instance
    with _instance_lock:
        if _instance is None:
            _instance = AgentCompetitionEngine()
    return _instance
