"""Lead Generator Bot — local business & real estate lead generation + cold outreach CRM.

Scrapes business data via web search, generates personalised cold emails/DMs using AI,
tracks every lead in a JSON CRM, and schedules follow-ups automatically.

Commands (via chatlog):
  leads <niche> <location>         — find 10 leads, generate AI cold email, save to CRM
  leads real-estate <location>     — same but targets makelaars / property agents
  leads status                     — CRM stats (total/contacted/replied/qualified/won)
  leads pipeline                   — list recent leads with current status
  leads followup                   — follow-ups for leads silent for 3+ days
  leads export                     — dump CRM as CSV-like text
  outreach <lead_id> <channel>     — personalised outreach for a specific lead

Config env vars:
  LEAD_GENERATOR_POLL_INTERVAL  — chatlog poll seconds (default: 5)
  LEAD_NICHE                    — default niche
  LEAD_LOCATION                 — default location
  LEAD_DAILY_LIMIT              — max new leads per day (default: 20)
"""
import json
import os
import re
import sys
import time
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path

AI_HOME = Path(os.environ.get("AI_HOME", str(Path.home() / ".ai-employee")))
STATE_FILE = AI_HOME / "state" / "lead-generator.state.json"
CHATLOG    = AI_HOME / "state" / "chatlog.jsonl"
CRM_FILE   = AI_HOME / "state" / "lead-generator-crm.json"

POLL_INTERVAL  = int(os.environ.get("LEAD_GENERATOR_POLL_INTERVAL", "5"))
DAILY_LIMIT    = int(os.environ.get("LEAD_DAILY_LIMIT", "20"))
DEFAULT_NICHE  = os.environ.get("LEAD_NICHE", "")
DEFAULT_LOC    = os.environ.get("LEAD_LOCATION", "")

_ai_router_path = AI_HOME / "bots" / "ai-router"
if str(_ai_router_path) not in sys.path:
    sys.path.insert(0, str(_ai_router_path))
try:
    from ai_router import query_ai as _query_ai, search_web as _search_web  # type: ignore
    _AI_AVAILABLE = True
except ImportError:
    _AI_AVAILABLE = False


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
    return (_query_ai(prompt, system_prompt=system) or {}).get("answer", "")


def _web(query: str) -> str:
    if not _AI_AVAILABLE:
        return "[search unavailable]"
    try:
        results = _search_web(query) or []
        return "\n".join(
            f"{r.get('title','')}: {r.get('url','')}\n{r.get('snippet','')}"
            for r in results[:6]
        )
    except Exception:
        return "[search error]"


# ── CRM ───────────────────────────────────────────────────────────────────────

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


def new_lead(name: str, niche: str, location: str) -> dict:
    return {
        "id": str(uuid.uuid4())[:8],
        "name": name,
        "niche": niche,
        "location": location,
        "website": "",
        "phone": "",
        "email": "",
        "status": "new",
        "outreach_messages": [],
        "notes": "",
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "next_followup": "",
    }


def get_lead_by_id(crm: dict, lead_id: str) -> dict | None:
    for item in crm["items"]:
        if item["id"] == lead_id:
            return item
    return None


# ── Core logic ────────────────────────────────────────────────────────────────

def _crm_stats(crm: dict) -> dict:
    statuses = [i["status"] for i in crm["items"]]
    return {
        "total": len(statuses),
        "new": statuses.count("new"),
        "contacted": statuses.count("contacted"),
        "replied": statuses.count("replied"),
        "qualified": statuses.count("qualified"),
        "appointment": statuses.count("appointment"),
        "won": statuses.count("won"),
        "lost": statuses.count("lost"),
    }


def find_leads(niche: str, location: str, is_real_estate: bool = False) -> str:
    """Search the web for leads and return a summary via chatlog."""
    category = "real estate / makelaars" if is_real_estate else niche
    query = f"{category} {location} contact email phone website"
    raw = _web(query)

    lead_names_text = _ai(
        f"Extract up to 10 distinct business names and any available details "
        f"(website, phone, email) from this search data. Return as a JSON array of objects "
        f'with keys: name, website, phone, email.\n\nSearch data:\n{raw}',
        system="You are a B2B lead generation specialist. Find real local businesses from "
               "web search snippets. Extract only factual data present in the snippets. "
               "Return valid JSON only.",
    )

    try:
        leads_raw = json.loads(re.search(r"\[.*\]", lead_names_text, re.DOTALL).group())
    except Exception:
        leads_raw = [{"name": f"{category} business #{i+1}", "website": "", "phone": "", "email": ""}
                     for i in range(5)]

    crm = load_crm()
    existing_names = {i["name"].lower() for i in crm["items"]}
    added = []

    for biz in leads_raw[:10]:
        name = biz.get("name", "Unknown")
        if name.lower() in existing_names:
            continue

        lead = new_lead(name, category, location)
        lead["website"] = biz.get("website", "")
        lead["phone"]   = biz.get("phone", "")
        lead["email"]   = biz.get("email", "")

        cold_email = _ai(
            f"Write a personalised cold email for this business:\n"
            f"Name: {name}\nNiche: {category}\nLocation: {location}\n"
            f"Website: {lead['website']}",
            system="You are an expert cold email copywriter. Write a personalised, short "
                   "(150 words max), value-focused cold email. Use a compelling subject line. "
                   "Be specific, avoid generic phrases. End with a clear CTA.",
        )
        lead["outreach_messages"].append({"channel": "email", "message": cold_email, "ts": now_iso()})
        lead["status"] = "new"
        lead["updated_at"] = now_iso()

        crm["items"].append(lead)
        existing_names.add(name.lower())
        added.append(f"[{lead['id']}] {name}")

    save_crm(crm)
    return f"Added {len(added)} leads for '{category}' in {location}:\n" + "\n".join(added)


def followup_leads() -> str:
    """Generate follow-up messages for leads silent for 3+ days."""
    crm = load_crm()
    cutoff = datetime.now(timezone.utc) - timedelta(days=3)
    due = []

    for lead in crm["items"]:
        if lead["status"] not in ("contacted", "replied"):
            continue
        updated = lead.get("updated_at", "")
        try:
            updated_dt = datetime.strptime(updated, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        except Exception:
            continue
        if updated_dt < cutoff:
            due.append(lead)

    if not due:
        return "No leads require follow-up right now."

    results = []
    for lead in due[:5]:
        msg = _ai(
            f"Write a brief follow-up for this lead:\n"
            f"Name: {lead['name']}\nNiche: {lead['niche']}\nLast contacted: {lead['updated_at']}",
            system="You are a sales follow-up specialist. Write a brief, non-pushy follow-up "
                   "message (under 80 words). Reference the previous contact naturally.",
        )
        lead["outreach_messages"].append({"channel": "followup", "message": msg, "ts": now_iso()})
        lead["next_followup"] = now_iso()
        lead["updated_at"] = now_iso()
        results.append(f"[{lead['id']}] {lead['name']}: follow-up generated")

    save_crm(crm)
    return "\n".join(results)


def outreach_lead(lead_id: str, channel: str) -> str:
    crm = load_crm()
    lead = get_lead_by_id(crm, lead_id)
    if not lead:
        return f"Lead '{lead_id}' not found."

    channel = channel.lower()
    msg = _ai(
        f"Generate a personalised {channel} outreach message for:\n"
        f"Name: {lead['name']}\nNiche: {lead['niche']}\nLocation: {lead['location']}\n"
        f"Website: {lead['website']}",
        system="You are an expert cold email copywriter. Write a personalised, short "
               "(150 words max), value-focused outreach message tailored to the channel. "
               "Be specific and end with a clear CTA.",
    )
    lead["outreach_messages"].append({"channel": channel, "message": msg, "ts": now_iso()})
    lead["status"] = "contacted"
    lead["updated_at"] = now_iso()
    save_crm(crm)
    return f"Outreach for [{lead_id}] {lead['name']} via {channel}:\n\n{msg}"


def pipeline_summary() -> str:
    crm = load_crm()
    if not crm["items"]:
        return "CRM is empty. Use 'leads <niche> <location>' to generate leads."
    recent = sorted(crm["items"], key=lambda x: x.get("updated_at", ""), reverse=True)[:10]
    lines = ["Recent leads:"]
    for lead in recent:
        lines.append(f"  [{lead['id']}] {lead['name']} | {lead['niche']} | {lead['location']} | {lead['status']}")
    return "\n".join(lines)


def export_crm() -> str:
    crm = load_crm()
    if not crm["items"]:
        return "CRM is empty."
    header = "id,name,niche,location,website,phone,email,status,created_at"
    rows = [header]
    for lead in crm["items"]:
        rows.append(
            f"{lead['id']},{lead['name']},{lead['niche']},{lead['location']},"
            f"{lead['website']},{lead['phone']},{lead['email']},"
            f"{lead['status']},{lead['created_at']}"
        )
    return "\n".join(rows)


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

        if msg_lower.startswith("leads real-estate "):
            location = msg[len("leads real-estate "):].strip()
            result = find_leads("real estate", location, is_real_estate=True)
            append_chatlog({"type": "bot", "bot": "lead-generator", "message": result, "ts": now_iso()})

        elif msg_lower.startswith("leads status"):
            crm = load_crm()
            stats = _crm_stats(crm)
            result = (
                f"CRM Stats: total={stats['total']} new={stats['new']} "
                f"contacted={stats['contacted']} replied={stats['replied']} "
                f"qualified={stats['qualified']} won={stats['won']} lost={stats['lost']}"
            )
            append_chatlog({"type": "bot", "bot": "lead-generator", "message": result, "ts": now_iso()})

        elif msg_lower.startswith("leads pipeline"):
            result = pipeline_summary()
            append_chatlog({"type": "bot", "bot": "lead-generator", "message": result, "ts": now_iso()})

        elif msg_lower.startswith("leads followup"):
            result = followup_leads()
            append_chatlog({"type": "bot", "bot": "lead-generator", "message": result, "ts": now_iso()})

        elif msg_lower.startswith("leads export"):
            result = export_crm()
            append_chatlog({"type": "bot", "bot": "lead-generator", "message": result, "ts": now_iso()})

        elif msg_lower.startswith("leads "):
            parts = msg[len("leads "):].strip().split(maxsplit=1)
            if len(parts) == 2:
                niche, location = parts
            elif len(parts) == 1:
                niche, location = parts[0], DEFAULT_LOC or "Netherlands"
            else:
                niche, location = DEFAULT_NICHE or "businesses", DEFAULT_LOC or "Netherlands"
            result = find_leads(niche, location)
            append_chatlog({"type": "bot", "bot": "lead-generator", "message": result, "ts": now_iso()})

        elif msg_lower.startswith("outreach "):
            parts = msg[len("outreach "):].strip().split(maxsplit=1)
            if len(parts) == 2:
                lead_id, channel = parts
            elif len(parts) == 1:
                lead_id, channel = parts[0], "email"
            else:
                continue
            result = outreach_lead(lead_id, channel)
            append_chatlog({"type": "bot", "bot": "lead-generator", "message": result, "ts": now_iso()})

    return new_idx


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    print(f"[{now_iso()}] lead-generator started")
    last_idx = len(load_chatlog())
    crm = load_crm()
    write_state({"bot": "lead-generator", "ts": now_iso(), "status": "starting",
                 "total_leads": len(crm["items"])})

    while True:
        try:
            last_idx = process_chatlog(last_idx)
            crm = load_crm()
            write_state({
                "bot": "lead-generator",
                "ts": now_iso(),
                "status": "running",
                "total_leads": len(crm["items"]),
                "stats": _crm_stats(crm),
            })
        except Exception as exc:
            print(f"[{now_iso()}] ERROR: {exc}")
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
