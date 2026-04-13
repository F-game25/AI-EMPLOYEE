from __future__ import annotations

from agents.base import BaseAgent
from agents.content_master import ContentMasterAgent
from agents.data_analyst import DataAnalystAgent
from agents.email_ninja import EmailNinjaAgent
from agents.intel_agent import IntelAgent
from agents.lead_hunter import LeadHunterAgent
from agents.social_guru import SocialGuruAgent
from agents.support_bot import SupportBotAgent


class TaskOrchestratorAgent(BaseAgent):
    agent_id = "task_orchestrator"
    required_fields = ("task",)

    def execute(self, payload: dict) -> dict:
        plan_prompt = (
            "Break task into substeps and output JSON with key 'steps' as list of agent ids from: "
            "lead_hunter,content_master,social_guru,intel_agent,email_ninja,support_bot,data_analyst. "
            f"Task: {payload['task']}"
        )
        plan, plan_tokens = self._ask_json(prompt=plan_prompt, system="You orchestrate specialist agents.")
        steps = plan.get("steps") if isinstance(plan, dict) else None
        if not isinstance(steps, list) or not steps:
            steps = ["intel_agent", "content_master"]

        registry = {
            "lead_hunter": LeadHunterAgent(self.client),
            "content_master": ContentMasterAgent(self.client),
            "social_guru": SocialGuruAgent(self.client),
            "intel_agent": IntelAgent(self.client),
            "email_ninja": EmailNinjaAgent(self.client),
            "support_bot": SupportBotAgent(self.client),
            "data_analyst": DataAnalystAgent(self.client),
        }

        outputs = []
        total_tokens = plan_tokens
        for step in steps:
            agent = registry.get(str(step))
            if not agent:
                continue
            result = agent.run({"task": payload["task"]})
            total_tokens += int(result.get("tokens_used", 0))
            outputs.append({"agent": agent.agent_id, "result": result})

        return {"steps": steps, "results": outputs, "tokens_used": total_tokens}
