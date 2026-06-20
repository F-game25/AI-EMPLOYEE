"""Skill catalog with class-based stateless skill modules.

``SkillCatalog`` manages ``SkillBase`` instances for the orchestrator.
``ExecutableSkillRegistry`` (also a singleton, exposed via
``get_skill_catalog()``) extends it with ``register_skill()``,
``execute_skill()``, and ``find_for_goal()`` for use by API routes and
direct skill execution.
"""
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


def get_skill_catalog() -> "ExecutableSkillCatalog":
    """Return the ExecutableSkillCatalog singleton."""
    global _instance
    with _instance_lock:
        if _instance is None:
            _instance = ExecutableSkillCatalog()
    return _instance  # type: ignore[return-value]


# ── Executable skill registry ─────────────────────────────────────────────────

class ExecutableSkillCatalog(SkillCatalog):
    """SkillCatalog extended with register/execute/find_for_goal for API use."""

    def __init__(self) -> None:
        super().__init__()
        self._exec_skills: dict[str, dict[str, Any]] = {}
        self._register_exec_defaults()

    # ── Registration ──────────────────────────────────────────────────────────

    def register_skill(self, name: str, version: str, fn: Callable,
                       tools_required: list[str], description: str,
                       risk_level: int = 1) -> None:
        self._exec_skills[name] = {
            "name": name, "version": version, "fn": fn,
            "tools": tools_required, "description": description,
            "risk_level": risk_level,
        }

    # ── Lookup ────────────────────────────────────────────────────────────────

    def get_skill(self, name: str) -> dict | None:
        return self._exec_skills.get(name)

    def list_skills(self) -> list[dict]:  # type: ignore[override]
        return [
            {
                "name": k, "version": v["version"],
                "description": v["description"],
                "tools": v["tools"], "risk_level": v["risk_level"],
            }
            for k, v in self._exec_skills.items()
        ]

    def find_for_goal(self, goal: str) -> list[dict]:
        gl = goal.lower()
        return [s for s in self.list_skills()
                if any(w in gl for w in s["description"].lower().split())]

    # ── Execution ─────────────────────────────────────────────────────────────

    def execute_skill(self, name: str, params: dict,
                      agent_id: str = "system") -> dict:
        skill = self._exec_skills.get(name)
        if not skill:
            return {"ok": False, "error": f"Skill '{name}' not found"}
        try:
            return {"ok": True, "skill": name, "result": skill["fn"](**params)}
        except Exception as e:
            return {"ok": False, "skill": name, "error": str(e)}

    # ── Unified dispatch (the one skill chain) ─────────────────────────────────

    def dispatch_for_goal(self, goal: str, ctx: dict | None = None) -> dict:
        """Run a free-text goal through the SAME skill chain the Executor uses.

        Two entry shapes, one chain: the Executor dispatches by skill *name*
        (``get(name).execute``); goal-shaped callers (companion broker, agents)
        dispatch here by *goal*. We first try a tool-composing executable skill
        (skill -> ToolRegistry -> real tools), and only fall back to the library
        LLM-prompt path when no executable skill matches. Never raises.
        """
        ctx = ctx or {}
        goal = (goal or "").strip()
        if not goal:
            return {"status": "error", "note": "no goal provided"}

        # 1) Tool-composing executable skill — explicit id or best description match.
        wanted = str(ctx.get("skill_id") or "").strip()
        name = wanted if (wanted and self.get_skill(wanted)) else None
        if name is None:
            matches = self.find_for_goal(goal)
            name = matches[0]["name"] if matches else None
        if name:
            # Executable skill fns take a primary free-text arg (topic/query/goal)
            # + **kwargs; pass all aliases and let the fn pick. Wrong-shaped skills
            # (e.g. needing a file path) raise -> caught -> library fallback.
            res = self.execute_skill(name, {"topic": goal, "query": goal, "goal": goal},
                                     agent_id=str(ctx.get("agent_id") or "system"))
            if res.get("ok"):
                return {"status": "ok", "skill_id": name, "via": "skill_catalog_tools",
                        "tools": (self.get_skill(name) or {}).get("tools", []),
                        "output": res.get("result")}

        # 2) Library skill via the LLM, guided by its own system_prompt.
        return self._run_library_skill(goal, ctx)

    @staticmethod
    def _run_library_skill(goal: str, ctx: dict) -> dict:
        """Select the best-matching library skill and run it via the LLM, guided
        by the skill's own system_prompt/execution_steps. Honest: no match or no
        LLM -> structured note, never a fabricated success."""
        try:
            from forge.lifecycle.skill_selector import select_skills, _load_skills
        except Exception as exc:  # noqa: BLE001
            return {"status": "unavailable", "note": f"skill selector not importable: {exc}"}
        skill = None
        wanted = str(ctx.get("skill_id") or "").strip()
        if wanted:
            skill = next((s for s in _load_skills() if s.get("id") == wanted), None)
        if skill is None:
            picks = select_skills(goal, str(ctx.get("task_type") or "chat"), max_skills=1)
            skill = picks[0] if picks else None
        if skill is None:
            return {"status": "no_skill", "note": "no matching skill in the library for this goal"}
        system = str(skill.get("system_prompt") or
                     f"You are the '{skill.get('name', 'specialist')}' capability. "
                     "Complete the user's goal concretely and concisely.")
        steps = skill.get("execution_steps")
        if isinstance(steps, list) and steps:
            system += "\n\nFollow these steps:\n" + "\n".join(f"- {s}" for s in steps[:8])
        try:
            from engine.api import generate
        except Exception as exc:  # noqa: BLE001
            return {"status": "unavailable", "note": f"LLM engine not importable: {exc}"}
        try:
            context = ctx.get("context")
            text = (generate(prompt=goal, system=system,
                             context=context if isinstance(context, str) else None) or "").strip()
            if not text:
                return {"status": "error", "skill_id": skill.get("id"),
                        "error": "skill produced no output"}
            return {"status": "ok", "skill_id": skill.get("id"), "via": "skill_library_llm",
                    "skill_name": skill.get("name"), "output": text,
                    "match_score": skill.get("match_score")}
        except Exception as exc:  # noqa: BLE001
            return {"status": "error", "skill_id": skill.get("id"), "error": str(exc)}

    # ── Default skills ────────────────────────────────────────────────────────

    def _register_exec_defaults(self) -> None:
        self.register_skill("market_research", "1.0", self._market_research,
                            ["web_search", "llm_infer"],
                            "Research a market or topic", 0)
        self.register_skill("content_creation", "1.0", self._content_creation,
                            ["llm_infer", "write_file"],
                            "Create written content", 1)
        self.register_skill("document_intelligence", "1.0", self._doc_intelligence,
                            ["read_file", "llm_infer", "embed_text"],
                            "Analyze documents", 0)
        self.register_skill("lead_generation", "1.0", self._lead_gen,
                            ["web_search", "call_api"],
                            "Find potential leads", 2)
        self.register_skill("customer_support", "1.0", self._support,
                            ["llm_infer", "get_memory"],
                            "Handle customer queries", 1)

    def _market_research(self, topic: str, **_):
        from tools.registry import get_tool_registry
        r = get_tool_registry()
        search_result = r.execute("web_search", {"query": topic, "limit": 5})
        llm_result = r.execute("llm_infer", {
            "prompt": f"Summarize market research for: {topic}", "max_tokens": 500,
        })
        return {"topic": topic, "sources": search_result, "summary": llm_result}

    def _content_creation(self, topic: str, format: str = "article", **_):
        from tools.registry import get_tool_registry
        return get_tool_registry().execute(
            "llm_infer",
            {"prompt": f"Write a {format} about: {topic}", "max_tokens": 1000},
        )

    def _doc_intelligence(self, path: str, query: str = "", **_):
        from tools.registry import get_tool_registry
        r = get_tool_registry()
        doc = r.execute("read_file", {"path": path})
        return r.execute("llm_infer", {
            "prompt": f"Analyze this document: {doc}\n\nQuery: {query}",
            "max_tokens": 800,
        })

    def _lead_gen(self, criteria: str, **_):
        return {"stub": True,
                "blocked": "Lead generation requires HITL approval",
                "criteria": criteria}

    def _support(self, query: str, **_):
        from tools.registry import get_tool_registry
        return get_tool_registry().execute(
            "llm_infer",
            {"prompt": f"Help customer with: {query}", "max_tokens": 500},
        )
