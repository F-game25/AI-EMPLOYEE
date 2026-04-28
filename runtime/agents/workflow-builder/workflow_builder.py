"""Workflow Builder Agent — automation workflow design.

Designs trigger→condition→action automation workflows, saves them as
reusable JSON recipes, and documents integration requirements.

Commands (via chat):
  workflow create   <description>  — design a new automation workflow
  workflow list                    — list saved workflow recipes
  workflow template <type>         — get a pre-built workflow template
  workflow run      <id>           — execute a saved workflow (simulated)
  workflow status                  — active/inactive workflow summary
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from agents.base import BaseAgent

AI_HOME = Path(os.environ.get("AI_HOME", str(Path.home() / ".ai-employee")))
WORKFLOWS_FILE = AI_HOME / "state" / "workflows.json"

SYSTEM = """You are an Automation Architect who designs clean, reliable workflow automations.

Output JSON with this structure:
{
  "workflow_name": "descriptive name",
  "description": "What this workflow does in one sentence",
  "trigger": {
    "type": "webhook|cron|event|manual|email|form",
    "config": {"schedule": "0 9 * * 1-5", "event": "...", "url": "..."},
    "description": "What fires this workflow"
  },
  "conditions": [{"field": "...", "operator": "equals|contains|greater_than|exists", "value": "..."}],
  "actions": [
    {
      "step": 1,
      "type": "api_call|email|slack|database|transform|branch|delay",
      "name": "descriptive step name",
      "config": {},
      "on_error": "retry|skip|stop|alert"
    }
  ],
  "integrations_required": ["service1", "service2"],
  "estimated_runtime": "< 5 seconds",
  "use_cases": ["example use case 1", "example use case 2"],
  "setup_steps": ["Step 1: ...", "Step 2: ..."]
}"""


class WorkflowBuilderAgent(BaseAgent):
    agent_id = "workflow-builder"
    required_fields = ("task",)

    def execute(self, payload: dict) -> dict:
        description = payload.get("description") or payload.get("task", "")
        trigger_type = payload.get("trigger", "")
        integrations = payload.get("integrations", [])
        template_type = payload.get("template", "")

        if template_type:
            description = f"Create a {template_type} automation workflow template"

        prompt = (
            f"Design an automation workflow.\n"
            f"Description: {description}\n"
            f"Preferred trigger type: {trigger_type or 'auto-detect'}\n"
            f"Available integrations: {', '.join(integrations) if integrations else 'any'}"
        )
        data, tokens = self._ask_json(prompt=prompt, system=SYSTEM)

        if isinstance(data, dict):
            workflow = {
                "id": str(uuid.uuid4())[:8],
                "name": data.get("workflow_name", description[:50]),
                "status": "inactive",
                "created_at": datetime.now(timezone.utc).isoformat(),
                **data,
            }
            self._save_workflow(workflow)
            data["workflow_id"] = workflow["id"]

        data["tokens_used"] = tokens
        return data

    def _save_workflow(self, workflow: dict) -> None:
        workflows = []
        if WORKFLOWS_FILE.exists():
            try:
                workflows = json.loads(WORKFLOWS_FILE.read_text())
            except Exception:
                pass
        workflows.append(workflow)
        WORKFLOWS_FILE.parent.mkdir(parents=True, exist_ok=True)
        WORKFLOWS_FILE.write_text(json.dumps(workflows, indent=2))
