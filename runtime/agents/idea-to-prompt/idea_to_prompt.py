"""Idea-to-Prompt Converter — transforms rough ideas into structured AI prompts.

This module sits between the user's raw input and the main orchestrator.
It accepts a vague idea or concept and uses an LLM to produce an efficient,
professional, and actionable task description that the orchestrator can execute.

Usage (standalone):
    from idea_to_prompt import convert_idea
    result = convert_idea("I want to sell t-shirts online")
    print(result["prompt"])   # structured task prompt
    print(result["title"])    # short title

Usage (via API):
    POST /api/idea/convert  {"idea": "I want to sell t-shirts online"}
    → {"ok": true, "prompt": "...", "title": "...", "original": "..."}
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

# ── AI Router integration ─────────────────────────────────────────────────────
_AGENTS_DIR = Path(__file__).parent.parent
if str(_AGENTS_DIR / "ai-router") not in sys.path:
    sys.path.insert(0, str(_AGENTS_DIR / "ai-router"))

try:
    from ai_router import query_ai_for_agent as _query_ai  # type: ignore
    _AI_AVAILABLE = True
except ImportError:
    _AI_AVAILABLE = False

# ── System prompt for the converter ──────────────────────────────────────────
_SYSTEM_PROMPT = """You are an expert AI prompt engineer and project manager.
Your job is to transform rough ideas into clear, structured, professional task
descriptions that an AI orchestrator can execute effectively.

Rules:
1. Identify the core goal and expand it into concrete sub-tasks.
2. Add specific success criteria and expected deliverables.
3. Specify desired output format (report, code, plan, etc.) where relevant.
4. Keep the description focused and actionable — no fluff.
5. Use bullet points or numbered steps where helpful.
6. Output ONLY the structured task description followed by a newline and then
   a short title prefixed with "TITLE: ".
   Do NOT include any preamble, explanation, or meta-commentary.

Example input:  "I want to grow my YouTube channel"
Example output:
Develop a comprehensive YouTube channel growth strategy:
1. Analyse the current channel: subscribers, top-performing videos, retention rate, and audience demographics.
2. Identify the top 10 content gaps and trending topics in the channel's niche using YouTube search data.
3. Create a 4-week content calendar with video titles, descriptions, and thumbnail concepts.
4. Write SEO-optimised descriptions and tag sets for the next 5 videos.
5. Draft a community engagement plan: comment response templates, community post ideas, and collaboration outreach.
6. Produce a concise growth report (PDF-ready) with metrics targets for 30/60/90 days.

TITLE: YouTube Channel Growth Strategy
"""

# ── Fallback template-based expansion (when AI is unavailable) ───────────────
_FALLBACK_EXPANSIONS: list[tuple[list[str], str]] = [
    (
        ["sell", "shop", "store", "ecommerce", "e-commerce", "product"],
        (
            "Launch an e-commerce operation:\n"
            "1. Define the product catalogue, pricing strategy, and target audience.\n"
            "2. Set up an online store (platform, domain, payment gateway).\n"
            "3. Create product listings with SEO-optimised titles and descriptions.\n"
            "4. Develop a marketing plan: social media, paid ads, and email campaigns.\n"
            "5. Outline fulfilment workflow and customer support process.\n"
            "6. Produce a 90-day revenue forecast.\n"
        ),
    ),
    (
        ["app", "software", "saas", "platform", "website", "build", "develop", "create"],
        (
            "Design and launch a software product:\n"
            "1. Define user personas and core problem being solved.\n"
            "2. Document functional requirements and MVP feature set.\n"
            "3. Create wireframes or a UX flow diagram.\n"
            "4. Outline technology stack and architecture.\n"
            "5. Draft a development roadmap with milestones.\n"
            "6. Plan the go-to-market strategy and pricing model.\n"
        ),
    ),
    (
        ["market", "grow", "audience", "brand", "social", "content"],
        (
            "Execute a digital marketing and brand-growth campaign:\n"
            "1. Audit current brand presence across all channels.\n"
            "2. Identify target audience segments and key messages.\n"
            "3. Create a 30-day content calendar for social media.\n"
            "4. Design 3 email nurture sequences for leads.\n"
            "5. Propose paid advertising budget allocation.\n"
            "6. Define KPIs and a weekly reporting template.\n"
        ),
    ),
    (
        ["company", "startup", "business", "launch"],
        (
            "Build and launch a new business:\n"
            "1. Develop a one-page business model canvas.\n"
            "2. Conduct market research and competitive analysis.\n"
            "3. Create a full business plan with financial projections.\n"
            "4. Design brand identity (name, logo, colours, tone-of-voice).\n"
            "5. Build a go-to-market strategy for the first 90 days.\n"
            "6. Identify legal requirements and operational setup steps.\n"
        ),
    ),
]

_FALLBACK_DEFAULT = (
    "Execute the following goal with a structured, multi-step approach:\n"
    "1. Research and analyse the current state of the topic.\n"
    "2. Identify the key actions needed to achieve the goal.\n"
    "3. Create a detailed action plan with clear milestones.\n"
    "4. Execute each step and document the outcomes.\n"
    "5. Review results against success criteria and iterate.\n"
)


def _fallback_expand(idea: str) -> tuple[str, str]:
    """Template-based fallback when AI is not available."""
    idea_lower = idea.lower()
    for keywords, template in _FALLBACK_EXPANSIONS:
        if any(kw in idea_lower for kw in keywords):
            prompt_body = f"Goal: {idea}\n\n" + template
            title = idea[:60].strip()
            return prompt_body, title
    prompt_body = f"Goal: {idea}\n\n" + _FALLBACK_DEFAULT
    title = idea[:60].strip()
    return prompt_body, title


def convert_idea(idea: str) -> dict:
    """Convert a rough idea into a structured, professional task prompt.

    Args:
        idea: The raw user idea (can be vague, 1 sentence or a paragraph).

    Returns:
        dict with keys:
            ok       — bool, True on success
            prompt   — the structured task description (str)
            title    — short title extracted from the prompt (str)
            original — the original idea text (str)
            provider — which AI provider was used (str, or "fallback")
            error    — error message if ok is False (str)
    """
    idea = idea.strip()
    if not idea:
        return {"ok": False, "error": "idea is empty", "prompt": "", "title": "", "original": idea, "provider": "none"}

    if _AI_AVAILABLE:
        try:
            result = _query_ai(
                "reasoning",
                f"Convert this idea into a structured AI task:\n\n{idea}",
                system_prompt=_SYSTEM_PROMPT,
            )
            raw = (result.get("content") or result.get("answer") or result.get("text") or "").strip()
            if raw:
                prompt_text, title = _parse_ai_response(raw, idea)
                return {
                    "ok": True,
                    "prompt": prompt_text,
                    "title": title,
                    "original": idea,
                    "provider": result.get("provider", "ai"),
                }
        except Exception as exc:
            logger.warning("idea_to_prompt: AI call failed, using fallback: %s", exc)

    # Fallback when AI is unavailable or failed
    prompt_text, title = _fallback_expand(idea)
    return {
        "ok": True,
        "prompt": prompt_text,
        "title": title,
        "original": idea,
        "provider": "fallback",
    }


def _parse_ai_response(raw: str, idea: str) -> tuple[str, str]:
    """Extract the prompt body and title from the AI's response."""
    title = idea[:60].strip()
    prompt_lines = []
    for line in raw.splitlines():
        stripped = line.strip()
        if stripped.upper().startswith("TITLE:"):
            candidate = stripped[6:].strip()
            if candidate:
                title = candidate
        else:
            prompt_lines.append(line)
    prompt_text = "\n".join(prompt_lines).strip()
    return prompt_text, title
