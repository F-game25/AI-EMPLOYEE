"""Skill catalog with class-based stateless skill modules."""
from __future__ import annotations

import json
from pathlib import Path
import threading
from typing import Any, Callable

from skills.base import SkillBase
from skills.context_research import ContextResearchSkill

# Capability tags per skill name
_SKILL_TAGS: dict[str, list[str]] = {
    "content-calendar": ["content", "planning", "scheduling"],
    "social-media-manager": ["content", "social", "publishing"],
    "lead-generator": ["sales", "outreach", "lead_generation"],
    "lead-crm": ["sales", "crm", "data_management"],
    "email-marketing": ["marketing", "email", "campaigns"],
    "ceo-briefing": ["analytics", "reporting", "business_intelligence"],
    "problem-solver": ["general", "fallback"],
    "context-research": ["research", "learning", "context"],
}


class AgentDispatchSkill(SkillBase):
    """Generic stateless adapter from domain skill to infrastructure action."""

    def __init__(
        self,
        *,
        skill_name: str,
        description: str,
        version: str = "1.0",
        capability_tags: list[str] | None = None,
    ) -> None:
        self.name = skill_name
        self.description = description
        self.version = version
        self.capability_tags = capability_tags if capability_tags is not None else []
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
        # Honest status: only "executed"/"success" count as success. unknown_action
        # or error must surface as a real failure — never a fake success.
        bus_status = (action_result or {}).get("status")
        ok = bus_status in ("executed", "success")
        result_obj = (action_result or {}).get("result") or {}
        return {
            "status": "success" if ok else "failed",
            "action_result": action_result,
            "output": result_obj.get("output") if ok else None,
            "error": "" if ok else ((action_result or {}).get("error") or f"action not executed (status={bus_status})"),
        }


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
        skills: dict[str, SkillBase] = {
            skill_name: AgentDispatchSkill(
                skill_name=skill_name,
                description=desc,
                capability_tags=list(_SKILL_TAGS.get(skill_name, [])),
            )
            for skill_name, desc in configured
        }
        # First-class skill: context research (executable directly, no dispatch indirection)
        skills["context-research"] = ContextResearchSkill()
        skills.update(self._load_configured_skills(existing=set(skills)))
        return skills

    def _load_configured_skills(self, *, existing: set[str]) -> dict[str, SkillBase]:
        config_path = Path(__file__).resolve().parents[1] / "config" / "skills_library.json"
        try:
            raw = json.loads(config_path.read_text(encoding="utf-8"))
        except Exception:
            return {}

        entries = raw if isinstance(raw, list) else raw.get("skills", [])
        if not isinstance(entries, list):
            return {}

        loaded: dict[str, SkillBase] = {}
        for item in entries:
            if not isinstance(item, dict):
                continue
            skill_id = str(item.get("id") or item.get("skill_id") or "").strip()
            if not skill_id or skill_id in existing:
                continue
            tags = item.get("tags") if isinstance(item.get("tags"), list) else []
            category = str(item.get("category") or "").strip().lower().replace(" ", "_")
            capability_tags = [str(tag) for tag in tags if str(tag).strip()]
            if category:
                capability_tags.append(category)
            if not capability_tags:
                capability_tags = ["configured"]
            loaded[skill_id] = AgentDispatchSkill(
                skill_name=skill_id,
                description=str(item.get("description") or item.get("name") or "Configured skill."),
                version=str(item.get("version") or "1.0"),
                capability_tags=capability_tags,
            )
        return loaded

    def get(self, name: str) -> SkillBase | None:
        return self._skills.get(name)

    def has(self, name: str) -> bool:
        return name in self._skills

    def all(self) -> dict[str, SkillBase]:
        return dict(self._skills)

    def list_skills(self) -> list[str]:
        return sorted(self._skills)


_instance: SkillCatalog | None = None
_instance_lock = threading.Lock()


def get_skill_catalog() -> SkillCatalog:
    global _instance
    with _instance_lock:
        if _instance is None:
            _instance = SkillCatalog()
    return _instance
