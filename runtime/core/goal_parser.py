"""Goal parser — converts natural language into a structured execution plan.

Output schema:
  {
    "is_goal": bool,           # true = actionable goal; false = question/chat
    "goal_type": str,          # "lead_generation" | "content_creation" | "research" | ...
    "structured_goal": {
      "action": str,
      "target": str,
      "quantity": int | null,
      "constraints": [str]
    },
    "task_plan": [
      {"id": int, "action": str, "params": dict, "description": str}
    ]
  }
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You are a goal-parsing engine for an AI automation system.
Your ONLY job is to convert user input into a structured JSON execution plan.

Available tools:
- web_search(query, max_results) — search the web
- fetch_page(url) — fetch web page content
- llm_extract(text, schema) — extract structured data from text
- llm_generate(prompt, context) — generate content (emails, posts, reports)
- save_leads(leads) — save leads to CRM
- read_leads(limit) — read leads from CRM
- save_file(filename, content) — save content to file
- send_email(to, subject, body) — send email (fails if not configured)
- apollo_search(icp, limit) — Apollo.io lead search (requires APOLLO_API_KEY)
- linkedin_post(content) — post to LinkedIn (requires LINKEDIN_ACCESS_TOKEN + LINKEDIN_PERSON_URN)
- website_builder(purpose, style, filename) — generate a complete HTML website and save to workspace

IMPORTANT RULES:
1. If the input is a question or greeting ("what can you do", "hello", "how are you"), set is_goal=false
2. If the input is an actionable goal ("find leads", "write a post", "research X"), set is_goal=true
3. task_plan steps must use ONLY the tools listed above
4. Each step must have: id (int), action (tool name), params (dict), description (str)
5. Reference previous step output using the string "$step_N" where N is the step id

Return ONLY valid JSON, no markdown, no explanation."""

_GOAL_TASK_TEMPLATES: dict[str, list[dict]] = {
    "lead_generation": [
        # continue_on_error=True: if search is rate-limited, still report clearly
        {"id": 1, "action": "web_search", "params": {"query": "{target} business contact email", "max_results": 10}, "description": "Search for {target} businesses", "continue_on_error": False},
        {"id": 2, "action": "llm_extract", "params": {"text": "$step_1", "schema": {"leads": [{"name": "str", "company": "str", "email": "str (if found)", "website": "str (if found)"}]}}, "description": "Extract lead data from search results"},
        {"id": 3, "action": "save_leads", "params": {"leads": "$step_2"}, "description": "Save leads to CRM"},
    ],
    "content_creation": [
        # Search is optional for content — LLM can generate without web context
        {"id": 1, "action": "web_search", "params": {"query": "latest trends {topic}", "max_results": 5}, "description": "Research topic trends", "continue_on_error": True},
        {"id": 2, "action": "llm_generate", "params": {"prompt": "Write a high-quality {content_type} about: {topic}. Be specific, engaging, and actionable.", "context": "$step_1"}, "description": "Generate content"},
        {"id": 3, "action": "save_file", "params": {"filename": "{topic}_content.md", "content": "$step_2"}, "description": "Save content to file"},
    ],
    "research": [
        {"id": 1, "action": "web_search", "params": {"query": "{topic}", "max_results": 8}, "description": "Search for {topic}", "continue_on_error": True},
        {"id": 2, "action": "llm_extract", "params": {"text": "$step_1", "schema": {"key_findings": ["str"], "summary": "str", "sources": ["str"]}}, "description": "Extract key findings"},
        {"id": 3, "action": "save_file", "params": {"filename": "{topic}_research.md", "content": "$step_2"}, "description": "Save research report"},
    ],
    "email_campaign": [
        {"id": 1, "action": "read_leads", "params": {"limit": 10}, "description": "Read leads from CRM"},
        {"id": 2, "action": "llm_generate", "params": {"prompt": "Write a compelling cold outreach email for: {goal}. Context: {target}. Be direct, personal, and value-focused.", "context": "$step_1"}, "description": "Generate email copy"},
        {"id": 3, "action": "save_file", "params": {"filename": "email_draft.md", "content": "$step_2"}, "description": "Save email draft"},
    ],
    "website_builder": [
        {"id": 1, "action": "website_builder", "params": {"purpose": "{target}", "style": "modern, professional", "filename": "index.html"}, "description": "Generate website HTML"},
    ],
}


def parse_goal(user_input: str) -> dict[str, Any]:
    """Parse user input into a structured execution plan.

    Returns the structured plan dict. If LLM is unavailable, falls back to
    keyword-based template matching.
    """
    from core.tool_llm_caller import call_llm_for_tool

    prompt = (
        f"{_SYSTEM_PROMPT}\n\n"
        f"User input: \"{user_input}\"\n\n"
        f"Return JSON:"
    )
    raw = call_llm_for_tool(prompt)
    if raw:
        plan = _extract_json(raw)
        if plan and _is_valid_plan(plan):
            logger.info("goal_parser: LLM plan parsed (is_goal=%s, steps=%d)",
                       plan.get("is_goal"), len(plan.get("task_plan", [])))
            return plan

    # Fallback: keyword-based classification + template
    return _keyword_fallback(user_input)


def _extract_json(text: str) -> dict | None:
    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


def _is_valid_plan(plan: dict) -> bool:
    return (
        isinstance(plan, dict) and
        "is_goal" in plan and
        isinstance(plan.get("task_plan"), list)
    )


# Simple keyword classifier matching the existing planner's logic
_GOAL_KEYWORDS: dict[str, list[str]] = {
    # Checked in order — first match wins
    "website_builder": ["build a website", "build me a website", "create a website", "make a website", "generate a website", "build a landing page", "create a landing page"],
    "content_creation": ["write", "create a post", "draft", "linkedin post", "twitter post", "blog post", "create content", "generate content", "article", "caption", "copy for"],
    "email_campaign": ["email campaign", "cold email", "send emails", "outreach email", "write an email", "draft an email"],
    "research": ["research", "learn about", "find out", "investigate", "analyze", "analyse", "what is", "summarize", "summarise"],
    "lead_generation": ["find leads", "find contacts", "find companies", "find emails", "get leads", "prospect", "lead list", "lead generation"],
}

_QUESTION_KEYWORDS = ["hello", "hi", "hey", "what can you", "how are you", "help me understand", "status", "who are you", "how does", "can you explain"]


def _keyword_fallback(user_input: str) -> dict[str, Any]:
    lower = user_input.lower()

    if any(kw in lower for kw in _QUESTION_KEYWORDS):
        return {"is_goal": False, "goal_type": "conversation", "structured_goal": {}, "task_plan": []}

    goal_type = "content_creation"  # default for action verbs
    for gtype, keywords in _GOAL_KEYWORDS.items():
        if any(kw in lower for kw in keywords):
            goal_type = gtype
            break

    template = _GOAL_TASK_TEMPLATES.get(goal_type, _GOAL_TASK_TEMPLATES["research"])
    # Fill in template placeholders
    plan_steps = []
    for step in template:
        filled_step = _fill_template(step, user_input)
        plan_steps.append(filled_step)

    return {
        "is_goal": True,
        "goal_type": goal_type,
        "structured_goal": {
            "action": goal_type,
            "target": user_input,
            "quantity": _extract_quantity(user_input),
            "constraints": [],
        },
        "task_plan": plan_steps,
    }


def _fill_template(step: dict, user_input: str) -> dict:
    import copy
    filled = copy.deepcopy(step)
    replacements = {
        "{target}": user_input[:60],
        "{topic}": user_input[:60],
        "{goal}": user_input[:60],
        "{type}": "outreach",
        "{content_type}": "blog post",
    }
    def _replace(obj: Any) -> Any:
        if isinstance(obj, str):
            for k, v in replacements.items():
                obj = obj.replace(k, v)
            return obj
        if isinstance(obj, dict):
            return {k: _replace(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_replace(i) for i in obj]
        return obj
    return _replace(filled)


def _extract_quantity(text: str) -> int | None:
    match = re.search(r"\b(\d+)\b", text)
    return int(match.group(1)) if match else None
