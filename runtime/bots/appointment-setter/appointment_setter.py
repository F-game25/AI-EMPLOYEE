"""Appointment Setter Bot — automated sales funnel orchestrator.

Orchestrates the full sales funnel: prospect discovery → cold outreach →
follow-up → WhatsApp close → calendar booking. Posts research requests to
web-researcher, generates outreach sequences, and manages pipeline state.

Commands:
  prospect <niche> <location>  — discover prospects for a niche/location
  outreach <campaign_name>     — generate a full 5-touch outreach campaign
  pipeline                     — show full sales pipeline with stage counts
  setter followup              — generate follow-up messages for stale prospects
  book <prospect_id> <date>    — generate appointment confirmation message
  setter status                — pipeline stats, conversion rates, revenue
  setter scripts               — generate objection handling + closing lines
"""
import json, os, re, sys, time, uuid
from datetime import datetime, timezone
from pathlib import Path

AI_HOME      = Path(os.environ.get("AI_HOME", str(Path.home() / ".ai-employee")))
STATE_FILE   = AI_HOME / "state" / "appointment-setter.state.json"
PIPELINE_FILE = AI_HOME / "state" / "appointment-setter-pipeline.json"
CHATLOG      = AI_HOME / "state" / "chatlog.jsonl"

POLL_INTERVAL       = int(os.environ.get("APPOINTMENT_SETTER_POLL_INTERVAL", "5"))
SETTER_NICHE        = os.environ.get("SETTER_NICHE", "")
VALUE_PER_CLIENT    = float(os.environ.get("SETTER_VALUE_PER_CLIENT", "1000"))
DAILY_OUTREACH_LIMIT = int(os.environ.get("SETTER_DAILY_OUTREACH_LIMIT", "20"))

STAGES = ["prospect", "contacted", "replied", "qualified", "appointment", "closed"]

_ai_router_path = AI_HOME / "bots" / "ai-router"
if str(_ai_router_path) not in sys.path:
    sys.path.insert(0, str(_ai_router_path))
try:
    from ai_router import query_ai as _query_ai, search_web as _search_web  # type: ignore
    _AI_AVAILABLE = True
except ImportError:
    _AI_AVAILABLE = False


# ── helpers ───────────────────────────────────────────────────────────────────

def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def write_state(s):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(s, indent=2))

def load_chatlog():
    if not CHATLOG.exists():
        return []
    try:
        return [json.loads(l) for l in CHATLOG.read_text().splitlines() if l.strip()]
    except Exception:
        return []

def append_chatlog(e):
    CHATLOG.parent.mkdir(parents=True, exist_ok=True)
    with open(CHATLOG, "a") as f:
        f.write(json.dumps(e) + "\n")

def _ai(prompt: str, system: str = "") -> str:
    if not _AI_AVAILABLE:
        return "[AI unavailable — install deps]"
    return (_query_ai(prompt, system_prompt=system) or {}).get("answer", "")

def load_pipeline() -> list[dict]:
    if not PIPELINE_FILE.exists():
        return []
    try:
        data = json.loads(PIPELINE_FILE.read_text())
        return data if isinstance(data, list) else []
    except Exception:
        return []

def save_pipeline(pipeline: list[dict]):
    PIPELINE_FILE.parent.mkdir(parents=True, exist_ok=True)
    PIPELINE_FILE.write_text(json.dumps(pipeline, indent=2))

def make_prospect(name: str, niche: str, contact: str = "", value_estimate: float = 0) -> dict:
    return {
        "id": str(uuid.uuid4())[:8],
        "name": name,
        "niche": niche,
        "contact": contact,
        "stage": "prospect",
        "outreach_sequence": [],
        "appointment_time": "",
        "value_estimate": value_estimate or VALUE_PER_CLIENT,
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }

def update_prospect(pipeline: list[dict], prospect_id: str, **kwargs) -> bool:
    for p in pipeline:
        if p["id"] == prospect_id:
            p.update(kwargs)
            p["updated_at"] = now_iso()
            return True
    return False

def hours_since(iso_ts: str) -> float:
    try:
        dt = datetime.strptime(iso_ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - dt).total_seconds() / 3600
    except Exception:
        return 0.0


# ── command handlers ──────────────────────────────────────────────────────────

def cmd_prospect(niche: str, location: str) -> str:
    prompt = (
        f"Generate 10 realistic prospect profiles for a sales pipeline targeting '{niche}' businesses "
        f"in {location}. For each prospect include: business name, owner name, estimated annual revenue, "
        f"primary pain point, best contact method (email/LinkedIn/phone), and a 1-sentence hook. "
        f"Format as a numbered list."
    )
    ai_profiles = _ai(prompt, system="You are a B2B sales prospecting expert.")

    # Parse AI output into structured prospects
    pipeline = load_pipeline()
    new_prospects: list[dict] = []
    for i, line in enumerate(ai_profiles.split("\n"), 1):
        line = line.strip()
        if not line or not re.match(r"^\d+[\.\)]", line):
            continue
        # Extract business name (first quoted or capitalized noun phrase)
        name_match = re.search(r'"([^"]+)"', line) or re.search(r"\d+[\.\)]\s+([A-Z][^\,\.]+)", line)
        name = name_match.group(1).strip() if name_match else f"Prospect {i} ({niche})"
        p = make_prospect(name=name, niche=niche, contact=location)
        new_prospects.append(p)
        if len(new_prospects) >= 10:
            break

    pipeline.extend(new_prospects)
    save_pipeline(pipeline)

    lines = [f"[{now_iso()}] Discovered {len(new_prospects)} prospects for '{niche}' in {location}:\n"]
    for p in new_prospects:
        lines.append(f"  [{p['id']}] {p['name']} | stage=prospect | value=€{p['value_estimate']:.0f}")
    lines.append(f"\nFull AI profiles:\n{ai_profiles}")
    return "\n".join(lines)

def cmd_outreach(campaign_name: str) -> str:
    pipeline = load_pipeline()
    prospect_list = pipeline[:3]  # first 3 uncontacted prospects as context
    names = [p["name"] for p in prospect_list] or ["Example Business"]
    niche = prospect_list[0]["niche"] if prospect_list else SETTER_NICHE or "general business"

    prompt = (
        f"Generate a complete 5-touch outreach campaign named '{campaign_name}' for {niche} businesses.\n"
        f"Touch 1 (Day 1): Cold email subject + body (150 words)\n"
        f"Touch 2 (Day 3): Follow-up email (100 words)\n"
        f"Touch 3 (Day 7): LinkedIn connection request note (300 chars)\n"
        f"Touch 4 (Day 10): WhatsApp opening message (2 sentences)\n"
        f"Touch 5 (Day 14): Final closing email with clear CTA (120 words)\n\n"
        f"Target: {niche} business owners. Value prop: ROI-focused, solve their top pain point.\n"
        f"Sample prospect names for personalisation: {', '.join(names[:3])}"
    )
    sequence = _ai(prompt, system="You are a top B2B sales copywriter specialising in cold outreach.")

    # Save campaign to pipeline prospects in 'prospect' stage
    for p in pipeline:
        if p["stage"] == "prospect":
            p["outreach_sequence"] = [{"campaign": campaign_name, "sequence": sequence, "sent_at": None}]
            p["stage"] = "contacted"
            p["updated_at"] = now_iso()

    save_pipeline(pipeline)

    daily = min(len([p for p in pipeline if p["stage"] == "contacted"]), DAILY_OUTREACH_LIMIT)
    return (
        f"[{now_iso()}] Campaign '{campaign_name}' generated. "
        f"Marked {daily} prospects as 'contacted'.\n\n{sequence}"
    )

def cmd_pipeline() -> str:
    pipeline = load_pipeline()
    stage_counts: dict[str, int] = {s: 0 for s in STAGES}
    for p in pipeline:
        stage = p.get("stage", "prospect")
        stage_counts[stage] = stage_counts.get(stage, 0) + 1

    total_pipeline_value = sum(
        p.get("value_estimate", 0) for p in pipeline if p["stage"] == "closed"
    )
    total_expected = sum(
        p.get("value_estimate", 0) * {"prospect": 0.05, "contacted": 0.1, "replied": 0.25,
                                       "qualified": 0.5, "appointment": 0.75, "closed": 1.0
                                       }.get(p["stage"], 0)
        for p in pipeline
    )

    lines = [f"[{now_iso()}] Sales Pipeline — {len(pipeline)} total prospects\n"]
    funnel_icons = {"prospect": "🔍", "contacted": "📧", "replied": "💬",
                    "qualified": "✅", "appointment": "📅", "closed": "💰"}
    for stage in STAGES:
        count = stage_counts.get(stage, 0)
        icon = funnel_icons.get(stage, "•")
        lines.append(f"  {icon} {stage.capitalize():12s}: {count:3d} prospects")

    lines.append(f"\n  💰 Closed revenue    : €{total_pipeline_value:,.0f}")
    lines.append(f"  📈 Expected pipeline : €{total_expected:,.0f}")
    lines.append(f"  🎯 Daily limit       : {DAILY_OUTREACH_LIMIT} outreaches")

    # Show recent appointments
    appointments = [p for p in pipeline if p["stage"] in ("appointment", "closed")]
    if appointments:
        lines.append("\n  Recent appointments:")
        for p in appointments[-5:]:
            lines.append(f"    [{p['id']}] {p['name']} | {p['stage']} | {p.get('appointment_time', 'TBD')}")

    return "\n".join(lines)

def cmd_setter_followup() -> str:
    pipeline = load_pipeline()
    stale: list[dict] = []
    for p in pipeline:
        if p["stage"] == "contacted":
            hours = hours_since(p.get("updated_at", p.get("created_at", now_iso())))
            if hours >= 48:
                stale.append(p)

    if not stale:
        return f"[{now_iso()}] No stale prospects (all contacted within 48h)."

    prompt = (
        f"Generate follow-up messages for {len(stale)} stale sales prospects who haven't replied in 48+ hours.\n"
        f"For each, generate:\n"
        f"1. Short follow-up email (80 words)\n"
        f"2. WhatsApp follow-up message (1-2 sentences)\n\n"
        f"Prospects: {', '.join(p['name'] + ' (' + p['niche'] + ')' for p in stale[:5])}\n"
        f"Tone: friendly, value-focused, no pressure."
    )
    follow_ups = _ai(prompt, system="You are a sales follow-up specialist.")

    # Mark as still contacted, refresh timestamp
    for p in stale:
        p["updated_at"] = now_iso()
    save_pipeline(pipeline)

    return (
        f"[{now_iso()}] Generated follow-ups for {len(stale)} stale prospects:\n\n{follow_ups}"
    )

def cmd_book(prospect_id: str, date_hint: str) -> str:
    pipeline = load_pipeline()
    prospect = next((p for p in pipeline if p["id"] == prospect_id), None)
    if not prospect:
        return f"[{now_iso()}] Prospect '{prospect_id}' not found. Use 'pipeline' to list IDs."

    prompt = (
        f"Generate an appointment confirmation message and calendar invite text for:\n"
        f"Name: {prospect['name']}\n"
        f"Niche: {prospect['niche']}\n"
        f"Requested time: {date_hint}\n\n"
        f"Include:\n"
        f"1. Confirmation WhatsApp/email message (friendly, professional)\n"
        f"2. Calendar invite title, description (agenda: intro 5min, pain points 15min, solution 20min, close 10min)\n"
        f"3. Reminder to send 24h before"
    )
    booking_msg = _ai(prompt, system="You are an expert appointment setter.")

    update_prospect(pipeline, prospect_id, stage="appointment",
                    appointment_time=date_hint, outreach_sequence=prospect.get("outreach_sequence", []))
    save_pipeline(pipeline)

    return (
        f"[{now_iso()}] Appointment booked for [{prospect_id}] {prospect['name']} at '{date_hint}':\n\n"
        f"{booking_msg}"
    )

def cmd_setter_status() -> str:
    pipeline = load_pipeline()
    closed = [p for p in pipeline if p["stage"] == "closed"]
    appointments = [p for p in pipeline if p["stage"] == "appointment"]
    contacted = [p for p in pipeline if p["stage"] == "contacted"]
    revenue = sum(p.get("value_estimate", 0) for p in closed)
    conversion = (len(closed) / len(pipeline) * 100) if pipeline else 0

    lines = [
        f"[{now_iso()}] Appointment Setter Status",
        f"  Niche            : {SETTER_NICHE or 'not set (use prospect <niche> <location>)'}",
        f"  Value per client : €{VALUE_PER_CLIENT:,.0f}",
        f"  Daily limit      : {DAILY_OUTREACH_LIMIT}",
        f"  Total prospects  : {len(pipeline)}",
        f"  In outreach      : {len(contacted)}",
        f"  Appointments     : {len(appointments)}",
        f"  Closed deals     : {len(closed)}",
        f"  Conversion rate  : {conversion:.1f}%",
        f"  Closed revenue   : €{revenue:,.0f}",
        f"  Pipeline value   : €{len(appointments) * VALUE_PER_CLIENT:,.0f} (appointments)",
    ]
    return "\n".join(lines)

def cmd_setter_scripts() -> str:
    niche = SETTER_NICHE or "general business"
    prompt = (
        f"Generate a complete sales script kit for closing {niche} clients. Include:\n\n"
        f"1. TOP 5 OBJECTIONS & RESPONSES\n"
        f"   Format each as: Objection → Response (2-3 sentences)\n\n"
        f"2. CLOSING LINES (5 variations)\n"
        f"   Soft close, assumptive close, urgency close, ROI close, question close\n\n"
        f"3. WHATSAPP CLOSING SEQUENCE (3 messages)\n"
        f"   Open, follow-up, final push\n\n"
        f"4. PRICE HANDLING (when they say it's too expensive)\n"
        f"   3-step reframe script\n"
    )
    scripts = _ai(prompt, system="You are a world-class sales closer who trains appointment setters.")
    return f"[{now_iso()}] Sales scripts for '{niche}':\n\n{scripts}"


# ── chatlog processor ─────────────────────────────────────────────────────────

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

        if msg_lower.startswith("prospect "):
            parts = msg.split(maxsplit=2)
            if len(parts) >= 3:
                response = cmd_prospect(parts[1], parts[2])
            else:
                response = "Usage: prospect <niche> <location>"
        elif msg_lower.startswith("outreach "):
            campaign = msg[len("outreach "):].strip()
            response = cmd_outreach(campaign) if campaign else "Usage: outreach <campaign_name>"
        elif msg_lower == "pipeline":
            response = cmd_pipeline()
        elif msg_lower == "setter followup":
            response = cmd_setter_followup()
        elif msg_lower.startswith("book "):
            parts = msg.split(maxsplit=2)
            if len(parts) >= 3:
                response = cmd_book(parts[1], parts[2])
            else:
                response = "Usage: book <prospect_id> <date_hint>"
        elif msg_lower == "setter status":
            response = cmd_setter_status()
        elif msg_lower == "setter scripts":
            response = cmd_setter_scripts()

        if response:
            print(response)
            append_chatlog({"type": "bot", "bot": "appointment-setter", "message": response, "ts": now_iso()})

    return new_idx


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    print(f"[{now_iso()}] appointment-setter started; poll={POLL_INTERVAL}s")
    last_idx = len(load_chatlog())
    write_state({"bot": "appointment-setter", "ts": now_iso(), "status": "starting"})
    while True:
        try:
            new_idx = process_chatlog(last_idx)
            last_idx = new_idx
        except Exception as exc:
            print(f"[{now_iso()}] appointment-setter error: {exc}")
        write_state({"bot": "appointment-setter", "ts": now_iso(), "status": "running"})
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
