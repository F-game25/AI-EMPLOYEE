from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.bus import get_message_bus
from skills.library import SkillsManager


class JsonStore:
    def __init__(self, state_dir: Path | None = None) -> None:
        self.state_dir = state_dir or Path(os.environ.get("AI_EMPLOYEE_STATE_DIR", "state"))
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.skills = SkillsManager(state_dir=self.state_dir)
        self.bus = get_message_bus()

    def _path(self, name: str) -> Path:
        return self.state_dir / f"{name}.json"

    def read(self, name: str, default: Any) -> Any:
        p = self._path(name)
        if not p.exists():
            return default
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return default

    def write(self, name: str, value: Any) -> Any:
        p = self._path(name)
        p.write_text(json.dumps(value, indent=2, default=str), encoding="utf-8")
        return value

    def append(self, name: str, item: dict[str, Any]) -> dict[str, Any]:
        items = self.read(name, [])
        if not isinstance(items, list):
            items = []
        items.append(item)
        self.write(name, items)
        return item

    def create_task(self, task: str) -> dict[str, Any]:
        item = {
            "id": str(uuid.uuid4()),
            "task": task,
            "status": "queued",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "result": None,
        }
        self.append("tasks", item)
        self.bus.publish_sync("tasks", item)
        return item


store = JsonStore()
