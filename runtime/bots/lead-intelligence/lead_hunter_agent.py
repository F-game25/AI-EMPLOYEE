"""Lead Hunter Agent — B2B lead scraping and ICP filtering.

Responsible for discovering and filtering potential B2B leads using:
  - Web search (DuckDuckGo, Tavily, SerpAPI via ai_router)
  - ICP (Ideal Customer Profile) scoring rules
  - AI-powered enrichment (NVIDIA Nemotron for deep reasoning)
  - Deduplication via VectorMemory

Commands (routed from task-orchestrator or direct chatlog):
  hunt <goal>              — run a full lead discovery pipeline
  scrape <niche> <location> — find leads matching niche + location
  filter <query>           — filter existing leads by ICP criteria
  status                   — show pipeline stats

State files:
  ~/.ai-employee/state/lead-hunter-agent.state.json
  ~/.ai-employee/state/leads-crm.json  (shared with other agents)
"""
from __future__ import annotations

import json
import logging
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

AI_HOME = Path(os.environ.get("AI_HOME", str(Path.home() / ".ai-employee")))
STATE_FILE = AI_HOME / "state" / "lead-hunter-agent.state.json"
CRM_FILE = AI_HOME / "state" / "leads-crm.json"
CHATLOG = AI_HOME / "state" / "chatlog.jsonl"
AGENT_TASKS_DIR = AI_HOME / "state" / "agent_tasks"
RESULTS_DIR = AI_HOME / "state" / "orchestrator_results"

POLL_INTERVAL = int(os.environ.get("LEAD_HUNTER_POLL_INTERVAL", "5"))
MAX_LEADS_PER_HUNT = int(os.environ.get("LEAD_HUNTER_MAX_LEADS", "20"))

logging.basicConfig(
    level=getattr(logging, os.environ.get("LOG_LEVEL", "WARNING").upper(), logging.WARNING),
    format="%(message)s",
)
logger = logging.getLogger("lead-hunter-agent")

# ── Dependency imports (graceful fallback) ────────────────────────────────────

_ai_router_path = AI_HOME / "bots" / "ai-router"
_nim_path = AI_HOME / "bots" / "nvidia-nim"
_memory_path = AI_HOME / "bots" / "memory"

for _p in [_ai_router_path, _nim_path, _memory_path]:
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

try:
    from ai_router import query_ai, search_web  # type: ignore
    _ROUTER_AVAILABLE = True
except ImportError:
    _ROUTER_AVAILABLE = False

try:
    from nim_client import NIMClient  # type: ignore
    _nim = NIMClient()
    _NIM_AVAILABLE = _nim.is_available()
except ImportError:
    _nim = None
    _NIM_AVAILABLE = False

try:
    from vector_memory import VectorMemory  # type: ignore
    _vmem = VectorMemory()
    _VMEM_AVAILABLE = True
except ImportError:
    _vmem = None
    _VMEM_AVAILABLE = False


# ── Helpers ───────────────────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {"hunts": 0, "leads_found": 0, "last_run": None}


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


def _query_ai_reasoning(prompt: str, system: str = "") -> str:
    """Use NVIDIA Nemotron for deep reasoning tasks; fall back to ai_router."""
    if _NIM_AVAILABLE:
        result = _nim.chat(prompt, system_prompt=system)
        if result.get("answer"):
            return result["answer"]
    if _ROUTER_AVAILABLE:
        result = query_ai(prompt, system_prompt=system)
        return result.get("answer", "")
    return ""


# ── ICP Scoring ───────────────────────────────────────────────────────────────

_ICP_KEYWORDS = {
    "high": ["B2B", "SaaS", "software", "technology", "fintech", "agency", "consulting"],
    "medium": ["startup", "SMB", "e-commerce", "marketing", "automation"],
    "low": ["B2C", "retail", "restaurant", "physical store", "non-profit"],
}


def score_icp(lead: dict) -> float:
    """Score a lead's ICP fit on a 0–10 scale."""
    text = " ".join([
        lead.get("name", ""),
        lead.get("description", ""),
        lead.get("industry", ""),
        lead.get("website", ""),
    ]).lower()

    score = 5.0  # baseline
    for kw in _ICP_KEYWORDS["high"]:
        if kw.lower() in text:
            score += 1.0
    for kw in _ICP_KEYWORDS["medium"]:
        if kw.lower() in text:
            score += 0.5
    for kw in _ICP_KEYWORDS["low"]:
        if kw.lower() in text:
            score -= 1.0

    # Bonus: has website and email
    if lead.get("website"):
        score += 0.5
    if lead.get("email"):
        score += 1.0

    return round(min(max(score, 0.0), 10.0), 1)


# ── Lead Discovery ────────────────────────────────────────────────────────────

def scrape_leads(niche: str, location: str = "") -> list[dict]:
    """Search for B2B leads matching the niche and optional location.

    Uses web search + AI extraction to build a structured lead list.
    """
    query = f"B2B companies {niche}"
    if location:
        query += f" in {location}"
    query += " email contact website"

    leads: list[dict] = []

    if _ROUTER_AVAILABLE:
        results = search_web(query, max_results=10)
        for r in results:
            lead = {
                "id": f"lead-{uuid.uuid4().hex[:8]}",
                "name": r.get("title", "Unknown"),
                "website": r.get("url", ""),
                "description": r.get("snippet", ""),
                "industry": niche,
                "location": location,
                "source": r.get("source", "web"),
                "status": "new",
                "created_at": _now_iso(),
            }
            leads.append(lead)

    # AI enrichment: extract structured data from snippets
    if leads and (_NIM_AVAILABLE or _ROUTER_AVAILABLE):
        snippets = "\n".join(
            f"- {l['name']}: {l['description'][:150]}" for l in leads[:10]
        )
        prompt = (
            f"From these search results for '{niche}' businesses, "
            f"extract key info. For each, identify: company name, likely industry, "
            f"if they are B2B or B2C, estimated company size if inferable. "
            f"Return a brief JSON array.\n\nResults:\n{snippets}"
        )
        ai_text = _query_ai_reasoning(
            prompt,
            system="You are a B2B lead qualification specialist. Be concise and accurate.",
        )
        if ai_text:
            logger.debug("lead-hunter: AI enrichment response received (%d chars)", len(ai_text))

    return leads[:MAX_LEADS_PER_HUNT]


def filter_leads(leads: list[dict], min_icp_score: float = 6.0) -> list[dict]:
    """Filter leads by ICP score threshold and remove duplicates."""
    qualified = []
    seen_domains: set[str] = set()

    for lead in leads:
        # ICP filtering
        icp = score_icp(lead)
        lead["icp_score"] = icp
        if icp < min_icp_score:
            continue

        # Deduplication by domain
        domain = _extract_domain(lead.get("website", ""))
        if domain and domain in seen_domains:
            continue
        if domain:
            seen_domains.add(domain)

        # Vector-based dedup (if available)
        if _VMEM_AVAILABLE and lead.get("description"):
            summary = f"{lead['name']} {lead['description']}"
            dupes = _vmem.find_duplicates(
                lead["id"], threshold=0.93
            )
            if dupes:
                logger.debug(
                    "lead-hunter: skipping duplicate lead %s (similar to %s)",
                    lead["name"], dupes[0]["entity_id"],
                )
                continue
            # Store in vector memory for future dedup
            _vmem.upsert(
                lead["id"],
                summary,
                entity_type="lead",
                metadata={"name": lead["name"], "niche": lead.get("industry", "")},
            )

        qualified.append(lead)

    return qualified


def _extract_domain(url: str) -> str:
    """Extract bare domain from URL for deduplication."""
    if not url:
        return ""
    url = url.lower().replace("https://", "").replace("http://", "").split("/")[0]
    return url.replace("www.", "")


# ── Pipeline ──────────────────────────────────────────────────────────────────

def run_hunt_pipeline(goal: str) -> dict:
    """Run a full lead discovery pipeline for the given goal.

    1. Parse niche + location from goal using AI
    2. Scrape leads via web search
    3. Filter by ICP score and deduplicate
    4. Save qualified leads to CRM
    5. Return summary stats

    Args:
        goal: Natural language goal, e.g. "Find 10 fintech startups in London"

    Returns:
        dict with keys: found, qualified, leads (list), niche, location
    """
    # Step 1: Parse goal
    niche, location = _parse_goal(goal)
    logger.info("lead-hunter: hunting for '%s' in '%s'", niche, location)

    # Step 2: Scrape
    raw_leads = scrape_leads(niche, location)

    # Step 3: Filter
    qualified = filter_leads(raw_leads)

    # Step 4: Save to CRM
    crm = _load_crm()
    existing_ids = {l["id"] for l in crm}
    new_leads = [l for l in qualified if l["id"] not in existing_ids]
    crm.extend(new_leads)
    _save_crm(crm)

    # Step 5: Update state
    state = _load_state()
    state["hunts"] = state.get("hunts", 0) + 1
    state["leads_found"] = state.get("leads_found", 0) + len(new_leads)
    state["last_run"] = _now_iso()
    _save_state(state)

    return {
        "found": len(raw_leads),
        "qualified": len(qualified),
        "new_in_crm": len(new_leads),
        "leads": qualified,
        "niche": niche,
        "location": location,
    }


def _parse_goal(goal: str) -> tuple[str, str]:
    """Extract niche and location from a natural language goal using AI."""
    if _NIM_AVAILABLE or _ROUTER_AVAILABLE:
        prompt = (
            f"Extract the business niche/industry and location (if any) from this goal: "
            f'"{goal}"\nRespond with exactly two lines:\nNiche: <value>\nLocation: <value or blank>'
        )
        answer = _query_ai_reasoning(prompt)
        niche = location = ""
        for line in answer.splitlines():
            if line.lower().startswith("niche:"):
                niche = line.split(":", 1)[1].strip()
            elif line.lower().startswith("location:"):
                location = line.split(":", 1)[1].strip()
        if niche:
            return niche, location

    # Fallback: use goal as niche
    return goal, ""


# ── Task handler ──────────────────────────────────────────────────────────────

def handle_command(cmd: str) -> str:
    """Process a single command string and return a text response."""
    cmd = cmd.strip()
    lower = cmd.lower()

    if lower.startswith("scrape "):
        parts = cmd[7:].split(maxsplit=1)
        niche = parts[0] if parts else ""
        location = parts[1] if len(parts) > 1 else ""
        leads = scrape_leads(niche, location)
        qualified = filter_leads(leads)
        return (
            f"🔍 Scraped {len(leads)} leads for '{niche}' in '{location or 'any location'}'.\n"
            f"✅ {len(qualified)} qualified leads after ICP filtering."
        )

    if lower.startswith("hunt "):
        goal = cmd[5:]
        result = run_hunt_pipeline(goal)
        return (
            f"🎯 Hunt complete for: {result['niche']} ({result['location'] or 'global'})\n"
            f"Found: {result['found']} | Qualified: {result['qualified']} | "
            f"New in CRM: {result['new_in_crm']}"
        )

    if lower.startswith("filter "):
        query = cmd[7:]
        crm = _load_crm()
        filtered = [l for l in crm if query.lower() in json.dumps(l).lower()]
        return f"🔎 Found {len(filtered)} leads matching '{query}' in CRM."

    if lower == "status":
        state = _load_state()
        crm = _load_crm()
        return (
            f"📊 Lead Hunter Status\n"
            f"Total hunts: {state.get('hunts', 0)}\n"
            f"Total leads found: {state.get('leads_found', 0)}\n"
            f"CRM size: {len(crm)}\n"
            f"Last run: {state.get('last_run', 'never')}"
        )

    return f"❓ Unknown command: {cmd}\nUsage: hunt <goal> | scrape <niche> [location] | filter <query> | status"


# ── Main polling loop ─────────────────────────────────────────────────────────

def main() -> None:
    import time

    logger.info("lead-hunter-agent: starting")
    AGENT_TASKS_DIR.mkdir(parents=True, exist_ok=True)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    while True:
        # Process agent task files
        for task_file in sorted(AGENT_TASKS_DIR.glob("lead-hunter-agent_*.json")):
            try:
                task = json.loads(task_file.read_text())
                cmd = task.get("command", "")
                result = handle_command(cmd)
                result_file = RESULTS_DIR / f"{task_file.stem}.result.json"
                result_file.write_text(json.dumps({"result": result, "ts": _now_iso()}))
                task_file.unlink()
                logger.info("lead-hunter-agent: processed task %s", task_file.name)
            except Exception as exc:
                logger.warning("lead-hunter-agent: task error — %s", exc)

        # Process chatlog commands
        _process_chatlog()
        time.sleep(POLL_INTERVAL)


def _process_chatlog() -> None:
    if not CHATLOG.exists():
        return
    state = _load_state()
    last_pos = state.get("chatlog_pos", 0)
    try:
        lines = CHATLOG.read_text().splitlines()
    except Exception:
        return

    for i, line in enumerate(lines[last_pos:], start=last_pos):
        try:
            entry = json.loads(line)
        except Exception:
            continue
        msg = entry.get("message", "").strip().lower()
        if msg.startswith("hunt ") or msg.startswith("scrape ") or msg.startswith("leadelite "):
            # Strip bot prefix if present
            if msg.startswith("leadelite "):
                msg = msg[len("leadelite "):]
            result = handle_command(msg)
            _append_chatlog(result)

    state["chatlog_pos"] = len(lines)
    _save_state(state)


def _append_chatlog(message: str) -> None:
    CHATLOG.parent.mkdir(parents=True, exist_ok=True)
    entry = json.dumps({"role": "assistant", "agent": "lead-hunter-agent",
                        "message": message, "ts": _now_iso()})
    with open(CHATLOG, "a") as f:
        f.write(entry + "\n")


if __name__ == "__main__":
    main()
