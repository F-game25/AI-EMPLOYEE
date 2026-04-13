from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


class SkillsManager:
    def __init__(self, definitions_dir: Path | None = None, state_dir: Path | None = None) -> None:
        self.definitions_dir = definitions_dir or Path("runtime/skills/definitions")
        self.state_dir = state_dir or Path(os.environ.get("AI_EMPLOYEE_STATE_DIR", "state"))
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.custom_path = self.state_dir / "custom_agents.json"
        self._skills = self._load()

    def _load(self) -> dict[str, dict[str, Any]]:
        skills: dict[str, dict[str, Any]] = {}
        self.definitions_dir.mkdir(parents=True, exist_ok=True)
        for fp in sorted(self.definitions_dir.glob("*.json")):
            try:
                data = json.loads(fp.read_text(encoding="utf-8"))
                sid = data.get("id")
                if sid:
                    skills[str(sid)] = data
            except Exception:
                continue
        return skills

    def search(self, query: str) -> list[dict[str, Any]]:
        q = query.lower().strip()
        results = []
        for skill in self._skills.values():
            blob = " ".join(
                str(skill.get(k, ""))
                for k in ("id", "name", "category", "description", "system_prompt")
            ).lower()
            if q in blob:
                results.append(skill)
        return results

    def get(self, skill_id: str) -> dict[str, Any] | None:
        return self._skills.get(skill_id)

    def list_by_category(self, cat: str) -> list[dict[str, Any]]:
        return [s for s in self._skills.values() if s.get("category") == cat]

    def compose_prompt(self, skill_ids: list[str]) -> str:
        chunks: list[str] = []
        for sid in skill_ids:
            s = self._skills.get(sid)
            if not s:
                continue
            chunks.append(str(s.get("system_prompt", "")))
            ex = s.get("examples", [])
            if isinstance(ex, list) and ex:
                chunks.append("Examples:\n" + "\n".join(str(i) for i in ex))
        return "\n\n".join(c for c in chunks if c.strip())

    def _read_custom(self) -> list[dict[str, Any]]:
        if not self.custom_path.exists():
            return []
        try:
            data = json.loads(self.custom_path.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except Exception:
            return []

    def _write_custom(self, data: list[dict[str, Any]]) -> None:
        self.custom_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def create_custom_agent(self, payload: dict[str, Any]) -> dict[str, Any]:
        items = self._read_custom()
        items.append(payload)
        self._write_custom(items)
        return payload

    def list_custom_agents(self) -> list[dict[str, Any]]:
        return self._read_custom()

    def update_custom_agent(self, agent_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
        items = self._read_custom()
        for item in items:
            if str(item.get("id")) == agent_id:
                item.update(updates)
                self._write_custom(items)
                return item
        return None

    def delete_custom_agent(self, agent_id: str) -> bool:
        items = self._read_custom()
        new_items = [i for i in items if str(i.get("id")) != agent_id]
        if len(new_items) == len(items):
            return False
        self._write_custom(new_items)
        return True
