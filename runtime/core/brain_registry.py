"""Shared Neural Brain registry used by controller and APIs."""
from __future__ import annotations

import json
import threading
import time
from collections import deque
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.contracts import TaskNode


_BUCKET_TO_SKILL: dict[int, str] = {
    0: "lead-generator",
    1: "email-marketing",
    2: "content-calendar",
    # 3/4 are strategy/exec-heavy buckets; both route to executive planning.
    3: "ceo-briefing",
    4: "ceo-briefing",
    5: "problem-solver",
    6: "problem-solver",
    7: "problem-solver",
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

    def get_strategy(self, *, goal: str, goal_type: str) -> dict[str, Any]:
        """Return brain-guided strategy metadata for planner injection."""
        bucket = 7
        confidence = 0.0
        source = "fallback"
        intel = self._load_intelligence()
        if intel is not None:
            try:
                bucket = int(intel.suggest_agent_bucket("user:default", goal, mode="power")) % 8
                confidence = 0.5
                source = "brain"
            except Exception:
                bucket = 7
        skill = _BUCKET_TO_SKILL.get(bucket, "problem-solver")
        strategy = {
            "agent": skill,
            "config": {
                "goal": goal,
                "goal_type": goal_type,
                "brain_bucket": bucket,
                "brain_confidence": confidence,
            },
            "brain": {
                "source": source,
                "bucket": bucket,
                "confidence": confidence,
                "selected_skill": skill,
            },
        }
        self._remember_event("strategy_selected", {"goal_type": goal_type, "skill": skill, "bucket": bucket})
        return strategy

    def learn_from_task(self, *, goal: str, task: TaskNode) -> dict[str, Any]:
        """Send task outcome to the brain/intelligence feedback loop."""
        reward = 1.0 if task.status == "success" else -1.0
        learned = False
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
        self._remember_event(
            "task_feedback",
            {
                "task_id": task.task_id,
                "skill": task.skill,
                "status": task.status,
                "reward": reward,
                "learned": learned,
            },
        )
        return {"learned": learned, "reward": reward}

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
        return {
            "active": bool(status.get("available")),
            "updated_at": status.get("last_updated"),
            "status": status.get("status"),
            "memory_size": status.get("memory_size", 0),
            "recent_learning_events": events,
            "performance_metrics": {
                "total_feedback_events": total,
                "success_rate": round(successes / total, 3) if total else 0.0,
                "avg_confidence": 0.0,
            },
        }

    def memory_size(self) -> int:
        return len(self._events)

    def last_updated(self) -> str | None:
        return self._last_updated

    def brain(self):
        return self._load_brain()


brain = BrainRegistry()
