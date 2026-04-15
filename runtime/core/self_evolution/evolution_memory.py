from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any


_DEFAULT_STATE = {
    "outcomes": [],
    "patches": [],
    "updated_at": None,
}


class EvolutionMemory:
    """Persistent memory for self-evolution outcomes and rewards."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or self._default_path()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._state = self._load()

    @staticmethod
    def _default_path() -> Path:
        ai_home = os.environ.get("AI_HOME")
        base = Path(ai_home) if ai_home else Path(__file__).resolve().parents[3]
        return base / "state" / "evolution_memory.json"

    @staticmethod
    def _ts() -> str:
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    def _load(self) -> dict[str, Any]:
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                state = dict(_DEFAULT_STATE)
                state.update(payload)
                return state
        except Exception:
            pass
        self._save(dict(_DEFAULT_STATE))
        return dict(_DEFAULT_STATE)

    def _save(self, state: dict[str, Any] | None = None) -> None:
        data = state if state is not None else self._state
        data["updated_at"] = self._ts()
        self._path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def record_patch(self, *, issue: dict[str, Any], patch_meta: dict[str, Any]) -> dict[str, Any]:
        row = {
            "id": f"patch-{int(time.time() * 1000)}",
            "ts": self._ts(),
            "issue": issue,
            "patch": patch_meta,
        }
        with self._lock:
            patches = self._state.setdefault("patches", [])
            patches.append(row)
            self._state["patches"] = patches[-500:]
            self._save()
        return row

    def record_outcome(
        self,
        *,
        issue: dict[str, Any],
        status: str,
        reward: int,
        detail: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        clamped_reward = max(-1, min(1, int(reward)))
        row = {
            "id": f"outcome-{int(time.time() * 1000)}",
            "ts": self._ts(),
            "issue": issue,
            "status": status,
            "reward": clamped_reward,
            "detail": detail or {},
        }
        with self._lock:
            outcomes = self._state.setdefault("outcomes", [])
            outcomes.append(row)
            self._state["outcomes"] = outcomes[-1000:]
            self._save()
        return row

    def summary(self) -> dict[str, Any]:
        with self._lock:
            outcomes = list(self._state.get("outcomes", []))
            patches = list(self._state.get("patches", []))
        total = len(outcomes)
        success = sum(1 for item in outcomes if item.get("reward") == 1)
        neutral = sum(1 for item in outcomes if item.get("reward") == 0)
        failed = sum(1 for item in outcomes if item.get("reward") == -1)
        avg_reward = round(sum(int(item.get("reward", 0)) for item in outcomes) / max(total, 1), 3)
        return {
            "total_outcomes": total,
            "success": success,
            "neutral": neutral,
            "failed": failed,
            "avg_reward": avg_reward,
            "patches_generated": len(patches),
            "recent_outcomes": outcomes[-20:],
            "updated_at": self._state.get("updated_at"),
        }


_instance: EvolutionMemory | None = None
_instance_lock = threading.Lock()


def get_evolution_memory(path: Path | None = None) -> EvolutionMemory:
    global _instance
    with _instance_lock:
        if _instance is None:
            _instance = EvolutionMemory(path)
        elif path is not None and _instance._path != path:
            _instance = EvolutionMemory(path)
    return _instance
