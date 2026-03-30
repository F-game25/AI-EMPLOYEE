"""Outreach Agent — personalized message generation for lead outreach.

Generates highly personalized cold outreach messages using:
  - NVIDIA Nemotron for persuasive, reasoning-heavy copy
  - Per-lead memory (MemoryStore) for context awareness
  - Multi-channel templates: email, WhatsApp, LinkedIn
  - Feedback loop integration (picks best-performing templates)

Commands:
  draft <lead_id> [channel]   — draft an outreach message for a lead
  batch <niche> [channel]     — draft messages for all leads in a niche
  template list               — list available templates
  template set <channel> <text> — set/update a template
  status                      — show outreach stats

Channels: email (default), whatsapp, linkedin

State files:
  ~/.ai-employee/state/outreach-agent.state.json
  ~/.ai-employee/state/leads-crm.json  (shared)
"""
from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

AI_HOME = Path(os.environ.get("AI_HOME", str(Path.home() / ".ai-employee")))
STATE_FILE = AI_HOME / "state" / "outreach-agent.state.json"
CRM_FILE = AI_HOME / "state" / "leads-crm.json"
CHATLOG = AI_HOME / "state" / "chatlog.jsonl"
AGENT_TASKS_DIR = AI_HOME / "state" / "agent_tasks"
RESULTS_DIR = AI_HOME / "state" / "orchestrator_results"

POLL_INTERVAL = int(os.environ.get("OUTREACH_POLL_INTERVAL", "5"))
SENDER_NAME = os.environ.get("OUTREACH_SENDER_NAME", "Alex")
SENDER_COMPANY = os.environ.get("OUTREACH_SENDER_COMPANY", "AI Employee")
SENDER_VALUE_PROP = os.environ.get(
    "OUTREACH_VALUE_PROP",
    "We help businesses automate their lead generation and outreach with AI",
)

logging.basicConfig(
    level=getattr(logging, os.environ.get("LOG_LEVEL", "WARNING").upper(), logging.WARNING),
    format="%(message)s",
)
logger = logging.getLogger("outreach-agent")

# ── Dependency imports ────────────────────────────────────────────────────────

_nim_path = AI_HOME / "bots" / "nvidia-nim"
_memory_path = AI_HOME / "bots" / "memory"
_ai_router_path = AI_HOME / "bots" / "ai-router"

for _p in [_nim_path, _memory_path, _ai_router_path]:
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

try:
    from nim_client import NIMClient  # type: ignore
    _nim = NIMClient()
    _NIM_AVAILABLE = _nim.is_available()
except ImportError:
    _nim = None
    _NIM_AVAILABLE = False

try:
    from ai_router import query_ai_for_agent  # type: ignore
    _ROUTER_AVAILABLE = True
except ImportError:
    _ROUTER_AVAILABLE = False

try:
    from memory_store import MemoryStore  # type: ignore
    _mem = MemoryStore()
    _MEM_AVAILABLE = True
except ImportError:
    _mem = None
    _MEM_AVAILABLE = False


# ── Helpers ───────────────────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {"drafted": 0, "templates": {}, "last_run": None}


def _save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


def _load_crm() -> list:
    if not CRM_FILE.exists():
        return []
    try:
        return json.loads(CRM_FILE.read_text())
    except Exception:
        return []


def _save_crm(leads: list) -> None:
    CRM_FILE.parent.mkdir(parents=True, exist_ok=True)
    CRM_FILE.write_text(json.dumps(leads, indent=2))


def _query_ai(prompt: str, system: str = "") -> str:
    """Use NVIDIA Nemotron for persuasive outreach copy; fall back to ai_router."""
    if _NIM_AVAILABLE:
        result = _nim.chat(
            prompt,
            system_prompt=system,
            temperature=0.85,  # slightly higher for more creative copy
        )
        if result.get("answer"):
            return result["answer"]
    if _ROUTER_AVAILABLE:
        result = query_ai_for_agent("outreach-agent", prompt, system_prompt=system)
        return result.get("answer", "")
    return ""


# ── Default templates ─────────────────────────────────────────────────────────

_DEFAULT_TEMPLATES: dict[str, str] = {
    "email": (
        "Subject: Quick question about {company}\n\n"
        "Hi {first_name},\n\n"
        "I came across {company} and was impressed by your work in {industry}.\n\n"
        "{value_prop}\n\n"
        "Would you be open to a quick 15-minute call this week to explore if there's a fit?\n\n"
        "Best,\n{sender_name}"
    ),
    "whatsapp": (
        "Hi {first_name} 👋\n\n"
        "Saw {company} is doing great work in {industry}.\n\n"
        "{value_prop}\n\n"
        "Open to a quick chat? 🤙"
    ),
    "linkedin": (
        "Hi {first_name},\n\n"
        "Your work at {company} in {industry} caught my attention. "
        "{value_prop} — thought it might be relevant to you.\n\n"
        "Would love to connect and share some ideas. Open to it?"
    ),
}


def _get_template(channel: str, state: dict) -> str:
    """Return the template for the given channel."""
    return state.get("templates", {}).get(channel) or _DEFAULT_TEMPLATES.get(channel, "")


# ── Message generation ────────────────────────────────────────────────────────

def draft_message(lead: dict, channel: str = "email") -> str:
    """Generate a personalized outreach message for a lead.

    Two-step process:
      1. Fill the template with lead data (fast, deterministic)
      2. AI refinement pass — personalize with lead context (optional)

    Args:
        lead:    Lead dict (from CRM).
        channel: "email" | "whatsapp" | "linkedin".

    Returns:
        Personalized message string.
    """
    state = _load_state()
    template = _get_template(channel, state)

    # Build template variables
    name = lead.get("name", "")
    parts = name.split()
    first_name = parts[0] if parts else "there"
    company = name or "your company"
    industry = lead.get("industry", "your industry")

    # Get memory context if available
    memory_context = ""
    if _MEM_AVAILABLE:
        facts = _mem.get_facts(lead.get("id", ""))
        if facts:
            memory_context = "\n".join(
                f"- {f.get('key')}: {f.get('value')}" for f in facts[:5]
            )

    # Fill template
    base_message = template.format(
        first_name=first_name,
        company=company,
        industry=industry,
        value_prop=SENDER_VALUE_PROP,
        sender_name=SENDER_NAME,
        sender_company=SENDER_COMPANY,
    )

    # AI refinement pass
    if _NIM_AVAILABLE or _ROUTER_AVAILABLE:
        lead_summary = (
            f"Company: {company}\n"
            f"Industry: {industry}\n"
            f"Description: {lead.get('description', 'N/A')[:200]}\n"
            f"Location: {lead.get('location', 'N/A')}"
        )
        if memory_context:
            lead_summary += f"\nKnown facts:\n{memory_context}"
        prompt = (
            f"Refine and personalize this {channel} outreach message for:\n\n"
            f"{lead_summary}\n\n"
            f"Base message:\n{base_message}\n\n"
            f"Make it feel genuine and specific. Keep the same channel format and length. "
            f"Do NOT use generic phrases like 'I hope this email finds you well'. "
            f"Return ONLY the refined message."
        )
        refined = _query_ai(
            prompt,
            system=(
                "You are an expert B2B sales copywriter. Write authentic, "
                "personalized outreach that doesn't feel like spam. "
                "Be concise, specific, and lead with value."
            ),
        )
        if refined.strip():
            return refined.strip()

    return base_message


def draft_batch(niche: str, channel: str = "email", limit: int = 5) -> list[dict]:
    """Draft messages for all CRM leads matching the given niche.

    Args:
        niche:   Industry/niche filter.
        channel: Outreach channel.
        limit:   Max leads to process.

    Returns:
        List of {lead_id, name, channel, message} dicts.
    """
    crm = _load_crm()
    matches = [
        l for l in crm
        if niche.lower() in l.get("industry", "").lower()
        or niche.lower() in l.get("description", "").lower()
    ][:limit]

    results = []
    state = _load_state()
    for lead in matches:
        msg = draft_message(lead, channel)
        results.append({
            "lead_id": lead.get("id", ""),
            "name": lead.get("name", ""),
            "channel": channel,
            "message": msg,
            "drafted_at": _now_iso(),
        })
        # Track in memory
        if _MEM_AVAILABLE:
            _mem.remember(
                lead.get("id", ""),
                f"outreach_{channel}",
                msg[:200],
                entity_type="lead",
            )
        state["drafted"] = state.get("drafted", 0) + 1

    state["last_run"] = _now_iso()
    _save_state(state)
    return results


# ── Commands ──────────────────────────────────────────────────────────────────

def handle_command(cmd: str) -> str:
    cmd = cmd.strip()
    lower = cmd.lower()

    if lower.startswith("draft "):
        parts = cmd[6:].split(maxsplit=1)
        lead_id = parts[0]
        channel = parts[1].strip() if len(parts) > 1 else "email"
        channel = channel.lower()
        if channel not in ("email", "whatsapp", "linkedin"):
            channel = "email"

        crm = _load_crm()
        lead = next((l for l in crm if l.get("id") == lead_id), None)
        if not lead:
            return f"❌ Lead not found: {lead_id}"

        msg = draft_message(lead, channel)
        state = _load_state()
        state["drafted"] = state.get("drafted", 0) + 1
        state["last_run"] = _now_iso()
        _save_state(state)
        return f"✉️ {channel.capitalize()} draft for {lead.get('name', lead_id)}:\n\n{msg}"

    if lower.startswith("batch "):
        parts = cmd[6:].split(maxsplit=1)
        niche = parts[0]
        channel = parts[1].strip().lower() if len(parts) > 1 else "email"
        results = draft_batch(niche, channel)
        if not results:
            return f"📭 No leads found for niche: {niche}"
        lines = [f"✉️ Drafted {len(results)} {channel} messages for niche '{niche}':"]
        for r in results:
            lines.append(f"\n── {r['name']} ──\n{r['message'][:300]}…")
        return "\n".join(lines)

    if lower == "template list":
        state = _load_state()
        channels = list(_DEFAULT_TEMPLATES.keys())
        custom = list(state.get("templates", {}).keys())
        return (
            f"📋 Available templates:\n"
            f"  Default: {', '.join(channels)}\n"
            f"  Custom:  {', '.join(custom) if custom else 'none'}"
        )

    if lower.startswith("template set "):
        rest = cmd[13:].strip()
        parts = rest.split(maxsplit=1)
        if len(parts) < 2:
            return "❌ Usage: template set <channel> <template_text>"
        channel, text = parts[0].lower(), parts[1]
        state = _load_state()
        state.setdefault("templates", {})[channel] = text
        _save_state(state)
        return f"✅ Template updated for channel: {channel}"

    if lower == "status":
        state = _load_state()
        return (
            f"📊 Outreach Agent Status\n"
            f"Messages drafted: {state.get('drafted', 0)}\n"
            f"Custom templates: {len(state.get('templates', {}))}\n"
            f"Sender: {SENDER_NAME} @ {SENDER_COMPANY}\n"
            f"Last run: {state.get('last_run', 'never')}"
        )

    return (
        f"❓ Unknown command: {cmd}\n"
        "Usage: draft <lead_id> [channel] | batch <niche> [channel] | "
        "template list | template set <channel> <text> | status"
    )


# ── Main polling loop ─────────────────────────────────────────────────────────

def main() -> None:
    import time

    logger.info("outreach-agent: starting")
    AGENT_TASKS_DIR.mkdir(parents=True, exist_ok=True)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    while True:
        for task_file in sorted(AGENT_TASKS_DIR.glob("outreach-agent_*.json")):
            try:
                task = json.loads(task_file.read_text())
                result = handle_command(task.get("command", ""))
                result_file = RESULTS_DIR / f"{task_file.stem}.result.json"
                result_file.write_text(json.dumps({"result": result, "ts": _now_iso()}))
                task_file.unlink()
            except Exception as exc:
                logger.warning("outreach-agent: task error — %s", exc)
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
