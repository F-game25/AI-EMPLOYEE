"""RoadmapEngine — convert goals into executable milestone plans.

Flow:
  engine.create_roadmap(goal, tenant_id) -> Roadmap
  engine.generate_milestones(roadmap)    -> Roadmap  (LLM decomposes goal)
  engine.execute_roadmap(roadmap_id)     -> dict      (runs tasks via AgentController)
  engine.get_roadmap(roadmap_id)         -> Roadmap
  engine.list_roadmaps(tenant_id)        -> list[Roadmap]

State persists to state/roadmaps/{roadmap_id}.json
"""
from __future__ import annotations

import json
import logging
import os
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ── Data model ────────────────────────────────────────────────────────────────

@dataclass
class Task:
    id: str
    title: str
    agent_id: str
    skill: str = ""
    status: str = "pending"   # pending | running | done | failed
    result: dict = field(default_factory=dict)


@dataclass
class Milestone:
    id: str
    title: str
    deadline: str = ""        # ISO date string
    tasks: list = field(default_factory=list)
    status: str = "pending"   # pending | running | done | failed


@dataclass
class Roadmap:
    id: str
    goal: str
    tenant_id: str
    milestones: list = field(default_factory=list)
    created_at: str = ""
    status: str = "draft"     # draft | active | complete | failed


# ── Engine ────────────────────────────────────────────────────────────────────

class RoadmapEngine:
    """Converts goals into structured, executable milestone plans."""

    # ── State helpers ─────────────────────────────────────────────────────────

    @staticmethod
    def _state_dir() -> Path:
        base = os.environ.get("STATE_DIR") or os.environ.get("AI_EMPLOYEE_STATE_DIR")
        if not base:
            base = str(Path.home() / ".ai-employee" / "state")
        return Path(base) / "roadmaps"

    def _path(self, roadmap_id: str) -> Path:
        return self._state_dir() / f"{roadmap_id}.json"

    def _save(self, roadmap: Roadmap) -> None:
        d = self._state_dir()
        d.mkdir(parents=True, exist_ok=True)
        tmp = self._path(roadmap.id).with_suffix(".json.tmp")
        tmp.write_text(json.dumps(asdict(roadmap), indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.rename(self._path(roadmap.id))

    def _load_raw(self, roadmap_id: str) -> dict | None:
        p = self._path(roadmap_id)
        if not p.exists():
            return None
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.error("roadmap_engine: failed to load roadmap %s (%s)", roadmap_id, type(exc).__name__)
            return None

    @staticmethod
    def _dict_to_roadmap(d: dict) -> Roadmap:
        milestones = [
            Milestone(
                id=m["id"],
                title=m["title"],
                deadline=m.get("deadline", ""),
                status=m.get("status", "pending"),
                tasks=[Task(**t) for t in m.get("tasks", [])],
            )
            for m in d.get("milestones", [])
        ]
        return Roadmap(
            id=d["id"],
            goal=d["goal"],
            tenant_id=d["tenant_id"],
            milestones=milestones,
            created_at=d.get("created_at", ""),
            status=d.get("status", "draft"),
        )

    # ── LLM helper ────────────────────────────────────────────────────────────

    @staticmethod
    def _llm_generate(prompt: str, system: str) -> str | None:
        try:
            from engine.api import generate
            return generate(prompt=prompt, system=system, timeout=60)
        except Exception as exc:
            logger.warning("roadmap_engine: LLM unavailable — %s", exc)
            return None

    # ── Public API ────────────────────────────────────────────────────────────

    def create_roadmap(self, goal: str, tenant_id: str) -> Roadmap:
        """Create a new empty roadmap for a goal."""
        roadmap = Roadmap(
            id=str(uuid.uuid4())[:12],
            goal=goal.strip(),
            tenant_id=tenant_id,
            created_at=datetime.now(timezone.utc).isoformat(),
            status="draft",
        )
        self._save(roadmap)
        logger.info("roadmap_engine: created %s for tenant=%s goal='%s'", roadmap.id, tenant_id, goal[:60])
        return roadmap

    def generate_milestones(self, roadmap: Roadmap) -> Roadmap:
        """Use LLM to decompose goal into 3-5 milestones with tasks each."""
        system = (
            "You are a product manager and execution planner. "
            "Return ONLY valid JSON. No markdown, no explanation."
        )
        prompt = (
            f"Decompose this goal into 3-5 milestones with 2-3 tasks each:\n"
            f"Goal: {roadmap.goal}\n\n"
            "Return JSON:\n"
            '{"milestones": [{"title": str, "deadline": "YYYY-MM-DD", '
            '"tasks": [{"title": str, "agent_id": str, "skill": str}]}]}'
        )
        raw = self._llm_generate(prompt, system)
        parsed: dict[str, Any] = {}
        if raw:
            try:
                parsed = json.loads(raw)
            except Exception:
                # Try to extract JSON block if LLM wrapped in markdown
                import re
                m = re.search(r"\{.*\}", raw, re.DOTALL)
                if m:
                    try:
                        parsed = json.loads(m.group())
                    except Exception:
                        pass

        if parsed.get("milestones"):
            roadmap.milestones = [
                Milestone(
                    id=str(uuid.uuid4())[:8],
                    title=m.get("title", f"Milestone {i+1}"),
                    deadline=m.get("deadline", ""),
                    tasks=[
                        Task(
                            id=str(uuid.uuid4())[:8],
                            title=t.get("title", f"Task {j+1}"),
                            agent_id=t.get("agent_id", "agent-controller"),
                            skill=t.get("skill", ""),
                        )
                        for j, t in enumerate(m.get("tasks", []))
                    ],
                )
                for i, m in enumerate(parsed["milestones"][:5])
            ]
        else:
            # Graceful degradation: stub milestones
            roadmap.milestones = self._stub_milestones(roadmap.goal)

        roadmap.status = "active"
        self._save(roadmap)
        logger.info("roadmap_engine: generated %d milestones for %s", len(roadmap.milestones), roadmap.id)
        return roadmap

    @staticmethod
    def _stub_milestones(goal: str) -> list[Milestone]:
        """Return basic stub milestones when LLM is unavailable."""
        phases = ["Discovery & Research", "Planning & Design", "Execution", "Review & Launch"]
        return [
            Milestone(
                id=str(uuid.uuid4())[:8],
                title=phase,
                tasks=[
                    Task(
                        id=str(uuid.uuid4())[:8],
                        title=f"{phase}: {goal[:40]}",
                        agent_id="agent-controller",
                        skill="",
                    )
                ],
            )
            for phase in phases
        ]

    async def execute_roadmap(self, roadmap_id: str) -> dict:
        """Run all pending tasks in milestone order via AgentController."""
        raw = self._load_raw(roadmap_id)
        if not raw:
            return {"ok": False, "error": f"Roadmap {roadmap_id} not found"}

        roadmap = self._dict_to_roadmap(raw)
        roadmap.status = "active"

        results: list[dict] = []
        try:
            from core.agent_controller import AgentController
            controller = AgentController()
        except Exception as exc:
            logger.error("roadmap_engine: AgentController unavailable — %s", exc)
            controller = None

        for milestone in roadmap.milestones:
            if milestone.status == "done":
                continue
            milestone.status = "running"
            milestone_ok = True

            for task in milestone.tasks:
                if task.status == "done":
                    continue
                task.status = "running"
                self._save(roadmap)

                task_result: dict = {}
                try:
                    if controller:
                        goal_str = task.title + (f" (skill: {task.skill})" if task.skill else "")
                        task_result = await controller.run_goal(goal=goal_str, tenant_id=roadmap.tenant_id)
                        task.status = "done"
                    else:
                        task_result = {"status": "skipped", "reason": "AgentController unavailable"}
                        task.status = "failed"
                        milestone_ok = False
                except Exception as exc:
                    task_result = {"error": str(exc)}
                    task.status = "failed"
                    milestone_ok = False
                    logger.error("roadmap_engine: task %s failed — %s", task.id, exc)

                task.result = task_result
                results.append({"milestone": milestone.title, "task": task.title,
                                 "status": task.status, "result": task_result})
                self._save(roadmap)

            milestone.status = "done" if milestone_ok else "failed"

        roadmap.status = "complete" if all(m.status == "done" for m in roadmap.milestones) else "active"
        self._save(roadmap)
        return {"ok": True, "roadmap_id": roadmap_id, "status": roadmap.status, "tasks_run": results}

    def get_roadmap(self, roadmap_id: str) -> Roadmap | None:
        raw = self._load_raw(roadmap_id)
        return self._dict_to_roadmap(raw) if raw else None

    def list_roadmaps(self, tenant_id: str) -> list[Roadmap]:
        d = self._state_dir()
        if not d.exists():
            return []
        roadmaps: list[Roadmap] = []
        for p in sorted(d.glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                if data.get("tenant_id") == tenant_id:
                    roadmaps.append(self._dict_to_roadmap(data))
            except Exception:
                continue
        return roadmaps

    def roadmap_status(self, roadmap_id: str) -> dict:
        r = self.get_roadmap(roadmap_id)
        if not r:
            return {"ok": False, "error": "not found"}
        return {
            "ok": True,
            "id": r.id,
            "goal": r.goal,
            "status": r.status,
            "created_at": r.created_at,
            "milestones": [
                {
                    "id": m.id,
                    "title": m.title,
                    "deadline": m.deadline,
                    "status": m.status,
                    "tasks": [{"id": t.id, "title": t.title, "status": t.status} for t in m.tasks],
                }
                for m in r.milestones
            ],
        }


# ── Singleton ──────────────────────────────────────────────────────────────────

_instance: RoadmapEngine | None = None
_instance_lock = __import__("threading").Lock()


def get_roadmap_engine() -> RoadmapEngine:
    global _instance
    with _instance_lock:
        if _instance is None:
            _instance = RoadmapEngine()
    return _instance
