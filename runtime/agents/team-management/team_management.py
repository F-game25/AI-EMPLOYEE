"""Team Management Agent — team roster, task assignment, workload tracking.

Manages team members, assigns tasks, tracks capacity, and generates
standup reports and workload balance summaries.

Commands (via chat):
  team roster          — list all team members and roles
  team assign <task>   — assign a task to best-fit team member
  team workload        — show workload per person
  team standup         — generate today's standup report
  team status          — team capacity and bottleneck analysis
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from agents.base import BaseAgent

AI_HOME = Path(os.environ.get("AI_HOME", str(Path.home() / ".ai-employee")))
ROSTER_FILE = AI_HOME / "state" / "team-roster.json"
TASKS_FILE = AI_HOME / "state" / "team-tasks.json"

SYSTEM = """You are a Team Management Expert and agile coach. Analyze team data and generate actionable outputs.

Output JSON with this structure:
{
  "summary": "One-sentence team status",
  "roster_analysis": [{"name": "...", "role": "...", "capacity_percent": 0, "current_tasks": 0, "status": "available|busy|blocked"}],
  "recommendations": [{"action": "...", "assignee": "...", "priority": "high|medium|low", "reason": "..."}],
  "blockers": [{"person": "...", "blocker": "...", "resolution": "..."}],
  "standup_report": "Formatted daily standup text ready to paste into Slack/Teams",
  "capacity_alert": "Warning if team is over/under capacity",
  "next_actions": ["action 1", "action 2"]
}"""


class TeamManagementAgent(BaseAgent):
    agent_id = "team-management"
    required_fields = ("task",)

    def execute(self, payload: dict) -> dict:
        roster = self._load_roster()
        tasks = self._load_tasks()
        request = payload.get("task", "standup")
        new_member = payload.get("member")
        new_task = payload.get("assign_task")

        if new_member:
            self._add_member(new_member)
            roster = self._load_roster()

        if new_task:
            self._add_task(new_task)
            tasks = self._load_tasks()

        prompt = (
            f"Request: {request}\n"
            f"Team roster ({len(roster)} members): {json.dumps(roster, indent=2)}\n"
            f"Active tasks ({len(tasks)} total): {json.dumps(tasks[:20], indent=2)}"
        )
        data, tokens = self._ask_json(prompt=prompt, system=SYSTEM)
        data["tokens_used"] = tokens
        return data

    def _load_roster(self) -> list:
        if not ROSTER_FILE.exists():
            return []
        try:
            return json.loads(ROSTER_FILE.read_text())
        except Exception:
            return []

    def _load_tasks(self) -> list:
        if not TASKS_FILE.exists():
            return []
        try:
            return json.loads(TASKS_FILE.read_text())
        except Exception:
            return []

    def _add_member(self, member: dict | str) -> None:
        roster = self._load_roster()
        if isinstance(member, str):
            member = {"name": member, "role": "team member", "capacity": 100}
        member.setdefault("added_at", datetime.now(timezone.utc).isoformat())
        roster.append(member)
        ROSTER_FILE.parent.mkdir(parents=True, exist_ok=True)
        ROSTER_FILE.write_text(json.dumps(roster, indent=2))

    def _add_task(self, task: dict | str) -> None:
        tasks = self._load_tasks()
        if isinstance(task, str):
            task = {"title": task, "status": "open", "priority": "medium"}
        task.setdefault("created_at", datetime.now(timezone.utc).isoformat())
        tasks.append(task)
        TASKS_FILE.parent.mkdir(parents=True, exist_ok=True)
        TASKS_FILE.write_text(json.dumps(tasks, indent=2))
