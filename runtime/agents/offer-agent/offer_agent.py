"""Offer Agent — crafts a personalised pitch per niche.

Takes a qualified lead from the CRM and generates a bespoke offer:
  • Adapts the value proposition to the lead's specific niche
  • Writes a short, human, result-focused pitch (no AI-speak)
  • Produces a WhatsApp-ready message + email version
  • Optionally includes a pricing anchor based on the niche

Commands (via chatlog):
  offer lead <lead_id>              — generate a personalised offer for a lead
  offer niche <niche> <pain_point>  — draft a niche-specific pitch template
  offer all                         — generate offers for all qualified leads
  offer list                        — list leads with their generated offers

Config env vars:
  OFFER_POLL_INTERVAL   — chatlog poll seconds (default: 5)
  OFFER_SERVICE         — your service/product name (default: '')
  OFFER_PRICE_LOW       — low price anchor in euros (default: 500)
  OFFER_PRICE_HIGH      — high price anchor in euros (default: 2500)
"""
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

AI_HOME = Path(os.environ.get("AI_HOME", str(Path.home() / ".ai-employee")))
STATE_FILE = AI_HOME / "state" / "offer-agent.state.json"
CHATLOG    = AI_HOME / "state" / "chatlog.jsonl"
CRM_FILE   = AI_HOME / "state" / "lead-generator-crm.json"

POLL_INTERVAL = int(os.environ.get("OFFER_POLL_INTERVAL", "5"))
SERVICE_NAME  = os.environ.get("OFFER_SERVICE", "")
PRICE_LOW     = int(os.environ.get("OFFER_PRICE_LOW", "500"))
PRICE_HIGH    = int(os.environ.get("OFFER_PRICE_HIGH", "2500"))

_ai_router_path = AI_HOME / "agents" / "ai-router"
if str(_ai_router_path) not in sys.path:
    sys.path.insert(0, str(_ai_router_path))
try:
    from ai_router import query_ai_for_agent as _query_ai_for_agent  # type: ignore
    _AI_AVAILABLE = True
except ImportError:
    _AI_AVAILABLE = False

# System prompt used for ALL offer generation — short, human, result-focused
_OFFER_SYSTEM = (
    "Je bent een directe ondernemer, geen AI. "
    "Je schrijft korte berichten die nieuwsgierigheid opwekken. "
    "Je verkoopt niet — je opent gesprekken. "
    "Wees specifiek over het resultaat. Geen buzzwords. Geen AI-praat. "
    "Maximaal 2 zinnen voor de WhatsApp-versie en maximaal 3 zinnen voor de e-mailversie."
)

_NICHE_SYSTEM = (
    "Je bent een directe sales-professional. "
    "Je kent elke niche van binnen en buiten. "
    "Schrijf een pitch-template die direct raakt aan het pijnpunt. "
    "Kort, menselijk, resultaatgericht. Geen AI-taal."
)


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
    return (_query_ai_for_agent("offer-agent", prompt, system_prompt=system) or {}).get("answer", "")


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


# ── Core ──────────────────────────────────────────────────────────────────────

def _build_offer_prompt(lead: dict) -> str:
    service = SERVICE_NAME or "onze dienst"
    pain_hint = lead.get("qualification", {}).get("reason", "")
    return (
        f"Genereer een gepersonaliseerd aanbod voor:\n"
        f"Naam: {lead['name']}\n"
        f"Niche: {lead.get('niche', '')}\n"
        f"Locatie: {lead.get('location', '')}\n"
        f"Website: {lead.get('website', '')}\n"
        f"Dienst/product: {service}\n"
        f"Pijnpunt (uit kwalificatie): {pain_hint}\n"
        f"Prijsrange: €{PRICE_LOW}–€{PRICE_HIGH}\n\n"
        f"Geef terug:\n"
        f"1. WhatsApp-versie (max 2 zinnen)\n"
        f"2. E-mail-versie (max 3 zinnen + onderwerpregel)\n"
        f"3. Eén concrete resultaatbelofte voor deze niche"
    )


def generate_offer(lead: dict, crm: dict) -> str:
    prompt = _build_offer_prompt(lead)
    offer_text = _ai(prompt, system=_OFFER_SYSTEM)

    lead.setdefault("offers", [])
    lead["offers"].append({"offer": offer_text, "ts": now_iso()})
    lead["updated_at"] = now_iso()
    save_crm(crm)

    return (
        f"💼 Aanbod voor [{lead['id']}] {lead['name']} ({lead.get('niche', '')}):\n\n"
        f"{offer_text}"
    )


def offer_lead(lead_id: str) -> str:
    crm = load_crm()
    lead = next((l for l in crm["items"] if l["id"] == lead_id), None)
    if not lead:
        return f"Lead '{lead_id}' niet gevonden."
    status = lead.get("status")
    if status != "qualified":
        return (
            f"Lead '{lead_id}' heeft status '{status or 'onbekend'}' en is niet gekwalificeerd "
            f"voor een aanbod. Gebruik 'qualify lead {lead_id}' om de lead eerst te kwalificeren."
        )
    return generate_offer(lead, crm)


def offer_niche(niche: str, pain_point: str) -> str:
    """Generate a reusable pitch template for a specific niche + pain point."""
    prompt = (
        f"Schrijf een pitch-template voor niche: {niche}\n"
        f"Pijnpunt: {pain_point}\n"
        f"Dienst/product: {SERVICE_NAME or 'onze dienst'}\n"
        f"Prijsrange: €{PRICE_LOW}–€{PRICE_HIGH}\n\n"
        f"Geef terug:\n"
        f"1. WhatsApp-template (max 2 zinnen, gebruik [NAAM] als placeholder)\n"
        f"2. E-mail-template (max 3 zinnen + onderwerpregel)\n"
        f"3. Uniek verkoopargument voor deze niche"
    )
    result = _ai(prompt, system=_NICHE_SYSTEM)
    return f"📋 Pitch-template voor '{niche}' (pijnpunt: {pain_point}):\n\n{result}"


def offer_all() -> str:
    crm = load_crm()
    eligible = [
        l for l in crm["items"]
        if l.get("status") == "qualified" and not l.get("offers")
    ]
    if not eligible:
        return "Geen gekwalificeerde leads zonder aanbod gevonden."

    results = [generate_offer(lead, crm) for lead in eligible]
    results.append(f"\n{len(eligible)} aanbod(en) gegenereerd.")
    return "\n\n---\n\n".join(results)


def offer_list() -> str:
    crm = load_crm()
    lines = ["Leads met gegenereerde aanbiedingen:"]
    for lead in crm["items"]:
        offers = lead.get("offers", [])
        if offers:
            last = offers[-1].get("ts", "")
            lines.append(
                f"  [{lead['id']}] {lead['name']} | {lead.get('niche', '')} "
                f"| {len(offers)} aanbod(en) | laatste: {last}"
            )
    return "\n".join(lines) if len(lines) > 1 else "Nog geen aanbiedingen gegenereerd."


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

        if msg_lower.startswith("offer lead "):
            lead_id = msg[len("offer lead "):].strip()
            response = offer_lead(lead_id) if lead_id else "Gebruik: offer lead <lead_id>"
        elif msg_lower.startswith("offer niche "):
            parts = msg[len("offer niche "):].strip().split(maxsplit=1)
            if len(parts) == 2:
                response = offer_niche(parts[0], parts[1])
            else:
                response = "Gebruik: offer niche <niche> <pijnpunt>"
        elif msg_lower == "offer all":
            response = offer_all()
        elif msg_lower == "offer list":
            response = offer_list()

        if response:
            print(response)
            append_chatlog({
                "type": "bot",
                "bot": "offer-agent",
                "message": response,
                "ts": now_iso(),
            })

    return new_idx


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    print(f"[{now_iso()}] offer-agent started; poll={POLL_INTERVAL}s "
          f"service='{SERVICE_NAME or '(niet ingesteld)'}' "
          f"price=€{PRICE_LOW}–€{PRICE_HIGH}")
    last_idx = len(load_chatlog())
    write_state({"bot": "offer-agent", "ts": now_iso(), "status": "starting"})

    while True:
        try:
            last_idx = process_chatlog(last_idx)
            write_state({"bot": "offer-agent", "ts": now_iso(), "status": "running"})
        except Exception as exc:
            print(f"[{now_iso()}] ERROR: {exc}")
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
