"""Follow-up Agent — sends 2–5 personalised follow-ups and adapts tone per reply.

Tracks every lead from the shared CRM and sends a new follow-up message each time
a lead has been silent. Tone shifts automatically: friendly on attempt 1, concise on
attempt 2, value-focused on attempt 3, urgency-light on attempt 4, last-chance on
attempt 5. After 5 attempts the lead is marked 'lost'.

Commands (via chatlog):
  followup run              — process all leads that are due for a follow-up
  followup lead <lead_id>   — force a follow-up for a specific lead
  followup status           — show follow-up stats per lead
  followup reset <lead_id>  — reset follow-up counter for a lead

Config env vars:
  FOLLOWUP_POLL_INTERVAL    — chatlog poll seconds (default: 5)
  FOLLOWUP_WAIT_HOURS       — hours between follow-ups (default: 48)
  FOLLOWUP_MAX_ATTEMPTS     — max follow-up attempts before marking lost (default: 5)
"""
import json
import logging
import os
import re
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

logger = logging.getLogger("follow-up-agent")

AI_HOME = Path(os.environ.get("AI_HOME", str(Path.home() / ".ai-employee")))
STATE_FILE = AI_HOME / "state" / "follow-up-agent.state.json"
CHATLOG    = AI_HOME / "state" / "chatlog.jsonl"
CRM_FILE   = AI_HOME / "state" / "lead-generator-crm.json"

# ── WhatsApp tool (optional) ──────────────────────────────────────────────────

_tools_path = AI_HOME / "agents" / "tools"
if str(_tools_path) not in sys.path:
    sys.path.insert(0, str(_tools_path))
try:
    from whatsapp import send_whatsapp as _send_whatsapp, is_whatsapp_configured as _wa_ok  # type: ignore
    _WHATSAPP_AVAILABLE = _wa_ok()
except ImportError:
    _WHATSAPP_AVAILABLE = False
    def _send_whatsapp(*a, **kw):  # type: ignore
        return False, {"error": "whatsapp not available"}

try:
    from discord_notify import notify_discord as _notify_discord, is_discord_configured as _discord_ok  # type: ignore
    _DISCORD_AVAILABLE = _discord_ok()
except ImportError:
    _DISCORD_AVAILABLE = False
    def _notify_discord(*a, **kw):  # type: ignore
        return False

POLL_INTERVAL  = int(os.environ.get("FOLLOWUP_POLL_INTERVAL", "5"))
WAIT_HOURS     = int(os.environ.get("FOLLOWUP_WAIT_HOURS", "48"))
MAX_ATTEMPTS   = int(os.environ.get("FOLLOWUP_MAX_ATTEMPTS", "5"))

_ai_router_path = AI_HOME / "agents" / "ai-router"
if str(_ai_router_path) not in sys.path:
    sys.path.insert(0, str(_ai_router_path))
try:
    from ai_router import query_ai_for_agent as _query_ai_for_agent  # type: ignore
    _AI_AVAILABLE = True
except ImportError:
    _AI_AVAILABLE = False
    def _query_ai_for_agent(*a, **kw):  # type: ignore
        return {"answer": "[AI unavailable]"}

# ── Memory store (optional) ───────────────────────────────────────────────────

_memory_path = AI_HOME / "agents" / "memory"
if str(_memory_path) not in sys.path:
    sys.path.insert(0, str(_memory_path))
try:
    from memory_store import MemoryStore as _MemoryStore  # type: ignore
    _MEMORY: "_MemoryStore | None" = _MemoryStore()
except ImportError:
    _MEMORY = None

# ── Feedback loop (optional) ──────────────────────────────────────────────────

_feedback_path = AI_HOME / "agents" / "feedback-loop"
if str(_feedback_path) not in sys.path:
    sys.path.insert(0, str(_feedback_path))
try:
    from feedback_loop import record_message as _record_message, get_best_template_as_example as _best_template  # type: ignore
    _FEEDBACK_AVAILABLE = True
except ImportError:
    _FEEDBACK_AVAILABLE = False
    def _record_message(*a, **kw):  # type: ignore
        return ""
    def _best_template(*a, **kw):  # type: ignore
        return ""

# Tone progression: attempt index → (label, system prompt)
_TONE = {
    1: (
        "friendly",
        "Je bent een directe ondernemer, geen AI. "
        "Je schrijft korte berichten die nieuwsgierigheid opwekken. "
        "Je verkoopt niet — je opent gesprekken. "
        "Gebruik max 2 zinnen.",
    ),
    2: (
        "concise",
        "Je bent een drukke ondernemer. "
        "Je stuurt een snelle, menselijke follow-up. "
        "Eén zin. Geen verkooppraatje.",
    ),
    3: (
        "value-focused",
        "Je bent een directe ondernemer. "
        "Benoem één concreet resultaat dat jij levert. "
        "Maximaal 2 zinnen. Geen AI-taal.",
    ),
    4: (
        "light-urgency",
        "Je bent een directe ondernemer. "
        "Geef aan dat je capaciteit bijna vol is. "
        "Kort, eerlijk, geen druk. Max 2 zinnen.",
    ),
    5: (
        "last-chance",
        "Je bent een directe ondernemer. "
        "Dit is je laatste bericht. Laat de deur op een kier. "
        "Één zin, menselijk, geen verwijt.",
    ),
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def write_state(s: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(s, indent=2))


def load_chatlog() -> list:
    if not CHATLOG.exists():
        return []
    try:
        return [json.loads(l) for l in CHATLOG.read_text().splitlines() if l.strip()]
    except Exception:
        return []


def append_chatlog(e: dict) -> None:
    CHATLOG.parent.mkdir(parents=True, exist_ok=True)
    with open(CHATLOG, "a") as f:
        f.write(json.dumps(e) + "\n")


def _ai(prompt: str, system: str = "") -> str:
    if not _AI_AVAILABLE:
        return "[AI unavailable]"
    return (_query_ai_for_agent("follow-up-agent", prompt, system_prompt=system) or {}).get("answer", "")


def load_crm() -> dict:
    if not CRM_FILE.exists():
        return {"items": []}
    try:
        return json.loads(CRM_FILE.read_text())
    except Exception:
        return {"items": []}


def save_crm(crm: dict) -> None:
    CRM_FILE.parent.mkdir(parents=True, exist_ok=True)
    CRM_FILE.write_text(json.dumps(crm, indent=2))


def _attempt_count(lead: dict) -> int:
    """Return how many follow-up messages have been sent for this lead."""
    return sum(1 for m in lead.get("outreach_messages", []) if m.get("channel") == "followup")


def _hours_since(iso_ts: str) -> float:
    try:
        dt = datetime.strptime(iso_ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - dt).total_seconds() / 3600
    except Exception:
        return 0.0


# ── Core ──────────────────────────────────────────────────────────────────────

def _send_followup(lead: dict, crm: dict) -> str:
    """Generate and record a follow-up message for a single lead. Returns result line."""
    attempts = _attempt_count(lead)

    if attempts >= MAX_ATTEMPTS:
        if lead["status"] != "lost":
            lead["status"] = "lost"
            lead["updated_at"] = now_iso()
            save_crm(crm)
        return f"[{lead['id']}] {lead['name']}: max attempts reached → marked lost"

    attempt_no = attempts + 1
    tone_label, system_prompt = _TONE.get(attempt_no, _TONE[5])

    # Build conversation context from memory
    memory_context = ""
    if _MEMORY:
        conv_summary = _MEMORY.get_conversation_summary(f"lead_{lead['id']}")
        if conv_summary and conv_summary != "(no conversation history)":
            memory_context = f"\n\nEerdere gesprekken:\n{conv_summary}"
        facts = _MEMORY.facts_as_context(f"lead_{lead['id']}")
        if facts:
            memory_context += f"\n\n{facts}"

    previous = ""
    if not memory_context and lead.get("outreach_messages"):
        last = lead["outreach_messages"][-1].get("message", "")
        previous = f"\nVorig bericht:\n{last[:300]}"

    # Use best-performing template as hint if available
    best_example = _best_template(niche=lead.get("niche", ""), channel="followup") if _FEEDBACK_AVAILABLE else ""
    example_hint = f"\n\nBest-performing voorbeeld:\n{best_example}" if best_example else ""

    msg = _ai(
        f"Schrijf follow-up #{attempt_no} voor:\n"
        f"Naam: {lead['name']}\nNiche: {lead['niche']}\nLocatie: {lead.get('location', '')}"
        f"{previous}{memory_context}{example_hint}",
        system=system_prompt,
    )

    msg_record: dict = {
        "channel": "followup",
        "attempt": attempt_no,
        "tone": tone_label,
        "message": msg,
        "ts": now_iso(),
        "direction": "outbound",
    }

    # Send via WhatsApp (Twilio) if a valid E.164 phone number is present
    phone = lead.get("phone", "")
    if phone and re.match(r"^\+?[1-9]\d{6,14}$", phone.replace(" ", "")) and _WHATSAPP_AVAILABLE:
        wa_ok, wa_info = _send_whatsapp(to=phone, message=msg)
        if wa_ok:
            msg_record["sent_via"] = "whatsapp"
            msg_record["message_sid"] = wa_info.get("message_sid", "")
        else:
            logger.warning(
                "WhatsApp send failed for lead %s: %s",
                lead["id"], wa_info.get("error", "unknown error"),
            )
            msg_record["send_error"] = wa_info.get("error", "unknown error")

    lead["outreach_messages"].append(msg_record)

    # Register message with feedback loop
    if _FEEDBACK_AVAILABLE:
        _record_message(
            lead_id=lead["id"],
            message=msg,
            niche=lead.get("niche", ""),
            channel="followup",
            tone=tone_label,
        )

    # Store in memory
    if _MEMORY:
        _MEMORY.append_conversation(
            entity_id=f"lead_{lead['id']}",
            role="assistant",
            content=msg,
            entity_type="lead",
        )

    # Do NOT overwrite an advanced pipeline status (qualified, appointment, …).
    # Only bump up if the lead is still in an early/silent stage.
    if lead.get("status") not in ("qualified", "appointment", "replied", "won"):
        lead["status"] = "contacted"
    lead["next_followup"] = (
        datetime.now(timezone.utc) + timedelta(hours=WAIT_HOURS)
    ).strftime("%Y-%m-%dT%H:%M:%SZ")
    lead["updated_at"] = now_iso()
    save_crm(crm)

    return (
        f"[{lead['id']}] {lead['name']} — poging {attempt_no}/{MAX_ATTEMPTS} "
        f"(toon: {tone_label}):\n{msg}"
    )


def run_followups() -> str:
    """Send follow-ups for all leads that are due."""
    crm = load_crm()
    due: list[dict] = []

    for lead in crm["items"]:
        # Only follow up on truly silent leads; skip closed, new, or
        # leads that have already replied or reached the appointment stage.
        if lead.get("status") in ("won", "lost", "new", "replied", "appointment"):
            continue
        # Prefer an explicit next_followup schedule if available; fall back to
        # the legacy updated_at/created_at + WAIT_HOURS logic for compatibility.
        next_followup = lead.get("next_followup")
        if next_followup:
            # _hours_since(next_followup) >= 0 means the scheduled time has passed.
            if _hours_since(next_followup) >= 0:
                due.append(lead)
            continue
        updated = lead.get("updated_at", lead.get("created_at", ""))
        if _hours_since(updated) >= WAIT_HOURS:
            due.append(lead)

    if not due:
        return "Geen leads die nu een follow-up nodig hebben."

    results = []
    for lead in due:
        results.append(_send_followup(lead, crm))

    summary = "\n\n".join(results)
    if results and _DISCORD_AVAILABLE:
        _notify_discord(
            f"📤 **{len(results)} follow-up(s) verstuurd**\n"
            + "\n".join(r.split("\n")[0] for r in results)
        )
    return summary


def followup_lead(lead_id: str) -> str:
    crm = load_crm()
    lead = next((l for l in crm["items"] if l["id"] == lead_id), None)
    if not lead:
        return f"Lead '{lead_id}' niet gevonden."
    return _send_followup(lead, crm)


def followup_status() -> str:
    crm = load_crm()
    lines = ["Follow-up status per lead:"]
    for lead in crm["items"]:
        attempts = _attempt_count(lead)
        lines.append(
            f"  [{lead['id']}] {lead['name']} | status={lead['status']} "
            f"| follow-ups={attempts}/{MAX_ATTEMPTS}"
        )
    return "\n".join(lines) if len(lines) > 1 else "CRM is leeg."


def reset_followup(lead_id: str) -> str:
    crm = load_crm()
    lead = next((l for l in crm["items"] if l["id"] == lead_id), None)
    if not lead:
        return f"Lead '{lead_id}' niet gevonden."
    lead["outreach_messages"] = [
        m for m in lead.get("outreach_messages", []) if m.get("channel") != "followup"
    ]
    lead["next_followup"] = ""
    lead["updated_at"] = now_iso()
    save_crm(crm)
    return f"Follow-up teller gereset voor [{lead_id}] {lead['name']}."


# ── Chatlog processing ────────────────────────────────────────────────────────

def process_chatlog(last_idx: int) -> int:
    chatlog = load_chatlog()
    new_entries = chatlog[last_idx:]
    new_idx = len(chatlog)

    for entry in new_entries:
        if entry.get("type") != "user":
            continue
        msg = entry.get("message", "").strip()
        msg_lower = msg.lower()

        response: str | None = None

        if msg_lower == "followup run":
            response = run_followups()
        elif msg_lower.startswith("followup lead "):
            lead_id = msg[len("followup lead "):].strip()
            response = followup_lead(lead_id) if lead_id else "Gebruik: followup lead <lead_id>"
        elif msg_lower == "followup status":
            response = followup_status()
        elif msg_lower.startswith("followup reset "):
            lead_id = msg[len("followup reset "):].strip()
            response = reset_followup(lead_id) if lead_id else "Gebruik: followup reset <lead_id>"

        if response:
            print(response)
            append_chatlog({
                "type": "bot",
                "bot": "follow-up-agent",
                "message": response,
                "ts": now_iso(),
            })

    return new_idx


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    print(f"[{now_iso()}] follow-up-agent started; poll={POLL_INTERVAL}s "
          f"wait={WAIT_HOURS}h max={MAX_ATTEMPTS}")
    last_idx = len(load_chatlog())
    write_state({"bot": "follow-up-agent", "ts": now_iso(), "status": "starting"})

    while True:
        try:
            last_idx = process_chatlog(last_idx)
            write_state({"bot": "follow-up-agent", "ts": now_iso(), "status": "running"})
        except Exception as exc:
            print(f"[{now_iso()}] ERROR: {exc}")
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
