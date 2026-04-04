"""Recruiter Bot — recruitment automation: CV screening, candidate outreach, interview scheduling.

Finds candidates via web search, screens CVs with AI, manages the hiring pipeline in a JSON
CRM, and sends personalised outreach and interview invitations.

Commands (via chatlog):
  recruit <role> <requirements>    — start search, find candidates, generate outreach
  recruit screen <cv_text>         — AI CV screening against active role, score 1-10
  recruit candidates               — list all candidates and pipeline status
  recruit interview <candidate_id> — generate interview invitation + scheduling message
  recruit followup                 — follow-ups for pending candidates
  recruit status                   — stats: active searches, candidates, placements

Config env vars:
  RECRUITER_POLL_INTERVAL    — chatlog poll seconds (default: 5)
  RECRUITER_DAILY_LIMIT      — max new candidates per day (default: 30)
  RECRUITER_DEFAULT_ROLE     — default role if none specified
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
STATE_FILE = AI_HOME / "state" / "recruiter.state.json"
CHATLOG    = AI_HOME / "state" / "chatlog.jsonl"
CRM_FILE   = AI_HOME / "state" / "recruiter-crm.json"

POLL_INTERVAL  = int(os.environ.get("RECRUITER_POLL_INTERVAL", "5"))
DAILY_LIMIT    = int(os.environ.get("RECRUITER_DAILY_LIMIT", "30"))
DEFAULT_ROLE   = os.environ.get("RECRUITER_DEFAULT_ROLE", "")

_ai_router_path = AI_HOME / "agents" / "ai-router"
if str(_ai_router_path) not in sys.path:
    sys.path.insert(0, str(_ai_router_path))
try:
    from ai_router import query_ai_for_agent as _query_ai_for_agent, search_web as _search_web  # type: ignore
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
    return (_query_ai_for_agent("recruiter", prompt, system_prompt=system) or {}).get("answer", "")


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
        return {"items": [], "active_roles": []}
    try:
        return json.loads(CRM_FILE.read_text())
    except Exception:
        return {"items": [], "active_roles": []}


def save_crm(crm: dict) -> None:
    CRM_FILE.parent.mkdir(parents=True, exist_ok=True)
    CRM_FILE.write_text(json.dumps(crm, indent=2))


def new_candidate(name: str, role: str) -> dict:
    return {
        "id": str(uuid.uuid4())[:8],
        "name": name,
        "role": role,
        "email": "",
        "linkedin": "",
        "cv_score": 0,
        "cv_summary": "",
        "status": "new",
        "messages": [],
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }


def get_candidate_by_id(crm: dict, cid: str) -> dict | None:
    for item in crm["items"]:
        if item["id"] == cid:
            return item
    return None


def _crm_stats(crm: dict) -> dict:
    statuses = [i["status"] for i in crm["items"]]
    return {
        "total": len(statuses),
        "new": statuses.count("new"),
        "outreached": statuses.count("outreached"),
        "replied": statuses.count("replied"),
        "screened": statuses.count("screened"),
        "interview_scheduled": statuses.count("interview_scheduled"),
        "offer": statuses.count("offer"),
        "hired": statuses.count("hired"),
        "rejected": statuses.count("rejected"),
        "active_roles": len(crm.get("active_roles", [])),
    }


# ── Core logic ────────────────────────────────────────────────────────────────

def start_recruitment(role: str, requirements: str) -> str:
    """Search for candidates online and generate personalised outreach for each."""
    query = f"{role} professional linkedin profile {requirements}"
    raw = _web(query)

    candidates_text = _ai(
        f"Extract up to 8 candidate profiles from this data for the role: {role}\n"
        f"Requirements: {requirements}\n\nSearch data:\n{raw}\n\n"
        "Return a JSON array of objects with keys: name, linkedin, email.",
        system="You are a senior recruitment researcher. Extract real professional profiles "
               "from web snippets. Return valid JSON only.",
    )

    try:
        raw_list = json.loads(re.search(r"\[.*\]", candidates_text, re.DOTALL).group())
    except Exception:
        raw_list = [{"name": f"Candidate #{i+1}", "linkedin": "", "email": ""} for i in range(3)]

    crm = load_crm()
    existing = {i["name"].lower() for i in crm["items"]}

    if role not in crm.get("active_roles", []):
        crm.setdefault("active_roles", []).append(role)

    added = []
    for c in raw_list[:DAILY_LIMIT]:
        name = c.get("name", "Unknown")
        if name.lower() in existing:
            continue

        candidate = new_candidate(name, role)
        candidate["linkedin"] = c.get("linkedin", "")
        candidate["email"] = c.get("email", "")

        outreach = _ai(
            f"Write a personalised LinkedIn/email outreach for:\n"
            f"Name: {name}\nRole: {role}\nRequirements: {requirements}\n"
            f"LinkedIn: {candidate['linkedin']}",
            system="You are a friendly recruiter at a top agency. Write a personalised "
                   "LinkedIn/email outreach message (under 120 words). Be warm, specific "
                   "about the role, and end with a clear next-step CTA.",
        )
        candidate["messages"].append({"type": "outreach", "text": outreach, "ts": now_iso()})
        candidate["status"] = "outreached"

        crm["items"].append(candidate)
        existing.add(name.lower())
        added.append(f"[{candidate['id']}] {name}")

    save_crm(crm)
    return f"Recruitment search for '{role}' complete. Added {len(added)} candidates:\n" + "\n".join(added)


def screen_cv(cv_text: str) -> str:
    """AI-powered CV screening against active role requirements."""
    crm = load_crm()
    active_role = crm.get("active_roles", ["general role"])
    role_context = ", ".join(active_role) if active_role else "general role"

    result = _ai(
        f"Screen this CV for the role(s): {role_context}\n\nCV Text:\n{cv_text}\n\n"
        "Provide: 1) Score out of 10, 2) Key strengths (3 bullets), "
        "3) Gaps/concerns (2 bullets), 4) Recommendation (proceed/reject/maybe).",
        system="You are a senior HR recruiter. Screen this CV objectively and thoroughly. "
               "Be concise but specific. Output structured text.",
    )
    return f"CV Screening Result (role: {role_context}):\n\n{result}"


def list_candidates() -> str:
    crm = load_crm()
    if not crm["items"]:
        return "No candidates in CRM. Use 'recruit <role> <requirements>' to start."
    recent = sorted(crm["items"], key=lambda x: x.get("updated_at", ""), reverse=True)[:15]
    lines = [f"Candidates ({len(crm['items'])} total):"]
    for c in recent:
        lines.append(f"  [{c['id']}] {c['name']} | {c['role']} | score={c['cv_score']} | {c['status']}")
    return "\n".join(lines)


def generate_interview_invite(candidate_id: str) -> str:
    crm = load_crm()
    candidate = get_candidate_by_id(crm, candidate_id)
    if not candidate:
        return f"Candidate '{candidate_id}' not found."

    invite = _ai(
        f"Generate an interview invitation and scheduling message for:\n"
        f"Name: {candidate['name']}\nRole: {candidate['role']}\nEmail: {candidate['email']}",
        system="You are a professional recruiter. Write a warm, clear interview invitation "
               "including proposed time slots (use placeholder dates), video link placeholder, "
               "and preparation tips. Keep it under 150 words.",
    )
    candidate["messages"].append({"type": "interview_invite", "text": invite, "ts": now_iso()})
    candidate["status"] = "interview_scheduled"
    candidate["updated_at"] = now_iso()
    save_crm(crm)
    return f"Interview invite for [{candidate_id}] {candidate['name']}:\n\n{invite}"


def followup_candidates() -> str:
    crm = load_crm()
    cutoff = datetime.now(timezone.utc) - timedelta(days=3)
    due = []

    for c in crm["items"]:
        if c["status"] not in ("outreached", "screened"):
            continue
        try:
            updated_dt = datetime.strptime(c["updated_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        except Exception:
            continue
        if updated_dt < cutoff:
            due.append(c)

    if not due:
        return "No candidates require follow-up right now."

    results = []
    for c in due[:5]:
        msg = _ai(
            f"Write a brief follow-up for this candidate:\nName: {c['name']}\nRole: {c['role']}\n"
            f"Last contact: {c['updated_at']}",
            system="You are a recruiter. Write a short, friendly follow-up (60 words max). "
                   "Reference the role and keep it light.",
        )
        c["messages"].append({"type": "followup", "text": msg, "ts": now_iso()})
        c["updated_at"] = now_iso()
        results.append(f"[{c['id']}] {c['name']}: follow-up generated")

    save_crm(crm)
    return "\n".join(results)


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

        if msg_lower.startswith("recruit screen "):
            cv_text = msg[len("recruit screen "):].strip()
            result = screen_cv(cv_text) if cv_text else "Usage: recruit screen <cv_text>"
            append_chatlog({"type": "bot", "bot": "recruiter", "message": result, "ts": now_iso()})

        elif msg_lower.startswith("recruit candidates"):
            result = list_candidates()
            append_chatlog({"type": "bot", "bot": "recruiter", "message": result, "ts": now_iso()})

        elif msg_lower.startswith("recruit interview "):
            cid = msg[len("recruit interview "):].strip()
            result = generate_interview_invite(cid) if cid else "Usage: recruit interview <candidate_id>"
            append_chatlog({"type": "bot", "bot": "recruiter", "message": result, "ts": now_iso()})

        elif msg_lower.startswith("recruit followup"):
            result = followup_candidates()
            append_chatlog({"type": "bot", "bot": "recruiter", "message": result, "ts": now_iso()})

        elif msg_lower.startswith("recruit status"):
            crm = load_crm()
            stats = _crm_stats(crm)
            result = (
                f"Recruiter Stats: total={stats['total']} outreached={stats['outreached']} "
                f"screened={stats['screened']} interviews={stats['interview_scheduled']} "
                f"hired={stats['hired']} active_roles={stats['active_roles']}"
            )
            append_chatlog({"type": "bot", "bot": "recruiter", "message": result, "ts": now_iso()})

        elif msg_lower.startswith("recruit "):
            rest = msg[len("recruit "):].strip()
            parts = rest.split(maxsplit=1)
            role = parts[0] if parts else DEFAULT_ROLE or "Developer"
            requirements = parts[1] if len(parts) > 1 else "experienced professional"
            result = start_recruitment(role, requirements)
            append_chatlog({"type": "bot", "bot": "recruiter", "message": result, "ts": now_iso()})

    return new_idx


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    print(f"[{now_iso()}] recruiter started")
    last_idx = len(load_chatlog())
    crm = load_crm()
    write_state({"bot": "recruiter", "ts": now_iso(), "status": "starting",
                 "total_candidates": len(crm["items"])})

    while True:
        try:
            last_idx = process_chatlog(last_idx)
            crm = load_crm()
            write_state({
                "bot": "recruiter",
                "ts": now_iso(),
                "status": "running",
                "total_candidates": len(crm["items"]),
                "stats": _crm_stats(crm),
            })
        except Exception as exc:
            print(f"[{now_iso()}] ERROR: {exc}")
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
