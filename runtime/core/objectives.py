from __future__ import annotations

import json
import os
from pathlib import Path
from threading import Lock
from typing import Any


class Objective:
    def __init__(self, id, system, goal, constraints, priority, status):
        self.id = id
        self.system = system  # "money_mode" or "ascend_forge"
        self.goal = goal
        self.constraints = constraints
        self.priority = priority
        self.status = status  # pending, running, completed

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "system": self.system,
            "goal": self.goal,
            "constraints": self.constraints,
            "priority": self.priority,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "Objective":
        return cls(
            payload.get("id"),
            payload.get("system"),
            payload.get("goal"),
            payload.get("constraints", {}),
            payload.get("priority", "medium"),
            payload.get("status", "pending"),
        )


class ObjectiveStore:
    def __init__(self, path: Path | None = None) -> None:
        root = Path(os.environ.get("AI_HOME", Path.cwd()))
        self._path = path or (root / "state" / "objectives.json")
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()
        if not self._path.exists():
            self._write_all([])

    def _read_all(self) -> list[Objective]:
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            if not isinstance(raw, list):
                return []
            return [Objective.from_dict(item) for item in raw if isinstance(item, dict)]
        except Exception:
            return []

    def _write_all(self, objectives: list[Objective]) -> None:
        self._path.write_text(
            json.dumps([obj.to_dict() for obj in objectives], ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def list(self, system: str | None = None) -> list[Objective]:
        with self._lock:
            data = self._read_all()
        if not system:
            return data
        return [obj for obj in data if obj.system == system]

    def upsert(self, objective: Objective) -> Objective:
        with self._lock:
            data = self._read_all()
            replaced = False
            for idx, item in enumerate(data):
                if item.id == objective.id:
                    data[idx] = objective
                    replaced = True
                    break
            if not replaced:
                data.append(objective)
            self._write_all(data)
        return objective

    def latest_for_system(self, system: str) -> Objective | None:
        rows = self.list(system)
        return rows[-1] if rows else None


_store: ObjectiveStore | None = None


def get_objective_store() -> ObjectiveStore:
    global _store
    if _store is None:
        _store = ObjectiveStore()
    return _store
