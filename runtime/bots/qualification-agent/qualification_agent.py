"""Qualification Agent — filters leads by budget, interest, and need.

Analyses each lead in the shared CRM and assigns a qualification score (0–10)
as the average across three dimensions:
  • Budget   — can they afford a solution?
  • Interest — how engaged are they?
  • Need     — do they have the pain point you solve?

Leads whose average qualification score falls below the threshold are marked
'unqualified' so the sales team can focus only on high-value opportunities.

Commands (via chatlog):
  qualify run               — qualify all leads that have not yet been scored
  qualify lead <lead_id>    — (re)qualify a specific lead
  qualify report            — show qualification scores for all leads
  qualify threshold <0-10>  — update the minimum average score to pass

Config env vars:
  QUALIFY_POLL_INTERVAL     — chatlog poll seconds (default: 5)
  QUALIFY_MIN_SCORE         — minimum average score to pass (default: 5)
"""
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

AI_HOME = Path(os.environ.get("AI_HOME", str(Path.home() / ".ai-employee")))
STATE_FILE = AI_HOME / "state" / "qualification-agent.state.json"
CHATLOG    = AI_HOME / "state" / "chatlog.jsonl"
CRM_FILE   = AI_HOME / "state" / "lead-generator-crm.json"

POLL_INTERVAL = int(os.environ.get("QUALIFY_POLL_INTERVAL", "5"))
MIN_SCORE     = int(os.environ.get("QUALIFY_MIN_SCORE", "5"))

_ai_router_path = AI_HOME / "bots" / "ai-router"
if str(_ai_router_path) not in sys.path:
    sys.path.insert(0, str(_ai_router_path))
try:
    from ai_router import query_ai_for_agent as _query_ai_for_agent  # type: ignore
    _AI_AVAILABLE = True
except ImportError:
    _AI_AVAILABLE = False

# Module-level threshold so 'qualify threshold' can update it at runtime
_threshold = MIN_SCORE

_QUALIFY_SYSTEM = (
    "Je bent een scherpe sales-professional. Geen AI-praat. "
    "Je beoordeelt leads snel en eerlijk op drie criteria: "
    "budget (0-10), interesse (0-10), en behoefte (0-10). "
    "Geef alleen een JSON-object terug. Geen uitleg."
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
    return (_query_ai_for_agent("qualification-agent", prompt, system_prompt=system) or {}).get("answer", "")


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


def _context(lead: dict) -> str:
    """Build a short context string from lead data."""
    messages = lead.get("outreach_messages", [])
    last_msg = messages[-1].get("message", "") if messages else ""
    return (
        f"Naam: {lead['name']}\n"
        f"Niche: {lead.get('niche', '')}\n"
        f"Locatie: {lead.get('location', '')}\n"
        f"Website: {lead.get('website', '')}\n"
        f"Status: {lead.get('status', '')}\n"
        f"Laatste bericht: {last_msg[:400]}"
    )


# ── Core ──────────────────────────────────────────────────────────────────────

def _score_lead(lead: dict) -> dict:
    """Ask the AI to score a lead and return {budget, interest, need, total, verdict}."""
    prompt = (
        f"Beoordeel deze lead op drie criteria (elk 0-10):\n"
        f"{_context(lead)}\n\n"
        f"Geef terug als JSON:\n"
        f'{{"budget": <0-10>, "interest": <0-10>, "need": <0-10>, "reason": "<max 1 zin>"}}'
    )
    raw = _ai(prompt, system=_QUALIFY_SYSTEM)

    # Parse JSON from AI response
    try:
        import re
        match = re.search(r"\{[^}]+\}", raw, re.DOTALL)
        data = json.loads(match.group()) if match else {}
    except Exception:
        data = {}

    def _safe_score(val, default: int = 3) -> int:
        try:
            return max(0, min(10, round(float(val))))
        except (TypeError, ValueError):
            return default

    budget   = _safe_score(data.get("budget"),   3)
    interest = _safe_score(data.get("interest"), 3)
    need     = _safe_score(data.get("need"),     3)
    total    = round((budget + interest + need) / 3, 1)
    verdict  = "qualified" if total >= _threshold else "unqualified"

    return {
        "budget": budget,
        "interest": interest,
        "need": need,
        "total": total,
        "verdict": verdict,
        "reason": data.get("reason", ""),
        "scored_at": now_iso(),
    }


def qualify_lead(lead: dict, crm: dict) -> str:
    scores = _score_lead(lead)
    lead.setdefault("qualification", {})
    lead["qualification"] = scores
    status = scores["verdict"]
    if status == "unqualified":
        # Map internal "unqualified" verdict to a CRM-compatible status
        status = "lost"
    lead["status"] = status
    lead["updated_at"] = now_iso()
    save_crm(crm)

    icon = "✅" if scores["verdict"] == "qualified" else "❌"
    return (
        f"{icon} [{lead['id']}] {lead['name']} — "
        f"budget={scores['budget']} interesse={scores['interest']} "
        f"behoefte={scores['need']} | totaal={scores['total']}/10 → {scores['verdict']}\n"
        f"  Reden: {scores['reason']}"
    )


def run_qualify() -> str:
    crm = load_crm()
    unscored = [
        l for l in crm["items"]
        if "qualification" not in l and l.get("status") not in ("won", "lost", "appointment", "replied")
    ]
    if not unscored:
        return "Alle leads zijn al gekwalificeerd of er zijn geen leads."

    results = [qualify_lead(lead, crm) for lead in unscored]
    qualified = sum(1 for l in unscored if l.get("qualification", {}).get("verdict") == "qualified")
    results.append(
        f"\nResultaat: {qualified}/{len(unscored)} leads gekwalificeerd "
        f"(drempelwaarde: {_threshold}/10)"
    )
    return "\n".join(results)


def qualify_one(lead_id: str) -> str:
    crm = load_crm()
    lead = next((l for l in crm["items"] if l["id"] == lead_id), None)
    if not lead:
        return f"Lead '{lead_id}' niet gevonden."
    return qualify_lead(lead, crm)


def qualify_report() -> str:
    crm = load_crm()
    lines = [f"Kwalificatierapport (drempelwaarde: {_threshold}/10):"]
    for lead in crm["items"]:
        q = lead.get("qualification", {})
        if q:
            icon = "✅" if q.get("verdict") == "qualified" else "❌"
            lines.append(
                f"  {icon} [{lead['id']}] {lead['name']} | "
                f"B={q.get('budget','?')} I={q.get('interest','?')} "
                f"N={q.get('need','?')} | totaal={q.get('total','?')}/10"
            )
        else:
            lines.append(f"  ⬜ [{lead['id']}] {lead['name']} | niet gescoord")
    return "\n".join(lines) if len(lines) > 1 else "CRM is leeg."


def set_threshold(value: str) -> str:
    global _threshold
    try:
        new_val = int(value)
        if not 0 <= new_val <= 10:
            raise ValueError
        _threshold = new_val
        return f"Drempelwaarde ingesteld op {_threshold}/10."
    except ValueError:
        return "Ongeldige waarde. Gebruik een getal tussen 0 en 10."


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

        if msg_lower == "qualify run":
            response = run_qualify()
        elif msg_lower.startswith("qualify lead "):
            lead_id = msg[len("qualify lead "):].strip()
            response = qualify_one(lead_id) if lead_id else "Gebruik: qualify lead <lead_id>"
        elif msg_lower == "qualify report":
            response = qualify_report()
        elif msg_lower.startswith("qualify threshold "):
            value = msg[len("qualify threshold "):].strip()
            response = set_threshold(value)

        if response:
            print(response)
            append_chatlog({
                "type": "bot",
                "bot": "qualification-agent",
                "message": response,
                "ts": now_iso(),
            })

    return new_idx


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    print(f"[{now_iso()}] qualification-agent started; poll={POLL_INTERVAL}s "
          f"min_score={_threshold}/10")
    last_idx = len(load_chatlog())
    write_state({"bot": "qualification-agent", "ts": now_iso(), "status": "starting"})

    while True:
        try:
            last_idx = process_chatlog(last_idx)
            write_state({
                "bot": "qualification-agent",
                "ts": now_iso(),
                "status": "running",
                "threshold": _threshold,
            })
        except Exception as exc:
            print(f"[{now_iso()}] ERROR: {exc}")
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
