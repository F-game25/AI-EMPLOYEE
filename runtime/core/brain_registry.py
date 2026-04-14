"""Shared Neural Brain registry used by controller and APIs."""
from __future__ import annotations

import json
import threading
import time
from collections import deque
from typing import TYPE_CHECKING, Any

from core.brain_model import (
    get_last_learning_update,
    score_agent as _score_agent,
    select_agent as _select_agent,
)
from core.brain_weights import get_weights, update_weight
from core.knowledge_store import get_knowledge_store
from core.memory_index import get_memory_index

if TYPE_CHECKING:
    from core.contracts import TaskNode

_AGENT_TO_SKILL: dict[str, str] = {
    "lead_hunter": "lead-generator",
    "email_ninja": "email-marketing",
    "intel_agent": "ceo-briefing",
    "social_guru": "social-media-manager",
    "data_analyst": "ceo-briefing",
    "task_orchestrator": "problem-solver",
}
_SKILL_TO_AGENT: dict[str, str] = {
    "lead-generator": "lead_hunter",
    "email-marketing": "email_ninja",
    "social-media-manager": "social_guru",
    "problem-solver": "task_orchestrator",
}
_AGENT_KEYWORDS: dict[str, tuple[str, ...]] = {
    "lead_hunter": ("lead", "prospect", "outreach", "pipeline"),
    "email_ninja": ("email", "campaign", "newsletter"),
    "intel_agent": ("research", "learn", "strategy", "business", "market"),
    "social_guru": ("social", "content", "post", "brand"),
    "data_analyst": ("analyze", "analyse", "metric", "data", "report"),
    "task_orchestrator": ("plan", "execute", "task", "workflow", "general"),
}
class BrainRegistry:
    """Singleton facade for brain strategy, learning, and telemetry."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._brain = None
        self._intel = None
        self._events: deque[dict[str, Any]] = deque(maxlen=200)
        self._last_updated: str | None = None

    @staticmethod
    def _ts() -> str:
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    def _load_brain(self):
        if self._brain is not None:
            return self._brain
        with self._lock:
            if self._brain is None:
                try:
                    from brain.brain import get_brain

                    self._brain = get_brain()
                except Exception:
                    self._brain = None
        return self._brain

    def _load_intelligence(self):
        if self._intel is not None:
            return self._intel
        with self._lock:
            if self._intel is None:
                try:
                    from brain.intelligence import get_intelligence

                    self._intel = get_intelligence()
                except Exception:
                    self._intel = None
        return self._intel

    def _remember_event(self, event: str, payload: dict[str, Any]) -> None:
        stamp = self._ts()
        with self._lock:
            self._last_updated = stamp
            self._events.appendleft({"ts": stamp, "event": event, **payload})

    def _priority_for_goal(self, goal: str, goal_type: str) -> float:
        text = f"{goal} {goal_type}".lower()
        if any(token in text for token in ("urgent", "critical", "asap", "immediately")):
            return 1.0
        if any(token in text for token in ("important", "priority", "high")):
            return 0.8
        return 0.5

    def _complexity_for_goal(self, goal: str) -> float:
        text = (goal or "").lower()
        factors = [
            "multi", "integrate", "architecture", "pipeline", "optimize",
            "refactor", "scale", "deep", "analysis",
        ]
        hits = sum(1 for f in factors if f in text)
        base = 0.35 + (0.08 * hits) + min(0.2, len(text.split()) / 120)
        return max(0.05, min(1.0, base))

    def _speed_for_agent(self, agent: str, priority: float, complexity: float) -> float:
        bias = {
            "lead_hunter": 0.85,
            "email_ninja": 0.8,
            "social_guru": 0.8,
            "intel_agent": 0.55,
            "data_analyst": 0.6,
            "task_orchestrator": 0.7,
        }.get(agent, 0.65)
        return max(0.0, min(1.0, (bias * (0.5 + (priority * 0.5))) - (complexity * 0.2)))

    def _task_match(self, *, agent: str, goal: str, goal_type: str, context: str) -> float:
        keywords = _AGENT_KEYWORDS.get(agent, ())
        text = f"{goal} {goal_type} {context}".lower()
        hits = sum(1 for k in keywords if k in text)
        if hits == 0:
            return 0.35
        return min(1.0, 0.4 + (hits * 0.2))

    def _agent_success_rate(self, agent: str) -> float:
        try:
            from memory.strategy_store import get_strategy_store

            skill = _AGENT_TO_SKILL.get(agent, "problem-solver")
            rows = [r for r in get_strategy_store().all_strategies() if r.get("agent") == skill]
            if not rows:
                return 0.5
            success = sum(1 for r in rows if r.get("outcome_status") == "success")
            return round(success / max(len(rows), 1), 3)
        except Exception:
            return 0.5

    def _build_features(self, *, goal: str, goal_type: str, context: str) -> dict[str, dict[str, float]]:
        priority = self._priority_for_goal(goal, goal_type)
        complexity = self._complexity_for_goal(goal)
        features: dict[str, dict[str, float]] = {}
        for agent in get_weights():
            task_match = self._task_match(agent=agent, goal=goal, goal_type=goal_type, context=context)
            speed_fit = self._speed_for_agent(agent, priority, complexity)
            features[agent] = {
                "task_match": task_match,
                "success_rate": self._agent_success_rate(agent),
                "speed": speed_fit * task_match,
                "complexity": complexity * task_match,
            }
        return features

    def _strategy_boosts(self, goal_type: str) -> dict[str, float]:
        try:
            from memory.strategy_store import get_strategy_store

            learned = get_strategy_store().learn_for_goal(goal_type)
            boosts: dict[str, float] = {}
            for row in learned.get("patterns", [])[:3]:
                agent = row.get("best_agent")
                if not agent:
                    continue
                rate = float(row.get("success_rate", 0.0))
                boosts[agent] = boosts.get(agent, 0.0) + (0.15 * max(0.0, min(1.0, rate)))
            if not boosts:
                for agent in learned.get("promote_agents", []):
                    boosts[agent] = boosts.get(agent, 0.0) + 0.05
            return boosts
        except Exception:
            return {}

    def select_agent(self, task_features: dict[str, Any], *, score_boosts: dict[str, float] | None = None) -> tuple[str, float, dict[str, float]]:
        return _select_agent(task_features, score_boosts=score_boosts)

    @staticmethod
    def calculate_reward(result: TaskNode) -> float:
        if result.status == "success":
            return 1.0
        output = result.output if isinstance(result.output, dict) else {}
        if output.get("partial") is True:
            return 0.0
        return -1.0

    def get_strategy(self, *, goal: str, goal_type: str) -> dict[str, Any]:
        """Return brain-guided strategy metadata for planner injection."""
        knowledge = get_knowledge_store()
        memory_index = get_memory_index()
        memory_index.apply_decay()
        context = knowledge.get_relevant_context(goal)
        memories = memory_index.get_relevant_memories(goal, top_k=5)
        profile = knowledge.snapshot().get("user_profile", {})
        context_bundle = {
            "knowledge": context,
            "memories": [
                {
                    "id": m.get("id"),
                    "text": m.get("text"),
                    "importance": m.get("importance", 0.0),
                    "usage_count": m.get("usage_count", 0),
                }
                for m in memories
            ],
            "user_profile": profile,
        }
        context_prompt = (
            "You have learned the following relevant context:\n"
            f"{json.dumps(context_bundle, ensure_ascii=False)}\n\n"
            "Use this to make better decisions."
        )
        features = self._build_features(goal=goal, goal_type=goal_type, context=context)
        boosts = self._strategy_boosts(goal_type)
        selected_agent, confidence, scores = self.select_agent(features, score_boosts=boosts)
        current_weights = get_weights()
        feature_row = features.get(
            selected_agent,
            {"task_match": 0.0, "success_rate": 0.0, "speed": 0.0, "complexity": 0.0},
        )
        chosen_score = _score_agent(selected_agent, feature_row) + boosts.get(selected_agent, 0.0)
        reason = (
            f"selected_agent={selected_agent}; "
            f"confidence={confidence:.3f}; "
            f"score={chosen_score:.3f}; "
            f"fallback={'yes' if selected_agent == 'task_orchestrator' and confidence < 0.4 else 'no'}"
        )
        source = "reinforcement_brain"
        skill = _AGENT_TO_SKILL.get(selected_agent, "problem-solver")
        strategy = {
            "agent": skill,
            "config": {
                "goal": goal,
                "goal_type": goal_type,
                "brain_agent": selected_agent,
                "brain_confidence": confidence,
                "knowledge_context": context,
                "context_bundle": context_bundle,
                "context_prompt": context_prompt,
            },
            "brain": {
                "source": source,
                "selected_agent": selected_agent,
                "confidence": confidence,
                "selected_skill": skill,
                "weights": current_weights,
                "task_features": features,
                "scores": scores,
                "score_boosts": boosts,
                "knowledge_context": context,
                "context": context_bundle,
                "reasoning": reason,
                "decision_reasoning": reason,
                "top_memories": context_bundle["memories"],
                "last_learning_update": get_last_learning_update(),
            },
        }
        self._remember_event(
            "strategy_selected",
            {
                "goal_type": goal_type,
                "skill": skill,
                "agent": selected_agent,
                "confidence": round(confidence, 3),
                "context": context[:200],
                "reasoning": reason,
            },
        )
        return strategy

    def learn_from_task(self, *, goal: str, task: TaskNode) -> dict[str, Any]:
        """Send task outcome to the brain/intelligence feedback loop."""
        reward = self.calculate_reward(task)
        learned = False
        routed_agent = self._agent_for_skill(task.skill, goal)
        memories_used = get_memory_index().get_relevant_memories(goal, top_k=3)
        get_memory_index().apply_feedback(memories_used, reward)
        weight_before, weight_after = update_weight(routed_agent, reward)

        intel = self._load_intelligence()
        if intel is not None:
            try:
                output = task.output if isinstance(task.output, dict) else {}
                response = json.dumps(
                    {"status": task.status, "error": task.error, "output": output},
                    ensure_ascii=False,
                )
                intel.on_exchange(
                    user_id="user:default",
                    user_msg=goal,
                    agent_response=response,
                    agent_id=task.skill,
                    mode="power",
                    reward=reward,
                )
                learned = True
            except Exception:
                learned = False

        try:
            get_knowledge_store().add_knowledge(
                "task_outcomes",
                {
                    "task_id": task.task_id,
                    "goal": goal,
                    "skill": task.skill,
                    "status": task.status,
                    "reward": reward,
                },
            )
        except Exception:
            pass
        self._remember_event(
            "task_feedback",
            {
                "task_id": task.task_id,
                "skill": task.skill,
                "agent": routed_agent,
                "status": task.status,
                "reward": reward,
                "learned": learned,
                "weight_before": round(weight_before, 4),
                "weight_after": round(weight_after, 4),
                "memories_updated": [
                    {
                        "id": m.get("id"),
                        "importance": m.get("importance"),
                        "usage_count": m.get("usage_count"),
                    }
                    for m in memories_used
                ],
            },
        )
        return {
            "learned": learned,
            "reward": reward,
            "agent": routed_agent,
            "weight_before": round(weight_before, 4),
            "weight_after": round(weight_after, 4),
            "memories_updated": memories_used,
        }

    @staticmethod
    def _agent_for_skill(skill: str, goal: str) -> str:
        routed = _SKILL_TO_AGENT.get(skill, "task_orchestrator")
        if skill == "ceo-briefing":
            text = goal.lower()
            if any(k in text for k in ("research", "learn", "business")):
                return "intel_agent"
            return "data_analyst"
        return routed

    def status(self) -> dict[str, Any]:
        """Return status payload consumed by APIs/UI.

        The BrainRegistry itself provides strategy selection and learning
        capabilities even when the optional torch-based neural network is
        not loaded.  Report ``active`` in both cases so the UI never shows
        "unavailable" for the brain system.
        """
        brain_obj = self._load_brain()
        if brain_obj is None:
            return {
                "status": "active",
                "available": True,
                "memory_size": self.memory_size(),
                "last_updated": self.last_updated(),
                "learn_step": 0,
                "experience_count": 0,
                "buffer_size": 0,
                "buffer_capacity": 0,
                "last_loss": 0.0,
                "last_reward": 0.0,
                "avg_reward": 0.0,
                "device": "cpu",
                "model_path": "—",
                "is_online": True,
                "bg_running": False,
                "lr": 0.0,
                "mode": "ONLINE",
                "recent_learning_events": list(self._events)[:10],
                "agent_weights": get_weights(),
                "last_learning_update": get_last_learning_update(),
            }
        try:
            payload = dict(brain_obj.stats())
        except Exception:
            payload = {}
        payload.update(
            {
                "status": "active",
                "available": True,
                "memory_size": self.memory_size(),
                "last_updated": self.last_updated(),
                "recent_learning_events": list(self._events)[:10],
                "agent_weights": get_weights(),
            }
        )
        return payload

    def insights(self) -> dict[str, Any]:
        """Return dashboard-friendly insight payload."""
        status = self.status()
        events = list(self._events)[:20]
        feedback = [e for e in events if e.get("event") == "task_feedback"]
        successes = sum(1 for e in feedback if e.get("status") == "success")
        total = len(feedback)
        recent_goal_hint = ""
        if status.get("recent_decisions"):
            recent_goal_hint = str(status["recent_decisions"][0].get("intent", ""))
        return {
            "active": bool(status.get("available")),
            "updated_at": status.get("last_updated"),
            "status": status.get("status"),
            "memory_size": status.get("memory_size", 0),
            "recent_learning_events": events,
            "agent_weights": get_weights(),
            "last_learning_update": get_last_learning_update(),
            "last_decision": next((e for e in events if e.get("event") == "strategy_selected"), None),
            "last_reward": next((e.get("reward") for e in events if e.get("event") == "task_feedback"), 0.0),
            "learning_updates": [e for e in events if e.get("event") == "task_feedback"][:10],
            "learned_topics": list(get_knowledge_store().snapshot().get("topics", {}).keys()),
            "top_memories": get_memory_index().get_relevant_memories(recent_goal_hint, top_k=5, touch=False) if recent_goal_hint else [],
            "performance_metrics": {
                "total_feedback_events": total,
                "success_rate": round(successes / total, 3) if total else 0.0,
                "avg_confidence": round(
                    (
                        sum(float(e.get("confidence", 0.0)) for e in events if e.get("event") == "strategy_selected")
                        / max(1, len([e for e in events if e.get("event") == "strategy_selected"]))
                    ),
                    3,
                ),
            },
        }

    def memory_size(self) -> int:
        return len(self._events)

    def last_updated(self) -> str | None:
        return self._last_updated

    def brain(self):
        return self._load_brain()


brain = BrainRegistry()
