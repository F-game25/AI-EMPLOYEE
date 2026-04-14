"""Research ingestion agent for explicit learn-topic commands."""
from __future__ import annotations

import re
from typing import Any

from core.knowledge_store import get_knowledge_store
from core.learning_engine import get_learning_engine
from core.memory_index import get_memory_index


class ResearchAgent:
    _TRIGGER_PATTERNS = (
        r"\blearn about\b",
        r"\blearn how to run\b",
        r"\bresearch online product sales\b",
        r"\bresearch\b",
    )
    _FASHION_RULE = {
        "insight": "{root}: fashion brands rely heavily on Instagram + influencers for discovery.",
        "strategy": "{root}: prioritize Instagram creative testing and influencer seeding before broad paid expansion.",
    }
    _TOPIC_INSIGHT_RULES = {
        "fashion": _FASHION_RULE,
        "clothing": _FASHION_RULE,
        "apparel": _FASHION_RULE,
    }

    def is_learn_command(self, text: str) -> bool:
        lower = (text or "").strip().lower()
        return any(re.search(pattern, lower) for pattern in self._TRIGGER_PATTERNS)

    def extract_topic(self, text: str) -> str:
        lower = (text or "").strip().lower()
        if "learn about" in lower:
            return lower.split("learn about", 1)[1].strip() or "general_business"
        if "research online product sales" in lower:
            return "online_product_sales"
        if "learn how to run a business" in lower:
            return "business_operations"
        if "learn how to run " in lower:
            return lower.split("learn how to run ", 1)[1].strip() or "business_operations"
        if "research " in lower:
            return lower.split("research ", 1)[1].strip() or "general_research"
        return lower or "general_research"

    def _subtopics(self, topic: str) -> list[str]:
        root = topic.replace("_", " ").strip()
        return [
            "marketing",
            "supply chain",
            "ads",
            "branding",
            "pricing",
            "funnels",
            f"{root} fundamentals",
            f"{root} operations",
        ]

    def _structured_knowledge(self, topic: str) -> dict[str, Any]:
        subs = self._subtopics(topic)
        root = topic.replace("_", " ").strip()
        by_subtopic = [self._research_subtopic(root=root, subtopic=sub) for sub in subs]
        insights: list[str] = []
        strategies: list[str] = []
        mistakes: list[str] = []
        playbooks: list[str] = []
        for row in by_subtopic:
            insights.extend(row.get("insights", []))
            strategies.extend(row.get("strategies", []))
            mistakes.extend(row.get("mistakes_to_avoid", []))
            playbooks.extend(row.get("actionable_playbooks", []))
        lowered = root.lower()
        for token, rule in self._TOPIC_INSIGHT_RULES.items():
            if re.search(rf"\b{re.escape(token)}\b", lowered):
                insights.append(str(rule["insight"]).format(root=root))
                strategies.append(str(rule["strategy"]).format(root=root))
        insights = list(dict.fromkeys(insights))
        strategies = list(dict.fromkeys(strategies))
        mistakes = list(dict.fromkeys(mistakes))
        playbooks = list(dict.fromkeys(playbooks))
        return {
            "topic": topic,
            "insights": insights,
            "strategies": strategies,
            "mistakes_to_avoid": mistakes,
            "actionable_playbooks": playbooks,
            "subtopics": subs,
            "research_tasks": by_subtopic,
        }

    @staticmethod
    def _research_subtopic(*, root: str, subtopic: str) -> dict[str, Any]:
        sub = subtopic.lower()
        return {
            "subtopic": subtopic,
            "insights": [
                f"{root}: {subtopic} decisions should be measured against contribution margin and payback period.",
                f"{root}: {subtopic} should be tuned through weekly experiment loops with clear success criteria.",
            ],
            "strategies": [
                f"{root}: create a repeatable {subtopic} operating cadence with KPI checkpoints.",
                f"{root}: connect {subtopic} execution to segment-level funnel performance.",
            ],
            "mistakes_to_avoid": [
                f"{subtopic}: scaling without validated unit economics.",
                f"{subtopic}: making channel changes without attribution tracking.",
            ],
            "actionable_playbooks": [
                f"{subtopic} playbook: hypothesis → test design → launch → weekly retrospective.",
            ],
            "source": "synthetic_research_loop",
        }

    def learn_topic(self, prompt: str) -> dict[str, Any]:
        topic = self.extract_topic(prompt)
        payload = self._structured_knowledge(topic)
        get_knowledge_store().add_knowledge(topic, payload)
        get_knowledge_store().add_knowledge("research_strategies", {"topic": topic, "strategies": payload.get("strategies", [])})
        for subtask in payload.get("research_tasks", []):
            tag = str(subtask.get("subtopic", "research")).strip().lower().replace(" ", "_")
            get_knowledge_store().add_knowledge(f"research:{tag}", {"topic": topic, **subtask})
        for item in payload.get("insights", [])[:5]:
            get_memory_index().add_memory(f"{topic}: {item}", importance=0.8)
        for item in payload.get("strategies", [])[:5]:
            get_memory_index().add_memory(f"{topic} strategy: {item}", importance=0.9)
        for item in payload.get("mistakes_to_avoid", [])[:3]:
            get_memory_index().add_memory(f"{topic} avoid: {item}", importance=0.75)
        for item in payload.get("actionable_playbooks", [])[:3]:
            get_memory_index().add_memory(f"{topic} playbook: {item}", importance=0.85)
        get_learning_engine().add_conversation_message(role="system", message=f"learned topic: {topic}")
        return payload


def is_learn_topic_intent(text: str) -> bool:
    return ResearchAgent().is_learn_command(text)


def extract_learn_topic(text: str) -> str:
    return ResearchAgent().extract_topic(text)
