"""Goal Alignment — Hierarchical Goal Ancestry for AI-EMPLOYEE.

Inspired by Paperclip's goal-alignment model, this module ensures every task
carries full goal ancestry so agents always know *what* to do and *why*.

Hierarchy:
  Company Mission
    └── Project Goals
          └── Task Context (injected into every AI prompt)

Config:  ~/.ai-employee/config/company_goals.json
State:   ~/.ai-employee/state/goal-alignment.state.json

API (via problem-solver-ui server.py):
  GET  /api/goals/company              — get company mission
  POST /api/goals/company              — set company mission
  GET  /api/goals/projects             — list all projects
  POST /api/goals/projects             — create/update a project
  DELETE /api/goals/projects/{id}      — remove a project
  GET  /api/goals/context/{project_id} — get full goal ancestry for a project
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger("goal-alignment")

AI_HOME = Path(os.environ.get("AI_HOME", str(Path.home() / ".ai-employee")))
GOALS_FILE = AI_HOME / "config" / "company_goals.json"
STATE_FILE = AI_HOME / "state" / "goal-alignment.state.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ── Persistence ───────────────────────────────────────────────────────────────


def _load_goals() -> dict:
    if GOALS_FILE.exists():
        try:
            return json.loads(GOALS_FILE.read_text())
        except Exception as exc:
            logger.warning("goals load error: %s", exc)
    return {"mission": "", "vision": "", "projects": [], "updated_at": _now_iso()}


def _save_goals(data: dict) -> None:
    GOALS_FILE.parent.mkdir(parents=True, exist_ok=True)
    data["updated_at"] = _now_iso()
    GOALS_FILE.write_text(json.dumps(data, indent=2))


# ── Company Mission ───────────────────────────────────────────────────────────


def get_company_mission() -> dict:
    """Return the company mission and vision."""
    data = _load_goals()
    return {
        "mission": data.get("mission", ""),
        "vision": data.get("vision", ""),
        "values": data.get("values", []),
        "updated_at": data.get("updated_at"),
    }


def set_company_mission(
    mission: str,
    vision: str = "",
    values: list[str] | None = None,
) -> dict:
    """Set the company mission and optional vision/values."""
    data = _load_goals()
    data["mission"] = mission.strip()
    data["vision"] = vision.strip()
    if values is not None:
        data["values"] = values
    _save_goals(data)
    return get_company_mission()


# ── Projects ──────────────────────────────────────────────────────────────────


def list_projects() -> list[dict]:
    data = _load_goals()
    return data.get("projects", [])


def upsert_project(
    project_id: str | None,
    name: str,
    goal: str,
    description: str = "",
    assigned_roles: list[str] | None = None,
    assigned_agents: list[str] | None = None,
    priority: str = "medium",  # low | medium | high | critical
    status: str = "active",    # active | paused | done
) -> dict:
    """Create or update a project under the company mission."""
    data = _load_goals()
    projects: list = data.get("projects", [])

    if not project_id:
        project_id = str(uuid.uuid4())[:8]

    existing = next((p for p in projects if p["project_id"] == project_id), None)
    project = {
        "project_id": project_id,
        "name": name,
        "goal": goal,
        "description": description,
        "assigned_roles": assigned_roles or [],
        "assigned_agents": assigned_agents or [],
        "priority": priority,
        "status": status,
        "created_at": existing.get("created_at", _now_iso()) if existing else _now_iso(),
        "updated_at": _now_iso(),
    }

    if existing:
        projects = [p if p["project_id"] != project_id else project for p in projects]
    else:
        projects.append(project)

    data["projects"] = projects
    _save_goals(data)
    return project


def delete_project(project_id: str) -> bool:
    data = _load_goals()
    projects = data.get("projects", [])
    original_len = len(projects)
    data["projects"] = [p for p in projects if p["project_id"] != project_id]
    _save_goals(data)
    return len(data["projects"]) < original_len


# ── Goal Ancestry / Context Injection ────────────────────────────────────────


def get_goal_context(
    project_id: str | None = None,
    agent_id: str | None = None,
) -> dict:
    """Return the full goal ancestry for injection into task prompts.

    Looks up the project by ID (or by agent assignment) and builds the chain:
      Company Mission → Project Goal → (task context placeholder)
    """
    data = _load_goals()
    mission = data.get("mission", "")
    vision = data.get("vision", "")
    projects = data.get("projects", [])

    project = None
    if project_id:
        project = next((p for p in projects if p["project_id"] == project_id), None)
    elif agent_id:
        # Find the most relevant project for this agent
        for p in projects:
            if agent_id in p.get("assigned_agents", []) and p.get("status") == "active":
                project = p
                break

    context = {"mission": mission, "vision": vision}
    if project:
        context["project"] = {
            "name": project["name"],
            "goal": project["goal"],
            "description": project["description"],
            "priority": project["priority"],
        }

    return context


def build_goal_preamble(
    project_id: str | None = None,
    agent_id: str | None = None,
) -> str:
    """Build a goal-context preamble string to prepend to any task prompt.

    This ensures every agent prompt carries full goal ancestry so the agent
    always knows *what* to do and *why* — exactly as Paperclip does.
    """
    ctx = get_goal_context(project_id=project_id, agent_id=agent_id)
    lines: list[str] = []

    if ctx.get("mission"):
        lines.append(f"Company Mission: {ctx['mission']}")
    if ctx.get("vision"):
        lines.append(f"Company Vision: {ctx['vision']}")
    if ctx.get("project"):
        p = ctx["project"]
        lines.append(f"Project: {p['name']} (priority: {p['priority']})")
        lines.append(f"Project Goal: {p['goal']}")
        if p.get("description"):
            lines.append(f"Project Context: {p['description']}")

    if not lines:
        return ""

    preamble = "\n".join(lines)
    return f"[GOAL CONTEXT]\n{preamble}\n[/GOAL CONTEXT]\n\n"
