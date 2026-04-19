"""Self-Learning Brain — unified adaptive intelligence facade.

This module ties together every learning-capable subsystem in AI Employee:

- ``LearningEngine``          — episodic + strategy memory
- ``DecisionEngine``          — weighted action scoring
- ``brain_model`` functions   — per-agent reinforcement weights
- ``MemoryIndex``             — vector-based memory retrieval

Agents and the orchestrator interact *only* through the functions exported
here.  They never touch the subsystems directly.

Usage::

    from core.self_learning_brain import get_self_learning_brain

    slb = get_self_learning_brain()
    suggestion = slb.suggest_action(context="write a sales email for ACME")
    slb.record_outcome(
        action="email_ninja",
        success=True,
        context="write a sales email for ACME",
        result={"delivered": 1},
    )

Design
------
The brain follows a feedback loop:

    INPUT → suggest_action() → agent executes → record_outcome()
                ↑______________reinforcement_path___________________|

Every recorded outcome:
  1. Updates strategy success rates in LearningEngine
  2. Adjusts per-agent weights via brain_model.update_agent_model()
  3. Tunes DecisionEngine weights from ROI history
  4. Writes an episodic memory entry via LearningEngine
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any

from core.learning_engine import LearningEngine
from core.decision_engine import DecisionEngine, ActionSpec, get_decision_engine
import core.brain_model as _bm
from core.memory_index import MemoryIndex

logger = logging.getLogger("self_learning_brain")

_LOCK = threading.RLock()


def _ts() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# ── Neural brain (torch-optional) ─────────────────────────────────────────────

_neural_brain: Any = None
_neural_brain_loaded = False
_torch: Any = None  # cached torch module reference


def _ensure_neural_brain() -> Any:
    """Try to import the heavy neural brain exactly once (torch is optional)."""
    global _neural_brain, _neural_brain_loaded, _torch
    if _neural_brain_loaded:
        return _neural_brain
    _neural_brain_loaded = True
    try:
        import torch as _t  # type: ignore
        _torch = _t
        from brain.brain import get_brain  # type: ignore
        _neural_brain = get_brain()
    except Exception as exc:  # noqa: BLE001
        logger.debug("Neural brain not available (non-fatal): %s", exc)
        _neural_brain = None
    return _neural_brain


# ══════════════════════════════════════════════════════════════════════════════
# SelfLearningBrain
# ══════════════════════════════════════════════════════════════════════════════

class SelfLearningBrain:
    """Unified self-learning intelligence layer.

    Responsibilities
    ----------------
    - Detect successful vs failed actions and update strategy weights
    - Learn optimal execution paths over time via reinforcement
    - Strengthen connections between prompts → agents → outcomes
    - Surface the best agent/strategy for a given context
    - Correct failure patterns by downweighting bad paths
    """

    def __init__(self) -> None:
        self._learning_engine = LearningEngine()
        self._decision_engine: DecisionEngine = get_decision_engine()
        self._memory_index = MemoryIndex()
        self._outcomes: list[dict[str, Any]] = []
        logger.info("SelfLearningBrain initialised")

    # ------------------------------------------------------------------
    # Suggestion
    # ------------------------------------------------------------------

    def suggest_action(
        self,
        *,
        context: str,
        candidates: list[str] | None = None,
    ) -> dict[str, Any]:
        """Return the best agent/strategy for *context*.

        Args:
            context:    Free-text description of the task.
            candidates: Optional list of agent names to score.  When omitted
                        the brain model's known agents are used.

        Returns:
            A dict with keys:
              - ``agent``      — recommended agent name
              - ``strategy``   — recommended strategy id
              - ``confidence`` — 0–1 confidence score
              - ``reasoning``  — short explanation
              - ``memories``   — relevant past episodes
        """
        with _LOCK:
            # Retrieve relevant past experiences
            memories = self._learning_engine.search_memory(context, top_k=3)

            # Score candidate agents using brain model weights
            agent_model = _bm.get_agent_model()
            agent_names = candidates or list(agent_model.keys())
            if not agent_names:
                agent_names = ["task_orchestrator"]

            action_specs = []
            for name in agent_names:
                success_rate = self._learning_engine.agent_success_rate(name)
                weights = agent_model.get(name, {"speed": 0.5, "complexity_fit": 0.5})
                action_specs.append(
                    ActionSpec(
                        id=name,
                        skill=name,
                        profit_potential=success_rate * 10,
                        execution_speed=float(weights.get("speed", 0.5)) * 10,
                        complexity=max(
                            0.0, 10.0 - float(weights.get("complexity_fit", 0.5)) * 10
                        ),
                    )
                )

            ranked = self._decision_engine.rank_actions(action_specs)
            best = ranked[0] if ranked else ActionSpec(id="task_orchestrator", skill="task_orchestrator")

            # Best strategy from learning engine
            strategies = self._learning_engine.metrics().get("best_strategies", [])
            best_strategy = (
                strategies[0].get("strategy_id", "default") if strategies else "default"
            )

            confidence = min(1.0, best.score / 10.0) if best.score else 0.5

            return {
                "agent": best.id,
                "strategy": best_strategy,
                "confidence": round(confidence, 3),
                "reasoning": (
                    f"Agent '{best.id}' scored {best.score:.2f}/10 "
                    f"(profit={best.profit_potential:.1f}, speed={best.execution_speed:.1f}, "
                    f"complexity={best.complexity:.1f})"
                ),
                "memories": memories,
                "ts": _ts(),
            }

    # ------------------------------------------------------------------
    # Outcome recording (reinforcement)
    # ------------------------------------------------------------------

    def record_outcome(
        self,
        *,
        action: str,
        success: bool,
        context: str = "",
        result: dict[str, Any] | None = None,
        strategy: str = "default",
        duration_ms: int = 0,
    ) -> dict[str, Any]:
        """Record the outcome of an agent action and reinforce accordingly.

        Args:
            action:      Agent / action name that was executed.
            success:     Whether the action succeeded.
            context:     Original task description.
            result:      Arbitrary result payload from the agent.
            strategy:    Strategy identifier used (defaults to ``"default"``).
            duration_ms: Execution time in milliseconds.

        Returns:
            A dict with ``reward``, ``strategy_stats``, and ``agent_stats``.
        """
        success_score = 1.0 if success else 0.0
        result = result or {}

        with _LOCK:
            # 1. Learning engine: update strategy + agent stats + episodic memory
            le_result = self._learning_engine.record_task(
                task_input=context,
                chosen_agent=action,
                strategy_used=strategy,
                result=result,
                success_score=success_score,
                decision_reason=f"duration_ms={duration_ms}",
            )

            # 2. Brain model: reinforce or penalise agent weights (ignore unknown agents)
            reward = 0.1 if success else -0.1
            try:
                _bm.update_agent_model(action, reward)
            except (ValueError, KeyError):
                pass  # Agent not in the brain model yet — non-fatal

            # 3. Auto-tune decision engine weights every 20 outcomes
            history = self._learning_engine.metrics().get("reward_trend", [])
            if len(history) % 20 == 0 and history:
                roi_data = [
                    {
                        "profit_potential": 10 * max(0.0, float(r.get("reward", 0))),
                        "execution_speed": 5.0,
                        "complexity": 5.0,
                        "revenue": max(0.0, float(r.get("reward", 0))),
                    }
                    for r in history[-100:]
                ]
                self._decision_engine.tune_weights(roi_data)

            # 4. Neural brain feedback (torch-optional)
            neural = _ensure_neural_brain()
            if neural is not None and _torch is not None:
                try:
                    input_size = getattr(neural, "input_size", 16)
                    state = _torch.zeros(input_size)
                    neural.store_experience(state, 0, success_score, state)
                except Exception:  # noqa: BLE001
                    pass

            self._outcomes.append({
                "ts": _ts(),
                "action": action,
                "success": success,
                "context_snippet": context[:120],
                "strategy": strategy,
                "duration_ms": duration_ms,
            })

            return {
                "reward": le_result.get("reward", success_score),
                "strategy_stats": le_result.get("strategy", {}),
                "agent_stats": le_result.get("agent", {}),
            }

    # ------------------------------------------------------------------
    # Explicit reinforcement (strength/weakness adjustment)
    # ------------------------------------------------------------------

    def reinforce(self, action: str, reward: float) -> None:
        """Directly adjust the strength of an action by *reward* (-1 .. 1).

        Use this for explicit feedback not tied to a specific task result.
        """
        with _LOCK:
            reward = max(-1.0, min(1.0, float(reward)))
            try:
                _bm.update_agent_model(action, reward * 0.1)
            except (ValueError, KeyError):
                pass
            logger.debug("Reinforced %s by %.3f", action, reward)

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def metrics(self) -> dict[str, Any]:
        """Return a snapshot of brain health and learning progress."""
        with _LOCK:
            le = self._learning_engine.metrics()
            return {
                "avg_reward_recent": le.get("avg_reward_recent", 0.0),
                "best_strategies": le.get("best_strategies", []),
                "worst_strategies": le.get("worst_strategies", []),
                "total_outcomes_recorded": len(self._outcomes),
                "agent_weights": _bm.get_agent_model(),
                "decision_weights": self._decision_engine.weights,
                "ts": _ts(),
            }

    def recent_outcomes(self, *, limit: int = 20) -> list[dict[str, Any]]:
        """Return the most recently recorded outcomes."""
        with _LOCK:
            return list(self._outcomes[-limit:])


# ── Singleton ─────────────────────────────────────────────────────────────────

_instance: SelfLearningBrain | None = None
_instance_lock = threading.Lock()


def get_self_learning_brain() -> SelfLearningBrain:
    """Return the process-wide SelfLearningBrain singleton."""
    global _instance
    with _instance_lock:
        if _instance is None:
            _instance = SelfLearningBrain()
    return _instance
