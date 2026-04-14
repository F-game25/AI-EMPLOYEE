"""Real learning loop engine with decision-impacting memory retrieval."""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any

from core.knowledge_store import get_knowledge_store
from core.memory_index import cosine_similarity, embed_text

_SHORT_TERM_LIMIT = 20
_EPISODIC_LIMIT = 500
_LOCK = threading.RLock()

_DEFAULT_STATE: dict[str, Any] = {
    "strategy_weights": {},
    "agent_stats": {},
    "short_term_memory": [],
    "episodic_memory": [],
    "reward_history": [],
    "updated_at": None,
}


def _ts() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _state_path() -> Path:
    home = os.getenv("AI_HOME")
    base = Path(home) if home else Path(__file__).resolve().parents[2]
    path = base / "state" / "learning_engine.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _clamp_reward(value: float) -> float:
    allowed = (-1.0, 0.0, 0.5, 1.0)
    val = float(value)
    return min(allowed, key=lambda x: abs(x - val))


def _running_avg(current: float, count: int, value: float) -> float:
    if count <= 1:
        return float(value)
    return ((float(current) * (count - 1)) + float(value)) / count


def _tokens(text: str, *, limit: int = 8) -> list[str]:
    clean = [t.strip(".,:;!?()[]{}\"'").lower() for t in (text or "").split()]
    return [t for t in clean if t][:limit]


class LearningEngine:
    def __init__(self, path: Path | None = None) -> None:
        self._path = path or _state_path()
        self._state = self._load()

    def _load(self) -> dict[str, Any]:
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                merged = dict(_DEFAULT_STATE)
                merged.update(payload)
                return merged
        except Exception:
            pass
        self._save(dict(_DEFAULT_STATE))
        return dict(_DEFAULT_STATE)

    def _save(self, state: dict[str, Any] | None = None) -> None:
        data = state if state is not None else self._state
        data["updated_at"] = _ts()
        self._path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def add_conversation_message(self, *, role: str, message: str) -> None:
        text = (message or "").strip()
        if not text:
            return
        with _LOCK:
            memory = self._state.setdefault("short_term_memory", [])
            memory.append({"ts": _ts(), "role": role or "user", "text": text[:500]})
            self._state["short_term_memory"] = memory[-_SHORT_TERM_LIMIT:]
            self._save()

    def strategy_success_rate(self, strategy_id: str) -> float:
        row = self._state.get("strategy_weights", {}).get(strategy_id, {})
        return float(row.get("success_rate", 0.5))

    def agent_success_rate(self, agent: str) -> float:
        row = self._state.get("agent_stats", {}).get(agent, {})
        return float(row.get("success_rate", 0.5))

    def search_memory(self, query: str, *, top_k: int = 5) -> dict[str, list[dict[str, Any]]]:
        q = (query or "").strip()
        if not q:
            return {"short_term": [], "long_term": [], "episodic": []}
        query_emb = embed_text(q)
        query_tokens = set(_tokens(q, limit=12))
        with _LOCK:
            short = [
                msg for msg in self._state.get("short_term_memory", [])
                if any(tok in msg.get("text", "").lower() for tok in query_tokens)
            ][-_SHORT_TERM_LIMIT:]
            episodic_ranked: list[dict[str, Any]] = []
            for item in self._state.get("episodic_memory", []):
                emb = item.get("context_embedding") or []
                sim = cosine_similarity(query_emb, emb)
                text = f"{item.get('task_input', '')} {item.get('strategy_used', '')}".lower()
                keyword = 1.0 if any(tok in text for tok in query_tokens) else 0.0
                score = (sim * 0.7) + (keyword * 0.3)
                episodic_ranked.append({"_score": score, **item})
            episodic = sorted(episodic_ranked, key=lambda x: x.get("_score", 0.0), reverse=True)[: max(1, top_k)]
        long_term = get_knowledge_store().search_knowledge(q)[: max(1, top_k)]
        return {
            "short_term": short[-max(1, top_k):],
            "long_term": long_term,
            "episodic": episodic,
        }

    def record_task(
        self,
        *,
        task_input: str,
        chosen_agent: str,
        strategy_used: str,
        result: dict[str, Any],
        success_score: float,
        decision_reason: str = "",
        memories_used: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        reward = _clamp_reward(success_score)
        memories_used = memories_used or []
        with _LOCK:
            strategies = self._state.setdefault("strategy_weights", {})
            strat = strategies.setdefault(
                strategy_used,
                {
                    "strategy_id": strategy_used,
                    "use_count": 0,
                    "success_rate": 0.5,
                    "avg_reward": 0.0,
                    "contexts_used_in": [],
                    "updated_at": None,
                },
            )
            strat["use_count"] = int(strat.get("use_count", 0)) + 1
            prior_successes = float(strat.get("success_rate", 0.5)) * (strat["use_count"] - 1)
            strat["success_rate"] = round((prior_successes + (1.0 if reward > 0 else 0.0)) / strat["use_count"], 4)
            strat["avg_reward"] = round(_running_avg(float(strat.get("avg_reward", 0.0)), strat["use_count"], reward), 4)
            contexts = list(strat.get("contexts_used_in", []))
            for token in _tokens(task_input):
                if token not in contexts:
                    contexts.append(token)
            strat["contexts_used_in"] = contexts[-30:]
            strat["updated_at"] = _ts()

            agents = self._state.setdefault("agent_stats", {})
            agent = agents.setdefault(chosen_agent, {"use_count": 0, "success_rate": 0.5, "avg_reward": 0.0, "updated_at": None})
            agent["use_count"] = int(agent.get("use_count", 0)) + 1
            prior_agent_successes = float(agent.get("success_rate", 0.5)) * (agent["use_count"] - 1)
            agent["success_rate"] = round((prior_agent_successes + (1.0 if reward > 0 else 0.0)) / agent["use_count"], 4)
            agent["avg_reward"] = round(_running_avg(float(agent.get("avg_reward", 0.0)), agent["use_count"], reward), 4)
            agent["updated_at"] = _ts()

            episodic = self._state.setdefault("episodic_memory", [])
            episodic.append(
                {
                    "id": f"ep-{abs(hash((task_input, strategy_used, _ts()))) % 10_000_000}",
                    "ts": _ts(),
                    "task_input": task_input,
                    "chosen_agent": chosen_agent,
                    "strategy_used": strategy_used,
                    "result": result,
                    "success_score": reward,
                    "decision_reason": decision_reason,
                    "memories_used": memories_used,
                    "context_embedding": embed_text(task_input),
                }
            )
            self._state["episodic_memory"] = episodic[-_EPISODIC_LIMIT:]

            reward_history = self._state.setdefault("reward_history", [])
            reward_history.append({"ts": _ts(), "strategy_id": strategy_used, "agent": chosen_agent, "reward": reward})
            self._state["reward_history"] = reward_history[-_EPISODIC_LIMIT:]

            self._save()
            return {
                "reward": reward,
                "strategy": dict(strat),
                "agent": dict(agent),
                "memory_sizes": {
                    "short_term": len(self._state.get("short_term_memory", [])),
                    "long_term": len(get_knowledge_store().snapshot().get("insights", [])),
                    "episodic": len(self._state.get("episodic_memory", [])),
                },
            }

    def metrics(self) -> dict[str, Any]:
        with _LOCK:
            strategies = list(self._state.get("strategy_weights", {}).values())
            strategies_sorted = sorted(strategies, key=lambda s: (float(s.get("success_rate", 0.0)), int(s.get("use_count", 0))), reverse=True)
            reward_history = self._state.get("reward_history", [])
            recent_rewards = reward_history[-50:]
            avg_reward = round(sum(float(r.get("reward", 0.0)) for r in recent_rewards) / max(len(recent_rewards), 1), 4) if recent_rewards else 0.0
            return {
                "strategies": strategies,
                "best_strategies": strategies_sorted[:5],
                "worst_strategies": list(reversed(strategies_sorted[-5:])),
                "reward_trend": recent_rewards,
                "avg_reward_recent": avg_reward,
                "memory_sizes": {
                    "short_term": len(self._state.get("short_term_memory", [])),
                    "long_term": len(get_knowledge_store().snapshot().get("insights", [])),
                    "episodic": len(self._state.get("episodic_memory", [])),
                },
            }


_instance: LearningEngine | None = None
_instance_lock = threading.Lock()


def get_learning_engine(path: Path | None = None) -> LearningEngine:
    global _instance
    with _instance_lock:
        if _instance is None:
            _instance = LearningEngine(path)
        elif path is not None and _instance._path != path:
            _instance = LearningEngine(path)
    return _instance
