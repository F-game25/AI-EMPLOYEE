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
        insights = [
            f"{root}: validate product-market fit before scaling paid acquisition.",
            f"{root}: combine organic channels and paid ads to reduce CAC volatility.",
            f"{root}: maintain contribution margin and repeat purchase tracking weekly.",
            f"{root}: use creator/influencer partnerships where audience trust is high.",
        ]
        strategies = [
            f"Build one repeatable {root} funnel per audience segment.",
            f"Run weekly test loops on offer, pricing, creative, and retention flows for {root}.",
            f"Prioritize channels with positive payback period for {root} growth.",
        ]
        mistakes = [
            "Scaling ad spend before conversion and retention are stable.",
            "Ignoring supply-chain reliability and stockout risk during growth.",
            "Using unclear positioning that weakens brand recall and conversion.",
        ]
        playbooks = [
            "90-day launch playbook: audience research → offer test → channel test → retention optimization.",
            "Channel playbook: organic content calendar + paid ad testing matrix + weekly KPI review.",
            "Pricing playbook: test entry offer, bundle upsell, and lifecycle email sequences.",
        ]
        return {
            "topic": topic,
            "insights": insights,
            "strategies": strategies,
            "mistakes_to_avoid": mistakes,
            "actionable_playbooks": playbooks,
            "subtopics": subs,
        }

    def learn_topic(self, prompt: str) -> dict[str, Any]:
        topic = self.extract_topic(prompt)
        payload = self._structured_knowledge(topic)
        get_knowledge_store().add_knowledge(topic, payload)
        get_knowledge_store().add_knowledge("research_strategies", {"topic": topic, "strategies": payload.get("strategies", [])})
        for item in payload.get("insights", [])[:5]:
            get_memory_index().add_memory(f"{topic}: {item}", importance=0.8)
        for item in payload.get("strategies", [])[:5]:
            get_memory_index().add_memory(f"{topic} strategy: {item}", importance=0.9)
        get_learning_engine().add_conversation_message(role="system", message=f"learned topic: {topic}")
        return payload


def is_learn_topic_intent(text: str) -> bool:
    return ResearchAgent().is_learn_command(text)


def extract_learn_topic(text: str) -> str:
    return ResearchAgent().extract_topic(text)
