"""Skill Registry — unified manifest of all available agents/skills.

Introspects the agents directory at startup and emits a JSON manifest so the
Planner can discover what capabilities exist.

Usage::

    from core.skill_registry import get_registry

    registry = get_registry()
    skills = registry.list_skills()          # all skills
    match  = registry.find_skill("email")    # fuzzy name search
    manifest = registry.to_json()            # full manifest dict
"""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any


_AGENTS_ROOT = Path(__file__).parent.parent / "agents"

# Hard-coded skill categories derived from agent names
_CATEGORY_MAP: dict[str, str] = {
    "lead": "money_generation",
    "sales": "money_generation",
    "affiliate": "money_generation",
    "revenue": "money_generation",
    "ecom": "money_generation",
    "referral": "money_generation",
    "arbitrage": "money_generation",
    "print-on-demand": "money_generation",
    "polymarket": "money_generation",
    "turbo-quant": "money_generation",
    "memecoin": "money_generation",
    "content": "task_execution",
    "faceless": "task_execution",
    "course": "task_execution",
    "newsletter": "task_execution",
    "email": "task_execution",
    "social": "task_execution",
    "brand": "task_execution",
    "ad-campaign": "task_execution",
    "paid-media": "task_execution",
    "creator": "task_execution",
    "memory": "memory_learning",
    "obsidian": "memory_learning",
    "feedback": "memory_learning",
    "brain": "memory_learning",
    "neural": "memory_learning",
    "intelligence": "memory_learning",
    "browser": "automation",
    "whatsapp": "automation",
    "discord": "automation",
    "webhook": "automation",
    "scheduler": "automation",
    "auto-updater": "automation",
    "task-orchestrator": "automation",
    "tools": "automation",
    "decision": "decision_engine",
    "goal": "decision_engine",
    "governance": "decision_engine",
    "qualification": "decision_engine",
    "discovery": "analytics",
    "competitor": "analytics",
    "financial": "analytics",
    "budget": "analytics",
    "status": "analytics",
    "analytics": "analytics",
    "ui": "ui_ux",
    "dashboard": "ui_ux",
    "meeting": "ui_ux",
    "ascend-forge": "ui_ux",
}


def _categorise(agent_name: str) -> str:
    for keyword, category in _CATEGORY_MAP.items():
        if keyword in agent_name:
            return category
    return "general"


def _scan_agents(root: Path) -> list[dict]:
    skills: list[dict] = []
    if not root.exists():
        return skills
    for item in sorted(root.iterdir()):
        if not item.is_dir() or item.name.startswith("_"):
            continue
        py_files = list(item.glob("*.py"))
        if not py_files:
            continue
        entry_point = next(
            (f for f in py_files if f.stem.replace("-", "_") == item.name.replace("-", "_")),
            py_files[0],
        )
        skills.append(
            {
                "name": item.name,
                "category": _categorise(item.name),
                "entry_point": str(entry_point.relative_to(root.parent.parent)),
                "inputs": {},   # extensible — agents can declare via __skill_inputs__
                "outputs": {},  # extensible — agents can declare via __skill_outputs__
            }
        )
    return skills


class SkillRegistry:
    """Lazy-loaded registry of all agent skills."""

    def __init__(self, agents_root: Path | None = None) -> None:
        self._root = agents_root or _AGENTS_ROOT
        self._lock = threading.Lock()
        self._skills: list[dict] | None = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure_loaded(self) -> None:
        if self._skills is None:
            self._skills = _scan_agents(self._root)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def list_skills(self, category: str | None = None) -> list[dict]:
        """Return all skills, optionally filtered by *category*."""
        with self._lock:
            self._ensure_loaded()
            skills = list(self._skills)  # type: ignore[arg-type]
        if category:
            skills = [s for s in skills if s["category"] == category]
        return skills

    def find_skill(self, query: str) -> dict | None:
        """Return the first skill whose name contains *query* (case-insensitive)."""
        q = query.lower()
        for skill in self.list_skills():
            if q in skill["name"].lower():
                return skill
        return None

    def categories(self) -> list[str]:
        """Return distinct category names present in the registry."""
        return sorted({s["category"] for s in self.list_skills()})

    def to_json(self) -> dict:
        """Return the full manifest as a JSON-serialisable dict."""
        skills = self.list_skills()
        by_category: dict[str, list] = {}
        for s in skills:
            by_category.setdefault(s["category"], []).append(s["name"])
        return {
            "total_skills": len(skills),
            "categories": self.categories(),
            "by_category": by_category,
            "skills": skills,
        }

    def reload(self) -> None:
        """Force a rescan of the agents directory."""
        with self._lock:
            self._skills = None


# ── Singleton ─────────────────────────────────────────────────────────────────

_instance: SkillRegistry | None = None
_instance_lock = threading.Lock()


def get_registry(agents_root: Path | None = None) -> SkillRegistry:
    """Return the process-wide SkillRegistry singleton."""
    global _instance
    with _instance_lock:
        if _instance is None:
            _instance = SkillRegistry(agents_root)
    return _instance
