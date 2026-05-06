"""Classify user intent to route to appropriate reasoning depth."""
import re
from typing import Literal

Intent = Literal["short", "deep", "multimodal", "agent", "embed_only"]


def classify_intent(text: str) -> Intent:
    """Route user input to a reasoning strategy.

    - short: simple questions answerable from memory/rules
    - deep: research, planning, analysis (multi-step reasoning)
    - multimodal: image/doc analysis
    - agent: skill invocation
    - embed_only: embedding/storage only, no reasoning needed
    """
    text_lower = text.lower().strip()

    # Detect multimodal
    if any(w in text_lower for w in ["image", "screenshot", "upload", "photo", "picture", "pdf", "document"]):
        return "multimodal"

    # Detect agent/skill invocation
    agent_keywords = ["run", "execute", "call", "invoke", "perform", "do", "send", "create", "write", "schedule"]
    if any(re.search(rf"(^|\W){kw}\s+", text_lower) for kw in agent_keywords):
        return "agent"

    # Detect deep reasoning
    deep_keywords = [
        "plan", "analyze", "research", "investigate", "compare", "strategy",
        "design", "evaluate", "recommend", "solve", "debug", "how would you",
        "what if", "brainstorm", "explore", "3 steps", "multiple steps"
    ]
    if any(kw in text_lower for kw in deep_keywords):
        return "deep"

    # Detect memory/store only
    store_keywords = ["remember", "save", "store", "note", "remind me"]
    if any(re.search(rf"(^|\W){kw}", text_lower) for kw in store_keywords):
        return "embed_only"

    # Default to short Q&A
    return "short"
