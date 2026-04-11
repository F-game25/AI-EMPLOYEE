"""Skill catalog with class-based stateless skill modules."""
from __future__ import annotations

import threading
from typing import Any, Callable

from skills.base import SkillBase


class AgentDispatchSkill(SkillBase):
    """Generic stateless adapter from domain skill to infrastructure action."""

    def __init__(self, *, skill_name: str, description: str) -> None:
        self.name = skill_name
        self.description = description
        self.input_schema = {
            "type": "object",
            "properties": {"goal": {"type": "string"}},
            "required": ["goal"],
        }
        self.output_schema = {
            "type": "object",
            "properties": {
                "status": {"type": "string"},
                "action_result": {"type": "object"},
            },
            "required": ["status"],
        }
        self.allowed_actions = ["skill_dispatch"]

    def execute(
        self,
        input_data: dict[str, Any],
        action_runner: Callable[[str, dict[str, Any]], dict[str, Any]],
    ) -> dict[str, Any]:
        payload = {"skill": self.name, "input": input_data}
        action_result = action_runner("skill_dispatch", payload)
        return {"status": "success", "action_result": action_result}


class SkillCatalog:
    """In-memory catalog of declared domain skills."""

    def __init__(self) -> None:
        self._skills = self._build_default_skills()

    def _build_default_skills(self) -> dict[str, SkillBase]:
        configured = [
            ("content-calendar", "Creates content plans and ideas."),
            ("social-media-manager", "Adapts and schedules social posts."),
            ("lead-generator", "Produces lead generation outputs."),
            ("lead-crm", "Updates and tracks CRM lead state."),
            ("email-marketing", "Builds and coordinates email campaigns."),
            ("ceo-briefing", "Creates analytical business briefing outputs."),
            ("problem-solver", "General-purpose fallback execution skill."),
        ]
        return {
            skill_name: AgentDispatchSkill(skill_name=skill_name, description=desc)
            for skill_name, desc in configured
        }

    def get(self, name: str) -> SkillBase | None:
        return self._skills.get(name)

    def has(self, name: str) -> bool:
        return name in self._skills

    def all(self) -> dict[str, SkillBase]:
        return dict(self._skills)


_instance: SkillCatalog | None = None
_instance_lock = threading.Lock()


def get_skill_catalog() -> SkillCatalog:
    global _instance
    with _instance_lock:
        if _instance is None:
            _instance = SkillCatalog()
    return _instance
