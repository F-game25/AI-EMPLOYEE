"""Hermes Agent — Autonomous, self-improving AI agent with full pipeline.

Pipeline:
  INPUT → OPENCLAW → OLLAMA (Hermes) → AGENT CORE → SKILLS → PLAN →
  ACTION → RESULT → VALIDATION → POSSIBLE CHANGES → OUTPUT →
  DASHBOARD + REMOTE SERVICES (WhatsApp, Discord, Telegram)

Commands (via chatlog / WhatsApp / Dashboard):
  hermes run <task>            — execute a task through the full pipeline
  hermes status                — show current agent state and recent tasks
  hermes skills                — list all available skills
  hermes memory                — show short-term and long-term memory summary
  hermes history               — show recent completed tasks
  hermes clear                 — clear short-term memory
  hermes retry                 — retry last failed task

FastAPI endpoints:
  GET  /                       — dashboard UI
  POST /api/run                — run a task through the pipeline
  GET  /api/status             — current agent state
  GET  /api/skills             — list available skills
  GET  /api/history            — recent task history
  GET  /api/memory             — agent memory summary
  POST /api/clear              — clear short-term memory

Config (in ~/.ai-employee/config/hermes-agent.env):
  HERMES_HOST          — bind address     (default: 127.0.0.1)
  HERMES_PORT          — port             (default: 8792)
  HERMES_MODEL         — Ollama model     (default: hermes3 or llama3.2 fallback)
  HERMES_MAX_RETRIES   — validation retry limit (default: 3)
  HERMES_NOTIFY_DISCORD — "true" to push results to Discord (default: true)
  HERMES_NOTIFY_WHATSAPP_TO — E.164 phone for result notifications (optional)
  HERMES_NOTIFY_TELEGRAM_CHAT_ID — Telegram chat ID for notifications (optional)

State files:
  ~/.ai-employee/state/hermes-agent.state.json     — current agent state
  ~/.ai-employee/state/hermes-tasks.json           — task history (last 50)
  ~/.ai-employee/state/hermes-memory.json          — long-term memory store
"""
from __future__ import annotations

import json
import logging
import os
import re
import sys
import time
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

try:
    import requests
    from fastapi import FastAPI
    from fastapi.responses import HTMLResponse, JSONResponse
    import uvicorn
    _FASTAPI_AVAILABLE = True
except ImportError:
    _FASTAPI_AVAILABLE = False
    FastAPI = None  # type: ignore[assignment,misc]
    HTMLResponse = None  # type: ignore[assignment,misc]
    JSONResponse = None  # type: ignore[assignment,misc]

# ── Module-level constants ────────────────────────────────────────────────────
TELEGRAM_MAX_MESSAGE_LENGTH = 4096
WHATSAPP_MAX_MESSAGE_LENGTH = 4096   # Twilio / Meta WhatsApp cap
DISCORD_MAX_MESSAGE_LENGTH = 2000
LOG_DESCRIPTION_MAX_LEN = 60

# ── Configuration ──────────────────────────────────────────────────────────────

AI_HOME = Path(os.environ.get("AI_HOME", str(Path.home() / ".ai-employee")))
STATE_FILE = AI_HOME / "state" / "hermes-agent.state.json"
TASKS_FILE = AI_HOME / "state" / "hermes-tasks.json"
MEMORY_FILE = AI_HOME / "state" / "hermes-memory.json"

HERMES_HOST = os.environ.get("HERMES_HOST", "127.0.0.1")
HERMES_PORT = int(os.environ.get("HERMES_PORT", "8792"))
HERMES_MODEL = os.environ.get("HERMES_MODEL", "hermes3")
HERMES_FALLBACK_MODEL = os.environ.get("HERMES_FALLBACK_MODEL", "llama3.2")
HERMES_MAX_RETRIES = int(os.environ.get("HERMES_MAX_RETRIES", "3"))
HERMES_NOTIFY_DISCORD = os.environ.get("HERMES_NOTIFY_DISCORD", "true").lower() == "true"
HERMES_NOTIFY_WHATSAPP_TO = os.environ.get("HERMES_NOTIFY_WHATSAPP_TO", "")
HERMES_NOTIFY_TELEGRAM_CHAT_ID = os.environ.get("HERMES_NOTIFY_TELEGRAM_CHAT_ID", "")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_TIMEOUT = int(os.environ.get("OLLAMA_TIMEOUT", "120"))

MAX_TASKS_HISTORY = int(os.environ.get("HERMES_MAX_HISTORY", "50"))
POLL_INTERVAL = int(os.environ.get("HERMES_POLL_INTERVAL", "5"))

logging.basicConfig(
    level=getattr(logging, os.environ.get("LOG_LEVEL", "INFO").upper(), logging.INFO),
    format="%(asctime)s [hermes-agent] %(levelname)s — %(message)s",
)
logger = logging.getLogger("hermes-agent")

# ── AI Router (optional, falls back to direct Ollama) ─────────────────────────

_ai_router_path = AI_HOME / "agents" / "ai-router"
if str(_ai_router_path) not in sys.path:
    sys.path.insert(0, str(_ai_router_path))

try:
    from ai_router import query_ai_for_agent as _query_ai_for_agent  # type: ignore
    _AI_ROUTER_AVAILABLE = True
except ImportError:
    _AI_ROUTER_AVAILABLE = False
    logger.warning("ai_router not found — using direct Ollama calls")

# ── Discord notifications (optional) ─────────────────────────────────────────

_tools_path = AI_HOME / "agents" / "tools"
if str(_tools_path) not in sys.path:
    sys.path.insert(0, str(_tools_path))

try:
    from discord_notify import notify_discord, is_discord_configured  # type: ignore
    _DISCORD_AVAILABLE = True
except ImportError:
    _DISCORD_AVAILABLE = False
    def notify_discord(msg: str, username: str = "AI Employee") -> bool:  # type: ignore
        return False
    def is_discord_configured() -> bool:  # type: ignore
        return False

try:
    from whatsapp import send_whatsapp  # type: ignore
    _WHATSAPP_AVAILABLE = True
except ImportError:
    _WHATSAPP_AVAILABLE = False
    def send_whatsapp(to: str, message: str, **kw) -> tuple:  # type: ignore
        return False, {"error": "whatsapp module not available"}

# ── Utility helpers ────────────────────────────────────────────────────────────


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def write_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


def load_tasks() -> list:
    if not TASKS_FILE.exists():
        return []
    try:
        return json.loads(TASKS_FILE.read_text())
    except Exception:
        return []


def save_tasks(tasks: list) -> None:
    TASKS_FILE.parent.mkdir(parents=True, exist_ok=True)
    TASKS_FILE.write_text(json.dumps(tasks[-MAX_TASKS_HISTORY:], indent=2))


def load_memory() -> dict:
    if not MEMORY_FILE.exists():
        return {"short_term": [], "long_term": [], "failures": []}
    try:
        return json.loads(MEMORY_FILE.read_text())
    except Exception:
        return {"short_term": [], "long_term": [], "failures": []}


def save_memory(memory: dict) -> None:
    MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    MEMORY_FILE.write_text(json.dumps(memory, indent=2))


# ── Short-term memory (in-process cache) ──────────────────────────────────────

_short_term_memory: list[dict] = []
MAX_SHORT_TERM = int(os.environ.get("HERMES_SHORT_TERM_MAX", "20"))


def remember_short(entry: dict) -> None:
    """Add entry to in-process short-term memory (capped at MAX_SHORT_TERM)."""
    _short_term_memory.append({**entry, "ts": now_iso()})
    if len(_short_term_memory) > MAX_SHORT_TERM:
        _short_term_memory.pop(0)


# ══════════════════════════════════════════════════════════════════════════════
# 1. OPENCLAW — Input normalisation & intent extraction
# ══════════════════════════════════════════════════════════════════════════════

_TASK_TYPES = {
    "search": ["find", "search", "look up", "research", "discover"],
    "generate": ["write", "create", "generate", "compose", "draft"],
    "analyse": ["analyse", "analyze", "evaluate", "assess", "review", "compare"],
    "code": ["code", "script", "program", "implement", "debug", "refactor"],
    "summarise": ["summarise", "summarize", "brief", "overview", "tldr"],
    "plan": ["plan", "strategy", "roadmap", "steps", "how to", "outline"],
    "lead": ["lead", "prospect", "outreach", "email", "contact"],
    "data": ["data", "report", "metrics", "stats", "numbers"],
}


def openclaw_process(raw_input: str | dict) -> dict:
    """Pre-process raw input: normalise, extract intent, entities, task type.

    Returns a normalised task descriptor:
    {
        "text": str,           # cleaned input text
        "task_type": str,      # detected task category
        "intent": str,         # short intent phrase
        "entities": list[str], # key entities / nouns
        "input_format": str,   # "text" | "json"
        "original": ...        # original raw input
    }
    """
    # ── Normalise input ──────────────────────────────────────────────────────
    if isinstance(raw_input, dict):
        text = raw_input.get("text", raw_input.get("task", str(raw_input)))
        input_format = "json"
    else:
        text = str(raw_input).strip()
        input_format = "text"

    text = text.strip()

    # ── Detect task type ─────────────────────────────────────────────────────
    text_lower = text.lower()
    task_type = "general"
    for ttype, keywords in _TASK_TYPES.items():
        if any(kw in text_lower for kw in keywords):
            task_type = ttype
            break

    # ── Extract rough entities (capitalised words / quoted strings) ──────────
    entities = re.findall(r'"([^"]+)"', text)
    entities += [w for w in re.findall(r"\b[A-Z][a-zA-Z]{2,}\b", text) if w not in {
        "The", "This", "That", "When", "What", "How", "Why", "Who",
        "Create", "Write", "Find", "Build", "Make", "Show",
    }]
    entities = list(dict.fromkeys(entities))[:10]  # deduplicate, cap at 10

    # ── Build a short intent phrase ───────────────────────────────────────────
    words = text.split()
    intent = " ".join(words[:8]) + ("…" if len(words) > 8 else "")

    logger.debug("openclaw: type=%s intent=%s entities=%s", task_type, intent, entities)

    return {
        "text": text,
        "task_type": task_type,
        "intent": intent,
        "entities": entities,
        "input_format": input_format,
        "original": raw_input,
    }


# ══════════════════════════════════════════════════════════════════════════════
# 2. LLM CORE — Ollama / ai_router integration
# ══════════════════════════════════════════════════════════════════════════════

HERMES_SYSTEM_PROMPT = """You are Hermes, an elite autonomous AI agent.
You think step-by-step, break complex tasks into clear subtasks, and execute
plans methodically. You always respond in valid JSON when asked for structured
output. You are precise, thorough, and self-critical — you evaluate whether
your outputs are truly good enough before declaring success.

When building plans, output JSON in this format:
{
  "steps": [
    {"id": 1, "description": "...", "skill": "...", "depends_on": []},
    ...
  ],
  "confidence": 0.0-1.0,
  "reasoning": "..."
}

When validating results, output JSON:
{
  "good_enough": true/false,
  "confidence": 0.0-1.0,
  "issues": ["...", ...],
  "improvements": ["...", ...]
}
"""


def _ollama_ready() -> bool:
    """Check whether Ollama is reachable and has the Hermes model available."""
    try:
        r = requests.get(f"{OLLAMA_HOST}/api/tags", timeout=3)
        if r.status_code != 200:
            return False
        models = [m.get("name", "") for m in r.json().get("models", [])]
        return any(HERMES_MODEL in m for m in models)
    except Exception:
        return False


def _ollama_chat(
    messages: list[dict],
    model: str | None = None,
    *,
    json_mode: bool = False,
) -> str:
    """Send a chat request to Ollama. Returns response text or raises."""
    mdl = model or HERMES_MODEL
    payload: dict = {
        "model": mdl,
        "messages": messages,
        "stream": False,
    }
    if json_mode:
        payload["format"] = "json"
    try:
        resp = requests.post(
            f"{OLLAMA_HOST}/api/chat",
            json=payload,
            timeout=OLLAMA_TIMEOUT,
        )
        resp.raise_for_status()
        return resp.json().get("message", {}).get("content", "").strip()
    except requests.exceptions.ConnectionError:
        # Try fallback model
        if mdl != HERMES_FALLBACK_MODEL:
            logger.warning("Hermes model unavailable, falling back to %s", HERMES_FALLBACK_MODEL)
            payload["model"] = HERMES_FALLBACK_MODEL
            resp = requests.post(
                f"{OLLAMA_HOST}/api/chat",
                json=payload,
                timeout=OLLAMA_TIMEOUT,
            )
            resp.raise_for_status()
            return resp.json().get("message", {}).get("content", "").strip()
        raise


def query_llm(prompt: str, *, agent_type: str = "reasoning", json_mode: bool = False) -> str:
    """Query the LLM — uses ai_router if available, otherwise direct Ollama."""
    if _AI_ROUTER_AVAILABLE:
        try:
            result = _query_ai_for_agent(
                agent_type,
                prompt,
                system_prompt=HERMES_SYSTEM_PROMPT,
            )
            answer = result.get("answer", "")
            if answer:
                return answer
        except Exception as exc:
            logger.warning("ai_router query failed (%s), falling back to Ollama", exc)

    # Direct Ollama fallback
    messages = [
        {"role": "system", "content": HERMES_SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]
    return _ollama_chat(messages, json_mode=json_mode)


# ══════════════════════════════════════════════════════════════════════════════
# 3. SKILLS MODULE
# ══════════════════════════════════════════════════════════════════════════════

class SkillResult:
    """Standard output envelope for all skill executions."""

    __slots__ = ("success", "output", "metadata", "error")

    def __init__(
        self,
        success: bool,
        output: str = "",
        metadata: dict | None = None,
        error: str = "",
    ) -> None:
        self.success = success
        self.output = output
        self.metadata = metadata or {}
        self.error = error

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "output": self.output,
            "metadata": self.metadata,
            "error": self.error,
        }


def _skill_content_generation(task: dict) -> SkillResult:
    """Generate written content (articles, emails, social posts, etc.)."""
    text = task.get("text", "")
    prompt = (
        f"Generate high-quality content for this request:\n\n{text}\n\n"
        "Return only the final content, ready to use."
    )
    try:
        output = query_llm(prompt, agent_type="creative")
        return SkillResult(True, output, {"skill": "content_generation", "chars": len(output)})
    except Exception as exc:
        return SkillResult(False, error=str(exc))


def _skill_research(task: dict) -> SkillResult:
    """Research and summarise information on a topic."""
    text = task.get("text", "")
    prompt = (
        f"Research and provide a comprehensive overview of:\n\n{text}\n\n"
        "Include key facts, insights, and actionable takeaways. "
        "Structure your answer with clear sections."
    )
    try:
        # Try web search via ai_router if available
        web_results = ""
        if _AI_ROUTER_AVAILABLE:
            try:
                from ai_router import search_web  # type: ignore
                hits = search_web(text, max_results=5)
                if hits:
                    web_results = "\n\nWeb search results:\n" + "\n".join(
                        f"- {h.get('title','')}: {h.get('snippet','')}" for h in hits[:5]
                    )
            except Exception:
                pass
        output = query_llm(prompt + web_results, agent_type="research")
        return SkillResult(True, output, {"skill": "research", "chars": len(output)})
    except Exception as exc:
        return SkillResult(False, error=str(exc))


def _skill_analysis(task: dict) -> SkillResult:
    """Analyse data, code, text, or situations and return insights."""
    text = task.get("text", "")
    prompt = (
        f"Perform a thorough analysis of the following:\n\n{text}\n\n"
        "Return: key findings, patterns, risks, opportunities, and recommendations."
    )
    try:
        output = query_llm(prompt, agent_type="analytics")
        return SkillResult(True, output, {"skill": "analysis", "chars": len(output)})
    except Exception as exc:
        return SkillResult(False, error=str(exc))


def _skill_planning(task: dict) -> SkillResult:
    """Break down a goal into actionable steps."""
    text = task.get("text", "")
    prompt = (
        f"Create a detailed, actionable plan for:\n\n{text}\n\n"
        "Break it into numbered steps with clear deliverables for each step."
    )
    try:
        output = query_llm(prompt, agent_type="reasoning")
        return SkillResult(True, output, {"skill": "planning", "chars": len(output)})
    except Exception as exc:
        return SkillResult(False, error=str(exc))


def _skill_code_generation(task: dict) -> SkillResult:
    """Write, review, or debug code."""
    text = task.get("text", "")
    prompt = (
        f"Write clean, production-ready code for:\n\n{text}\n\n"
        "Include comments, error handling, and usage examples."
    )
    try:
        output = query_llm(prompt, agent_type="coding")
        return SkillResult(True, output, {"skill": "code_generation", "chars": len(output)})
    except Exception as exc:
        return SkillResult(False, error=str(exc))


def _skill_lead_generation(task: dict) -> SkillResult:
    """Generate lead outreach copy or qualification questions."""
    text = task.get("text", "")
    prompt = (
        f"You are an elite sales professional. Create compelling lead generation "
        f"content for:\n\n{text}\n\n"
        "Include: value proposition, pain points addressed, call to action."
    )
    try:
        output = query_llm(prompt, agent_type="sales")
        return SkillResult(True, output, {"skill": "lead_generation", "chars": len(output)})
    except Exception as exc:
        return SkillResult(False, error=str(exc))


def _skill_summarise(task: dict) -> SkillResult:
    """Summarise long text into concise key points."""
    text = task.get("text", "")
    prompt = (
        f"Provide a clear, concise summary of:\n\n{text}\n\n"
        "Include: TL;DR (1-2 sentences), key points (bullet list), next actions."
    )
    try:
        output = query_llm(prompt, agent_type="general")
        return SkillResult(True, output, {"skill": "summarise", "chars": len(output)})
    except Exception as exc:
        return SkillResult(False, error=str(exc))


def _skill_general(task: dict) -> SkillResult:
    """General-purpose skill for tasks that don't match a specific category."""
    text = task.get("text", "")
    prompt = f"Complete this task thoroughly and helpfully:\n\n{text}"
    try:
        output = query_llm(prompt, agent_type="general")
        return SkillResult(True, output, {"skill": "general", "chars": len(output)})
    except Exception as exc:
        return SkillResult(False, error=str(exc))


# ── Skill registry ─────────────────────────────────────────────────────────────

SKILLS: dict[str, dict] = {
    "content_generation": {
        "fn": _skill_content_generation,
        "description": "Generate written content (articles, emails, social posts)",
        "input_schema": {"text": "str"},
        "output_schema": {"output": "str"},
        "task_types": ["generate"],
        "rank": 1.0,
    },
    "research": {
        "fn": _skill_research,
        "description": "Research and summarise information on any topic",
        "input_schema": {"text": "str"},
        "output_schema": {"output": "str"},
        "task_types": ["search", "data"],
        "rank": 1.0,
    },
    "analysis": {
        "fn": _skill_analysis,
        "description": "Analyse data, code, text, or situations",
        "input_schema": {"text": "str"},
        "output_schema": {"output": "str"},
        "task_types": ["analyse", "data"],
        "rank": 1.0,
    },
    "planning": {
        "fn": _skill_planning,
        "description": "Break down goals into actionable steps and roadmaps",
        "input_schema": {"text": "str"},
        "output_schema": {"output": "str"},
        "task_types": ["plan"],
        "rank": 1.0,
    },
    "code_generation": {
        "fn": _skill_code_generation,
        "description": "Write, review, and debug code in any language",
        "input_schema": {"text": "str"},
        "output_schema": {"output": "str"},
        "task_types": ["code"],
        "rank": 1.0,
    },
    "lead_generation": {
        "fn": _skill_lead_generation,
        "description": "Create lead outreach copy and qualification content",
        "input_schema": {"text": "str"},
        "output_schema": {"output": "str"},
        "task_types": ["lead"],
        "rank": 1.0,
    },
    "summarise": {
        "fn": _skill_summarise,
        "description": "Summarise long text into key points and TL;DR",
        "input_schema": {"text": "str"},
        "output_schema": {"output": "str"},
        "task_types": ["summarise"],
        "rank": 1.0,
    },
    "general": {
        "fn": _skill_general,
        "description": "General-purpose reasoning and task completion",
        "input_schema": {"text": "str"},
        "output_schema": {"output": "str"},
        "task_types": ["general"],
        "rank": 0.8,
    },
}


def select_skill(task_type: str) -> str:
    """Select the best-ranked skill for a given task type."""
    candidates = [
        (name, info)
        for name, info in SKILLS.items()
        if task_type in info["task_types"]
    ]
    if not candidates:
        return "general"
    # Sort by rank descending; tie-break by name for determinism
    candidates.sort(key=lambda x: (-x[1]["rank"], x[0]))
    return candidates[0][0]


def execute_skill(skill_name: str, task: dict) -> SkillResult:
    """Execute a skill by name."""
    skill = SKILLS.get(skill_name)
    if not skill:
        logger.warning("Unknown skill %s — falling back to general", skill_name)
        skill = SKILLS["general"]
    logger.info("Executing skill: %s", skill_name)
    try:
        result: SkillResult = skill["fn"](task)
        return result
    except Exception as exc:
        logger.error("Skill %s raised exception: %s", skill_name, exc)
        return SkillResult(False, error=str(exc))


# ══════════════════════════════════════════════════════════════════════════════
# 4. PLANNING ENGINE
# ══════════════════════════════════════════════════════════════════════════════


def build_plan(normalized_input: dict) -> list[dict]:
    """Ask the LLM to decompose the task into an ordered list of steps.

    Each step: {"id": int, "description": str, "skill": str, "depends_on": list}
    Falls back to a single-step plan on parse failure.
    """
    text = normalized_input["text"]
    task_type = normalized_input["task_type"]
    available_skills = ", ".join(SKILLS.keys())

    prompt = (
        f"You are a planning engine. Decompose this task into clear execution steps.\n\n"
        f"Task: {text}\n"
        f"Task type: {task_type}\n"
        f"Available skills: {available_skills}\n\n"
        "Return ONLY a JSON object with this structure:\n"
        "{\n"
        '  "steps": [\n'
        '    {"id": 1, "description": "...", "skill": "...", "depends_on": []},\n'
        "    ...\n"
        "  ],\n"
        '  "confidence": 0.9,\n'
        '  "reasoning": "..."\n'
        "}\n\n"
        "Use 1-5 steps. Each skill must be one of the available skills listed above."
    )

    try:
        raw = query_llm(prompt, agent_type="reasoning", json_mode=True)
        # Extract JSON from response (handle markdown code blocks)
        json_match = re.search(r"\{.*\}", raw, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group())
            steps = data.get("steps", [])
            # Validate each step has required fields
            validated = []
            for i, step in enumerate(steps, 1):
                skill = step.get("skill", "general")
                if skill not in SKILLS:
                    skill = select_skill(task_type)
                validated.append({
                    "id": i,
                    "description": step.get("description", f"Step {i}"),
                    "skill": skill,
                    "depends_on": step.get("depends_on", []),
                })
            if validated:
                logger.info("Plan built: %d steps", len(validated))
                return validated
    except Exception as exc:
        logger.warning("Plan parsing failed (%s) — using single-step fallback", exc)

    # Fallback: single step using best skill
    skill = select_skill(task_type)
    return [{"id": 1, "description": text, "skill": skill, "depends_on": []}]


# ══════════════════════════════════════════════════════════════════════════════
# 5. ACTION EXECUTION
# ══════════════════════════════════════════════════════════════════════════════


def execute_plan(
    plan: list[dict],
    normalized_input: dict,
    *,
    max_workers: int = 3,
) -> list[dict]:
    """Execute the plan steps, respecting dependencies.

    Steps with no unresolved dependencies run concurrently.
    Returns a list of step results:
    {"step_id": int, "description": str, "skill": str, "result": dict, "success": bool}
    """
    completed: dict[int, dict] = {}  # step_id → result dict
    remaining = list(plan)

    def _can_run(step: dict) -> bool:
        return all(dep in completed for dep in step.get("depends_on", []))

    def _run_step(step: dict) -> dict:
        logger.info("Running step %d: %s [skill=%s]", step["id"], step["description"][:LOG_DESCRIPTION_MAX_LEN], step["skill"])
        # Build per-step task context, enriched with prior results
        prior_outputs = "\n\n".join(
            f"Step {sid} output:\n{completed[sid]['result'].get('output','')}"
            for sid in sorted(step.get("depends_on", []))
            if sid in completed and completed[sid]["result"].get("output")
        )
        step_text = step["description"]
        if prior_outputs:
            step_text = f"{step_text}\n\nContext from previous steps:\n{prior_outputs}"

        step_task = {**normalized_input, "text": step_text}
        result = execute_skill(step["skill"], step_task)
        return {
            "step_id": step["id"],
            "description": step["description"],
            "skill": step["skill"],
            "result": result.to_dict(),
            "success": result.success,
        }

    max_iter = len(plan) * 2  # safety cap
    iteration = 0
    while remaining and iteration < max_iter:
        iteration += 1
        runnable = [s for s in remaining if _can_run(s)]
        if not runnable:
            logger.error("Dependency deadlock — marking remaining steps as skipped")
            for step in remaining:
                completed[step["id"]] = {
                    "step_id": step["id"],
                    "description": step["description"],
                    "skill": step["skill"],
                    "result": {"success": False, "output": "", "error": "dependency deadlock"},
                    "success": False,
                }
            break

        with ThreadPoolExecutor(max_workers=min(max_workers, len(runnable))) as pool:
            futures = {pool.submit(_run_step, step): step for step in runnable}
            for future in as_completed(futures):
                step_result = future.result()
                completed[step_result["step_id"]] = step_result
                remaining = [s for s in remaining if s["id"] != step_result["step_id"]]

    return list(completed.values())


# ══════════════════════════════════════════════════════════════════════════════
# 6. RESULT GENERATION
# ══════════════════════════════════════════════════════════════════════════════


def generate_result(step_results: list[dict], normalized_input: dict) -> dict:
    """Combine step outputs into a single structured result."""
    successful = [r for r in step_results if r["success"]]
    failed = [r for r in step_results if not r["success"]]

    if not successful:
        return {
            "output": "",
            "success": False,
            "error": "; ".join(r["result"].get("error", "") for r in failed),
            "steps_run": len(step_results),
            "steps_ok": 0,
            "tools_used": [],
        }

    # If single step, return its output directly
    if len(step_results) == 1:
        output = successful[0]["result"].get("output", "")
    else:
        # Combine multiple step outputs with the LLM
        combined_parts = "\n\n".join(
            f"## Step {r['step_id']}: {r['description']}\n{r['result'].get('output','')}"
            for r in successful
        )
        synthesis_prompt = (
            f"Original task: {normalized_input['text']}\n\n"
            f"The task was completed in {len(successful)} steps. "
            f"Combine the following step outputs into a single, coherent, "
            f"well-structured final answer:\n\n{combined_parts}"
        )
        try:
            output = query_llm(synthesis_prompt, agent_type="reasoning")
        except Exception as exc:
            # Fall back to simple concatenation
            logger.warning("Result synthesis failed (%s) — concatenating outputs", exc)
            output = "\n\n---\n\n".join(
                r["result"].get("output", "") for r in successful
            )

    tools_used = list({r["skill"] for r in step_results})
    return {
        "output": output,
        "success": True,
        "error": "",
        "steps_run": len(step_results),
        "steps_ok": len(successful),
        "steps_failed": len(failed),
        "tools_used": tools_used,
    }


# ══════════════════════════════════════════════════════════════════════════════
# 7. VALIDATION LAYER
# ══════════════════════════════════════════════════════════════════════════════


def validate_result(result: dict, original_task: str) -> dict:
    """Evaluate the result quality. Returns validation report.

    {
        "good_enough": bool,
        "confidence": float,
        "issues": list[str],
        "improvements": list[str],
    }
    """
    output = result.get("output", "")

    # Quick heuristic checks first
    if not output or len(output.strip()) < 20:
        return {
            "good_enough": False,
            "confidence": 0.0,
            "issues": ["Output is empty or too short"],
            "improvements": ["Re-run the task with a more specific prompt"],
        }

    if not result.get("success"):
        return {
            "good_enough": False,
            "confidence": 0.0,
            "issues": [result.get("error", "Task execution failed")],
            "improvements": ["Fix the underlying error and retry"],
        }

    # LLM-based quality evaluation
    prompt = (
        f"Evaluate whether this AI output adequately addresses the original task.\n\n"
        f"Original task: {original_task}\n\n"
        f"AI output (first 1500 chars): {output[:1500]}\n\n"
        "Return ONLY a JSON object:\n"
        "{\n"
        '  "good_enough": true,\n'
        '  "confidence": 0.85,\n'
        '  "issues": [],\n'
        '  "improvements": []\n'
        "}\n\n"
        "good_enough = true if the output fully and correctly addresses the task."
    )

    try:
        raw = query_llm(prompt, agent_type="reasoning", json_mode=True)
        json_match = re.search(r"\{.*\}", raw, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group())
            return {
                "good_enough": bool(data.get("good_enough", False)),
                "confidence": float(data.get("confidence", 0.5)),
                "issues": list(data.get("issues", [])),
                "improvements": list(data.get("improvements", [])),
            }
    except Exception as exc:
        logger.warning("Validation LLM call failed (%s) — using heuristic pass", exc)

    # Heuristic fallback: if output is long enough and task completed, pass
    heuristic_pass = len(output.strip()) >= 100 and result.get("success", False)
    return {
        "good_enough": heuristic_pass,
        "confidence": 0.6 if heuristic_pass else 0.3,
        "issues": [] if heuristic_pass else ["Could not verify quality — output may be incomplete"],
        "improvements": [],
    }


# ══════════════════════════════════════════════════════════════════════════════
# 8. POSSIBLE CHANGES LOOP (self-improvement)
# ══════════════════════════════════════════════════════════════════════════════


def analyse_failure(result: dict, validation: dict, attempt: int) -> str:
    """Ask the LLM to propose improvements after a failed validation."""
    issues = "; ".join(validation.get("issues", []))
    improvements = "; ".join(validation.get("improvements", []))
    output_preview = result.get("output", "")[:500]

    prompt = (
        f"A task failed validation on attempt {attempt}.\n\n"
        f"Issues: {issues}\n"
        f"Suggested improvements: {improvements}\n"
        f"Current output preview: {output_preview}\n\n"
        "Provide a revised, improved prompt that would fix these issues. "
        "Return ONLY the improved prompt text, nothing else."
    )
    try:
        return query_llm(prompt, agent_type="reasoning")
    except Exception:
        return ""


# ══════════════════════════════════════════════════════════════════════════════
# 9. REMOTE NOTIFICATIONS
# ══════════════════════════════════════════════════════════════════════════════


def _send_telegram(chat_id: str, message: str) -> bool:
    """Send a message via Telegram Bot API."""
    if not TELEGRAM_BOT_TOKEN or not chat_id:
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = json.dumps({"chat_id": chat_id, "text": message[:TELEGRAM_MAX_MESSAGE_LENGTH]}).encode()
    try:
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status < 400
    except Exception as exc:
        logger.warning("Telegram notification failed: %s", exc)
        return False


def notify_all(task_id: str, intent: str, result: dict, validation: dict) -> None:
    """Push result summary to all configured remote services."""
    confidence = validation.get("confidence", 0.0)
    status_emoji = "✅" if validation.get("good_enough") else "⚠️"
    output_preview = result.get("output", "")[:300]
    tools = ", ".join(result.get("tools_used", []))

    message = (
        f"{status_emoji} Hermes Agent completed task\n"
        f"ID: {task_id}\n"
        f"Task: {intent}\n"
        f"Confidence: {confidence:.0%}\n"
        f"Steps: {result.get('steps_run', 0)} ({result.get('steps_ok', 0)} ok)\n"
        f"Skills: {tools}\n"
        f"Output preview:\n{output_preview}"
    )

    # Discord
    if HERMES_NOTIFY_DISCORD and _DISCORD_AVAILABLE and is_discord_configured():
        notify_discord(message[:DISCORD_MAX_MESSAGE_LENGTH], username="Hermes Agent")
        logger.info("Discord notification sent for task %s", task_id)

    # WhatsApp
    if HERMES_NOTIFY_WHATSAPP_TO and _WHATSAPP_AVAILABLE:
        ok, info = send_whatsapp(HERMES_NOTIFY_WHATSAPP_TO, message[:WHATSAPP_MAX_MESSAGE_LENGTH])
        if ok:
            logger.info("WhatsApp notification sent for task %s", task_id)
        else:
            logger.warning("WhatsApp notification failed: %s", info.get("error"))

    # Telegram
    if HERMES_NOTIFY_TELEGRAM_CHAT_ID:
        _send_telegram(HERMES_NOTIFY_TELEGRAM_CHAT_ID, message)
        logger.info("Telegram notification sent for task %s", task_id)


# ══════════════════════════════════════════════════════════════════════════════
# 10. MAIN PIPELINE ORCHESTRATOR
# ══════════════════════════════════════════════════════════════════════════════


def run_pipeline(raw_input: str | dict, *, task_id: str | None = None) -> dict:
    """Execute the full Hermes pipeline and return the final result.

    Returns:
    {
        "task_id": str,
        "status": "success" | "failed" | "partial",
        "output": str,
        "plan": list[dict],
        "step_results": list[dict],
        "validation": dict,
        "attempts": int,
        "confidence": float,
        "tools_used": list[str],
        "steps_taken": int,
        "metadata": dict,
        "ts_start": str,
        "ts_end": str,
    }
    """
    task_id = task_id or str(uuid.uuid4())[:8]
    ts_start = now_iso()
    logger.info("=== Hermes pipeline start: task_id=%s ===", task_id)

    # ── 1. OpenClaw: normalise & extract intent ───────────────────────────────
    normalized = openclaw_process(raw_input)
    logger.info("OpenClaw: type=%s intent=%s", normalized["task_type"], normalized["intent"])

    # ── 2. Build plan ─────────────────────────────────────────────────────────
    plan = build_plan(normalized)
    logger.info("Plan: %d steps", len(plan))

    # ── 3. Self-improvement retry loop ────────────────────────────────────────
    result: dict = {}
    validation: dict = {"good_enough": False, "confidence": 0.0, "issues": [], "improvements": []}
    step_results: list[dict] = []
    attempts = 0
    current_input = normalized

    while attempts < HERMES_MAX_RETRIES:
        attempts += 1
        logger.info("Attempt %d/%d", attempts, HERMES_MAX_RETRIES)

        # ── 4. Execute plan ───────────────────────────────────────────────────
        step_results = execute_plan(plan, current_input)

        # ── 5. Generate combined result ───────────────────────────────────────
        result = generate_result(step_results, current_input)

        # ── 6. Validate ───────────────────────────────────────────────────────
        validation = validate_result(result, normalized["text"])
        logger.info(
            "Validation: good_enough=%s confidence=%.2f",
            validation["good_enough"],
            validation["confidence"],
        )

        if validation["good_enough"]:
            break

        if attempts < HERMES_MAX_RETRIES:
            # Analyse failure & adjust
            logger.info("Result not good enough — analysing failure for retry...")
            improved_prompt = analyse_failure(result, validation, attempts)
            if improved_prompt:
                # Store failure in memory for self-improvement
                memory = load_memory()
                memory.setdefault("failures", []).append({
                    "ts": now_iso(),
                    "task": normalized["text"][:200],
                    "issues": validation.get("issues", []),
                    "improvement": improved_prompt[:500],
                    "attempt": attempts,
                })
                memory["failures"] = memory["failures"][-100:]
                save_memory(memory)

                # Rebuild plan with improved prompt
                improved_normalized = openclaw_process(improved_prompt)
                # Keep original task type for routing
                improved_normalized["task_type"] = normalized["task_type"]
                plan = build_plan(improved_normalized)
                current_input = improved_normalized
            else:
                logger.warning("No improvement suggestion generated — stopping retry")
                break

    # ── 7. Finalize output ────────────────────────────────────────────────────
    ts_end = now_iso()
    status = "success" if validation.get("good_enough") else (
        "partial" if result.get("output") else "failed"
    )

    final_result = {
        "task_id": task_id,
        "status": status,
        "output": result.get("output", ""),
        "plan": plan,
        "step_results": step_results,
        "validation": validation,
        "attempts": attempts,
        "confidence": validation.get("confidence", 0.0),
        "tools_used": result.get("tools_used", []),
        "steps_taken": result.get("steps_run", 0),
        "metadata": {
            "task_type": normalized["task_type"],
            "intent": normalized["intent"],
            "entities": normalized["entities"],
            "input_format": normalized["input_format"],
        },
        "ts_start": ts_start,
        "ts_end": ts_end,
    }

    # ── 8. Persist task history ───────────────────────────────────────────────
    tasks = load_tasks()
    tasks.append({
        "task_id": task_id,
        "status": status,
        "intent": normalized["intent"],
        "confidence": validation.get("confidence", 0.0),
        "attempts": attempts,
        "tools_used": result.get("tools_used", []),
        "ts_start": ts_start,
        "ts_end": ts_end,
    })
    save_tasks(tasks)

    # ── 9. Update short-term memory ───────────────────────────────────────────
    remember_short({
        "task_id": task_id,
        "intent": normalized["intent"],
        "status": status,
        "confidence": validation.get("confidence", 0.0),
    })

    # ── 10. Write agent state ─────────────────────────────────────────────────
    write_state({
        "status": "idle",
        "last_task_id": task_id,
        "last_task_status": status,
        "last_task_intent": normalized["intent"],
        "last_run": ts_end,
        "model": HERMES_MODEL,
    })

    # ── 11. Send remote notifications ─────────────────────────────────────────
    notify_all(task_id, normalized["intent"], result, validation)

    logger.info(
        "=== Hermes pipeline done: task_id=%s status=%s confidence=%.2f attempts=%d ===",
        task_id, status, validation.get("confidence", 0.0), attempts,
    )
    return final_result


# ══════════════════════════════════════════════════════════════════════════════
# 11. FASTAPI APPLICATION + DASHBOARD
# ══════════════════════════════════════════════════════════════════════════════

if _FASTAPI_AVAILABLE:
    app = FastAPI(title="Hermes Agent", version="1.0.0")
else:
    class _StubApp:  # type: ignore[no-redef]
        """Minimal stub so @app route decorators don't raise at import time."""
        def get(self, *a, **kw):
            return lambda f: f
        def post(self, *a, **kw):
            return lambda f: f
    app = _StubApp()  # type: ignore[assignment]

_DASHBOARD_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  <title>Hermes Agent Dashboard</title>
  <style>
    *{box-sizing:border-box;margin:0;padding:0}
    body{font-family:system-ui,sans-serif;background:#0f172a;color:#e2e8f0;min-height:100vh;padding:24px}
    h1{color:#a78bfa;margin-bottom:4px;font-size:1.8em;letter-spacing:-0.5px}
    h2{color:#c4b5fd;font-size:1.1em;margin-bottom:12px;border-bottom:1px solid #334155;padding-bottom:6px}
    .badge{display:inline-block;background:#2e1065;color:#c4b5fd;padding:4px 14px;border-radius:20px;font-size:.85em;margin-bottom:20px}
    .grid{display:grid;grid-template-columns:1fr 1fr;gap:16px;max-width:1200px;margin:0 auto}
    .card{background:#1e293b;border:1px solid #334155;border-radius:12px;padding:20px}
    .card.wide{grid-column:1/-1}
    .metric{text-align:center;padding:12px}
    .metric .val{font-size:2em;font-weight:700;color:#a78bfa}
    .metric .lbl{font-size:.8em;color:#64748b;margin-top:2px}
    #run-area{display:flex;flex-direction:column;gap:10px}
    textarea{width:100%;background:#0f172a;border:1px solid #334155;color:#e2e8f0;border-radius:8px;padding:10px;font-size:.9em;resize:vertical;min-height:80px}
    button{background:linear-gradient(135deg,#7c3aed,#4f46e5);color:#fff;border:none;padding:10px 22px;border-radius:8px;cursor:pointer;font-size:.9em;font-weight:600}
    button:hover{opacity:.88}
    button:disabled{opacity:.45;cursor:not-allowed}
    #result-box{background:#0f172a;border:1px solid #334155;border-radius:8px;padding:14px;min-height:80px;max-height:340px;overflow-y:auto;font-size:.85em;white-space:pre-wrap;word-break:break-word;line-height:1.6}
    .step-row{display:flex;align-items:center;gap:8px;padding:6px 0;border-bottom:1px solid #1e293b;font-size:.83em}
    .step-ok{color:#4ade80} .step-fail{color:#f87171}
    .tag{background:#1e3a5f;color:#93c5fd;padding:2px 8px;border-radius:10px;font-size:.75em;margin-right:4px}
    .history-row{display:flex;align-items:center;gap:8px;padding:5px 0;border-bottom:1px solid #1e293b;font-size:.82em}
    .status-ok{color:#4ade80} .status-fail{color:#f87171} .status-partial{color:#fbbf24}
    .progress-bar{background:#1e293b;border-radius:4px;height:6px;width:100%;margin-top:6px}
    .progress-fill{background:linear-gradient(90deg,#7c3aed,#4f46e5);height:6px;border-radius:4px;transition:width .3s}
    #status-bar{font-size:.82em;color:#64748b;margin-top:8px;min-height:18px}
    .skills-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:8px}
    .skill-card{background:#0f172a;border:1px solid #334155;border-radius:8px;padding:10px;font-size:.8em}
    .skill-name{color:#a78bfa;font-weight:600;margin-bottom:4px}
    .skill-desc{color:#94a3b8;line-height:1.4}
  </style>
</head>
<body>
<div class="grid">
  <div class="card wide">
    <h1>🧠 Hermes Agent</h1>
    <div class="badge" id="model-badge">Loading...</div>
  </div>

  <div class="card">
    <h2>📊 Metrics</h2>
    <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px">
      <div class="metric"><div class="val" id="m-total">—</div><div class="lbl">Tasks Run</div></div>
      <div class="metric"><div class="val" id="m-success">—</div><div class="lbl">Success Rate</div></div>
      <div class="metric"><div class="val" id="m-avg-conf">—</div><div class="lbl">Avg Confidence</div></div>
    </div>
  </div>

  <div class="card">
    <h2>⚡ Run Task</h2>
    <div id="run-area">
      <textarea id="task-input" placeholder="Enter your task here...
Examples:
• Write a cold email for a SaaS product
• Analyse the current AI market landscape
• Create a 5-step plan to grow a Twitter account
• Write Python code to parse JSON from an API"></textarea>
      <button onclick="runTask()" id="run-btn">🚀 Run Task</button>
      <div id="status-bar"></div>
    </div>
  </div>

  <div class="card wide">
    <h2>📋 Result</h2>
    <div id="pipeline-steps" style="margin-bottom:12px"></div>
    <div id="result-box">No task run yet. Enter a task above and click Run.</div>
    <div id="result-meta" style="font-size:.78em;color:#64748b;margin-top:8px"></div>
  </div>

  <div class="card">
    <h2>📜 Task History</h2>
    <div id="history-list"><span style="color:#4b5563">No history yet.</span></div>
  </div>

  <div class="card">
    <h2>🔧 Available Skills</h2>
    <div id="skills-list" class="skills-grid"></div>
  </div>
</div>
<script>
async function loadStatus(){
  try{
    const r=await fetch('/api/status');
    const d=await r.json();
    document.getElementById('model-badge').textContent='Model: '+d.model+' | Status: '+d.status;
    if(d.metrics){
      document.getElementById('m-total').textContent=d.metrics.total_tasks;
      document.getElementById('m-success').textContent=d.metrics.success_rate+'%';
      document.getElementById('m-avg-conf').textContent=(d.metrics.avg_confidence*100).toFixed(0)+'%';
    }
  }catch(e){}
}
async function loadHistory(){
  try{
    const r=await fetch('/api/history');
    const d=await r.json();
    const tasks=d.tasks||[];
    const el=document.getElementById('history-list');
    if(!tasks.length){el.innerHTML='<span style="color:#4b5563">No history yet.</span>';return;}
    el.innerHTML=tasks.slice(-10).reverse().map(t=>{
      const cls=t.status==='success'?'status-ok':t.status==='partial'?'status-partial':'status-fail';
      const conf=(t.confidence*100).toFixed(0)+'%';
      return`<div class="history-row"><span class="${cls}">●</span><span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(t.intent)}</span><span style="color:#64748b;font-size:.75em">${conf}</span></div>`;
    }).join('');
  }catch(e){}
}
async function loadSkills(){
  try{
    const r=await fetch('/api/skills');
    const d=await r.json();
    const el=document.getElementById('skills-list');
    el.innerHTML=(d.skills||[]).map(s=>`<div class="skill-card"><div class="skill-name">${esc(s.name)}</div><div class="skill-desc">${esc(s.description)}</div></div>`).join('');
  }catch(e){}
}
function esc(s){return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}
async function runTask(){
  const input=document.getElementById('task-input').value.trim();
  if(!input)return;
  const btn=document.getElementById('run-btn');
  btn.disabled=true;
  document.getElementById('status-bar').textContent='Running pipeline…';
  document.getElementById('result-box').textContent='Processing…';
  document.getElementById('pipeline-steps').innerHTML='';
  document.getElementById('result-meta').textContent='';
  try{
    const r=await fetch('/api/run',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({task:input})});
    const d=await r.json();
    // Pipeline steps
    if(d.step_results&&d.step_results.length){
      document.getElementById('pipeline-steps').innerHTML='<div style="margin-bottom:8px;font-size:.8em;color:#94a3b8">Pipeline steps:</div>'+
        d.step_results.map(s=>`<div class="step-row"><span class="${s.success?'step-ok':'step-fail'}">${s.success?'✅':'❌'}</span><span>${esc(s.description)}</span><span class="tag">${esc(s.skill)}</span></div>`).join('');
    }
    // Result
    const out=d.output||d.error||'(no output)';
    document.getElementById('result-box').textContent=out;
    const v=d.validation||{};
    const conf=(( d.confidence||0)*100).toFixed(0);
    const status=d.status==='success'?'✅ Success':d.status==='partial'?'⚠️ Partial':'❌ Failed';
    document.getElementById('result-meta').textContent=`${status} | Confidence: ${conf}% | Attempts: ${d.attempts} | Steps: ${d.steps_taken} | Skills: ${(d.tools_used||[]).join(', ')}`;
    document.getElementById('status-bar').textContent=`Done in ${d.attempts} attempt(s). Confidence: ${conf}%`;
  }catch(e){
    document.getElementById('result-box').textContent='Error: '+e.message;
    document.getElementById('status-bar').textContent='Error occurred';
  }
  btn.disabled=false;
  loadStatus();
  loadHistory();
}
document.getElementById('task-input').addEventListener('keydown',e=>{if(e.key==='Enter'&&e.ctrlKey){runTask();}});
loadStatus();loadHistory();loadSkills();
setInterval(()=>{loadStatus();loadHistory();},15000);
</script>
</body>
</html>"""


@app.get("/", response_class=HTMLResponse)
def dashboard() -> str:
    return _DASHBOARD_HTML


@app.post("/api/run")
def api_run(payload: dict) -> JSONResponse:
    """Run a task through the full Hermes pipeline."""
    raw = payload.get("task", payload.get("text", payload.get("input", "")))
    if not raw:
        return JSONResponse({"error": "No task provided. Use {'task': '...'}"}, status_code=400)
    try:
        result = run_pipeline(raw if isinstance(raw, (str, dict)) else str(raw))
        return JSONResponse(result)
    except Exception as exc:
        logger.exception("Pipeline error for payload %s", str(payload)[:100])
        error_type = type(exc).__name__
        return JSONResponse(
            {"error": "pipeline_error", "error_type": error_type, "status": "failed"},
            status_code=500,
        )


@app.get("/api/status")
def api_status() -> JSONResponse:
    """Return current agent state and performance metrics."""
    state: dict = {}
    if STATE_FILE.exists():
        try:
            state = json.loads(STATE_FILE.read_text())
        except Exception:
            pass

    tasks = load_tasks()
    total = len(tasks)
    success_count = sum(1 for t in tasks if t.get("status") == "success")
    avg_conf = (
        sum(t.get("confidence", 0.0) for t in tasks) / total if total else 0.0
    )
    success_rate = round((success_count / total) * 100, 1) if total else 0.0

    return JSONResponse({
        "status": state.get("status", "idle"),
        "model": HERMES_MODEL,
        "ollama_host": OLLAMA_HOST,
        "ollama_ready": _ollama_ready(),
        "last_task_id": state.get("last_task_id"),
        "last_task_status": state.get("last_task_status"),
        "last_run": state.get("last_run"),
        "max_retries": HERMES_MAX_RETRIES,
        "skills_count": len(SKILLS),
        "metrics": {
            "total_tasks": total,
            "success_rate": success_rate,
            "avg_confidence": round(avg_conf, 3),
        },
    })


@app.get("/api/skills")
def api_skills() -> JSONResponse:
    """List all available skills."""
    return JSONResponse({
        "skills": [
            {
                "name": name,
                "description": info["description"],
                "task_types": info["task_types"],
                "rank": info["rank"],
            }
            for name, info in SKILLS.items()
        ]
    })


@app.get("/api/history")
def api_history() -> JSONResponse:
    """Return recent task history."""
    tasks = load_tasks()
    return JSONResponse({"tasks": tasks[-50:], "total": len(tasks)})


@app.get("/api/memory")
def api_memory() -> JSONResponse:
    """Return agent memory summary."""
    memory = load_memory()
    return JSONResponse({
        "short_term": _short_term_memory[-20:],
        "long_term_count": len(memory.get("long_term", [])),
        "failure_count": len(memory.get("failures", [])),
        "recent_failures": memory.get("failures", [])[-5:],
    })


@app.post("/api/clear")
def api_clear() -> JSONResponse:
    """Clear short-term memory."""
    global _short_term_memory
    _short_term_memory = []
    return JSONResponse({"status": "cleared"})


@app.get("/health")
def health() -> JSONResponse:
    return JSONResponse({"status": "ok", "agent": "hermes-agent"})


# ══════════════════════════════════════════════════════════════════════════════
# 12. CHATLOG POLLING (background worker)
# ══════════════════════════════════════════════════════════════════════════════

CHATLOG = AI_HOME / "state" / "chatlog.jsonl"
_last_chatlog_pos: int = 0


def _process_chatlog_commands() -> None:
    """Poll chatlog for `hermes` commands and run them via the pipeline."""
    global _last_chatlog_pos
    if not CHATLOG.exists():
        return
    try:
        with CHATLOG.open() as fh:
            fh.seek(_last_chatlog_pos)
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                except Exception:
                    continue
                text = msg.get("text", "").strip()
                if not text.lower().startswith("hermes "):
                    continue
                command = text[7:].strip()
                logger.info("Chatlog command: hermes %s", command[:60])
                _handle_chatlog_command(command)
            _last_chatlog_pos = fh.tell()
    except Exception as exc:
        logger.debug("Chatlog poll error: %s", exc)


def _handle_chatlog_command(command: str) -> None:
    """Handle a hermes command from chatlog."""
    global _short_term_memory
    cmd_lower = command.lower()
    if cmd_lower == "status":
        state = json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {}
        logger.info("Status: %s", state)
    elif cmd_lower == "skills":
        logger.info("Skills: %s", ", ".join(SKILLS.keys()))
    elif cmd_lower == "memory":
        memory = load_memory()
        logger.info(
            "Memory: %d short-term, %d long-term, %d failures",
            len(_short_term_memory),
            len(memory.get("long_term", [])),
            len(memory.get("failures", [])),
        )
    elif cmd_lower == "clear":
        _short_term_memory = []
        logger.info("Short-term memory cleared")
    elif cmd_lower.startswith("run "):
        task_text = command[4:].strip()
        if task_text:
            run_pipeline(task_text)
    else:
        # Treat any other hermes command as a task to run
        run_pipeline(command)


def _chatlog_worker() -> None:
    """Background thread for chatlog polling."""
    logger.info("Chatlog worker started (poll interval: %ds)", POLL_INTERVAL)
    while True:
        try:
            _process_chatlog_commands()
        except Exception as exc:
            logger.debug("Chatlog worker error: %s", exc)
        time.sleep(POLL_INTERVAL)


# ══════════════════════════════════════════════════════════════════════════════
# 13. ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import threading

    # Ensure state dirs exist
    (AI_HOME / "state").mkdir(parents=True, exist_ok=True)
    (AI_HOME / "config").mkdir(parents=True, exist_ok=True)

    # Write initial state
    write_state({
        "status": "starting",
        "model": HERMES_MODEL,
        "started": now_iso(),
    })

    print(f"[hermes-agent] Starting on http://{HERMES_HOST}:{HERMES_PORT}")
    print(f"[hermes-agent] Ollama host: {OLLAMA_HOST}  model: {HERMES_MODEL}")
    print(f"[hermes-agent] Fallback model: {HERMES_FALLBACK_MODEL}")
    print(f"[hermes-agent] Max retries: {HERMES_MAX_RETRIES}")
    print(f"[hermes-agent] Dashboard: http://{HERMES_HOST}:{HERMES_PORT}/")
    print(f"[hermes-agent] Skills: {', '.join(SKILLS.keys())}")

    # Start chatlog polling in background
    t = threading.Thread(target=_chatlog_worker, daemon=True)
    t.start()

    if not _FASTAPI_AVAILABLE:
        print("[hermes-agent] ERROR: fastapi/uvicorn not installed. Run: pip install fastapi uvicorn requests")
        sys.exit(1)

    uvicorn.run(app, host=HERMES_HOST, port=HERMES_PORT, log_level="warning")
