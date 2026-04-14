"""Research ingestion agent for explicit learn-topic commands."""
from __future__ import annotations

import re
from typing import Any

from core.knowledge_store import get_knowledge_store


class ResearchAgent:
    _TRIGGER_PATTERNS = (
        r"\blearn about\b",
        r"\blearn how to run a business\b",
        r"\bresearch online product sales\b",
        r"\bresearch\b",
    )

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
        if "research " in lower:
            return lower.split("research ", 1)[1].strip() or "general_research"
        return lower or "general_research"

    def _subtopics(self, topic: str) -> list[str]:
        root = topic.replace("_", " ").strip()
        return [
            f"{root} fundamentals",
            f"{root} growth channels",
            f"{root} economics and operations",
            f"{root} execution playbooks",
        ]

    def _structured_knowledge(self, topic: str) -> dict[str, Any]:
        subs = self._subtopics(topic)
        return {
            "topic": topic,
            "subtopics": subs,
            "key_points": [
                f"Prioritize clear customer problem definition for {topic}.",
                f"Track unit economics and retention to validate {topic} performance.",
                f"Run fast experiments, then scale proven {topic} channels.",
            ],
            "strategies": [
                f"Create a weekly execution loop for {topic} planning, testing, and review.",
                f"Build a repeatable acquisition-conversion-retention funnel for {topic}.",
                f"Use KPI dashboards to decide which {topic} initiatives to expand or stop.",
            ],
            "mistakes": [
                "Scaling channels before validating conversion assumptions.",
                "Ignoring customer feedback and churn patterns.",
                "Optimizing vanity metrics instead of revenue and retention.",
            ],
            "principles": [
                "Customer-first problem solving.",
                "Iterative experimentation with measurable outcomes.",
                "Operational discipline and feedback loops.",
            ],
            "examples": [
                f"Pilot one offer for {topic}, validate demand, then expand segments.",
                "Use post-mortems on failed tests to improve future decisions.",
            ],
        }

    def learn_topic(self, prompt: str) -> dict[str, Any]:
        topic = self.extract_topic(prompt)
        payload = self._structured_knowledge(topic)
        get_knowledge_store().add_knowledge(topic, payload)
        return payload


def is_learn_topic_intent(text: str) -> bool:
    return ResearchAgent().is_learn_command(text)


def extract_learn_topic(text: str) -> str:
    return ResearchAgent().extract_topic(text)
